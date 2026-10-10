"""
AWS Lambda Function: Intelligent Document Processor (IDP)
Triggered by: S3 ObjectCreated
Services: AWS Textract + AWS Comprehend + DynamoDB
"""

import json
import os
import urllib.parse
import boto3
from datetime import datetime
from decimal import Decimal

# Initialize AWS SDK clients
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')
comprehend_client = boto3.client('comprehend')
dynamodb = boto3.resource('dynamodb')

DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'ProcessedDocuments')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)


def float_to_decimal(obj):
    """DynamoDB requires Decimal instead of float."""
    if isinstance(obj, float):
        return Decimal(str(round(obj, 4)))
    elif isinstance(obj, dict):
        return {k: float_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [float_to_decimal(i) for i in obj]
    return obj


def parse_textract_forms(blocks):
    """
    Extract key-value pairs (form fields) from Textract AnalyzeDocument blocks.
    """
    key_map = {}
    val_map = {}
    block_map = {}

    for block in blocks:
        block_id = block['Id']
        block_map[block_id] = block
        if block['BlockType'] == 'KEY_VALUE_SET':
            if 'KEY' in block.get('EntityTypes', []):
                key_map[block_id] = block
            elif 'VALUE' in block.get('EntityTypes', []):
                val_map[block_id] = block

    def get_text(result, blocks_dict):
        text = ''
        if 'Relationships' in result:
            for relationship in result['Relationships']:
                if relationship['Type'] == 'CHILD':
                    for child_id in relationship['Ids']:
                        word = blocks_dict.get(child_id)
                        if word and word['BlockType'] == 'WORD':
                            text += word['Text'] + ' '
                        elif word and word['BlockType'] == 'SELECTION_ELEMENT':
                            if word.get('SelectionStatus') == 'SELECTED':
                                text += '[X] '
        return text.strip()

    kvs = {}
    for key_id, key_block in key_map.items():
        key_text = get_text(key_block, block_map)
        val_text = ''
        if 'Relationships' in key_block:
            for rel in key_block['Relationships']:
                if rel['Type'] == 'VALUE':
                    for val_id in rel['Ids']:
                        val_block = val_map.get(val_id)
                        if val_block:
                            val_text = get_text(val_block, block_map)
        if key_text:
            kvs[key_text] = val_text
    return kvs


def process_document(bucket_name, object_key):
    """
    Main extraction pipeline: Textract -> Comprehend -> DynamoDB
    """
    print(f"Processing s3://{bucket_name}/{object_key}")
    start_time = datetime.utcnow()

    # Determine document category from filename/key
    filename = object_key.split('/')[-1]
    doc_category = "General Document"
    lower_name = filename.lower()
    if any(k in lower_name for k in ['invoice', 'bill', 'receipt', 'inv']):
        doc_category = "Invoice"
    elif any(k in lower_name for k in ['resume', 'cv', 'profile']):
        doc_category = "Resume"
    elif any(k in lower_name for k in ['id', 'passport', 'license', 'form']):
        doc_category = "ID / Form"

    # Step 1: Call AWS Textract (AnalyzeDocument with Forms)
    try:
        textract_response = textract_client.analyze_document(
            Document={'S3Object': {'Bucket': bucket_name, 'Name': object_key}},
            FeatureTypes=['FORMS']
        )
    except Exception as e:
        print(f"analyze_document failed, falling back to detect_document_text: {e}")
        textract_response = textract_client.detect_document_text(
            Document={'S3Object': {'Bucket': bucket_name, 'Name': object_key}}
        )

    blocks = textract_response.get('Blocks', [])
    raw_lines = [b['Text'] for b in blocks if b['BlockType'] == 'LINE']
    full_text = "\n".join(raw_lines)
    form_fields = parse_textract_forms(blocks)

    if not full_text.strip():
        full_text = "(No text detected in document)"

    # Step 2: Call AWS Comprehend for Entities & Key Phrases
    # Comprehend text limit per call is 5000 bytes
    comprehend_input_text = full_text[:4800]

    entities_response = comprehend_client.detect_entities(
        Text=comprehend_input_text,
        LanguageCode='en'
    )
    raw_entities = entities_response.get('Entities', [])
    entities_list = [
        {
            "Text": ent['Text'],
            "Type": ent['Type'],
            "Score": float(ent['Score'])
        }
        for ent in raw_entities
    ]

    key_phrases_response = comprehend_client.detect_key_phrases(
        Text=comprehend_input_text,
        LanguageCode='en'
    )
    raw_phrases = key_phrases_response.get('KeyPhrases', [])
    key_phrases_list = [
        {
            "Text": kp['Text'],
            "Score": float(kp['Score'])
        }
        for kp in raw_phrases[:15]  # Top 15 key phrases
    ]

    end_time = datetime.utcnow()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)

    # Step 3: Prepare record for DynamoDB
    record = {
        "document_id": object_key,
        "filename": filename,
        "category": doc_category,
        "s3_bucket": bucket_name,
        "s3_key": object_key,
        "processed_at": end_time.isoformat() + "Z",
        "processing_time_ms": duration_ms,
        "status": "COMPLETED",
        "word_count": len(full_text.split()),
        "extracted_text": full_text,
        "form_fields": form_fields,
        "entities": entities_list,
        "key_phrases": key_phrases_list
    }

    # Step 4: Write to DynamoDB
    table.put_item(Item=float_to_decimal(record))
    print(f"Successfully processed and stored document: {object_key}")
    return record


def lambda_handler(event, context):
    """
    AWS Lambda entrypoint triggered by S3 bucket event.
    """
    print("Received event:", json.dumps(event))
    results = []

    for record in event.get('Records', []):
        bucket_name = record['s3']['bucket']['name']
        object_key = urllib.parse.unquote_plus(
            record['s3']['object']['key'],
            encoding='utf-8'
        )

        try:
            res = process_document(bucket_name, object_key)
            results.append({"status": "SUCCESS", "document_id": object_key})
        except Exception as e:
            print(f"Error processing {object_key}: {e}")
            # Log failure to DynamoDB so dashboard can show failed status
            table.put_item(
                Item=float_to_decimal({
                    "document_id": object_key,
                    "filename": object_key.split('/')[-1],
                    "s3_bucket": bucket_name,
                    "s3_key": object_key,
                    "processed_at": datetime.utcnow().isoformat() + "Z",
                    "status": "FAILED",
                    "error": str(e)
                })
            )
            results.append({"status": "FAILED", "document_id": object_key, "error": str(e)})

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": results})
    }
