"""
Intelligent Document Processor - FastAPI Backend
Supports both Live AWS Mode (boto3) and Local Sandbox Mode
"""

import os
import json
import uuid
import time
import shutil
from datetime import datetime
from typing import List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Form  # type: ignore
from fastapi.middleware.cors import CORSMiddleware  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
import boto3  # type: ignore

app = FastAPI(title="Intelligent Document Processor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
SAMPLE_DIR = BASE_DIR / "sample_documents"
SAMPLE_DIR.mkdir(exist_ok=True)
DATA_FILE = BASE_DIR / "local_documents.json"

# AWS Configuration from environment or defaults
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_BUCKET = os.environ.get("S3_BUCKET", "")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "ProcessedDocuments")

# Check if AWS credentials exist
def check_aws_available():
    try:
        session = boto3.Session()
        credentials = session.get_credentials()
        return credentials is not None and credentials.access_key is not None
    except Exception:
        return False

HAS_AWS = check_aws_available()

# In-memory / local storage persistence for sandbox and local viewing
def load_local_db() -> List[Dict[str, Any]]:
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_local_db(records: List[Dict[str, Any]]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

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


def generate_sandbox_analysis(filename: str, file_path: str) -> Dict[str, Any]:
    """Generate realistic Textract & Comprehend extraction for local demonstration."""
    lower_name = filename.lower()
    
    # Try to extract real text from the file if it exists
    real_text = ""
    if file_path and os.path.exists(file_path):
        try:
            if lower_name.endswith('.pdf'):
                import pypdf
                with open(file_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    for page in reader.pages:
                        real_text += page.extract_text() + "\n"
            elif lower_name.endswith('.txt'):
                with open(file_path, "r", encoding="utf-8") as f:
                    real_text = f.read()
        except Exception:
            pass

    # 1. INVOICE PATTERN
    if any(k in lower_name for k in ["invoice", "bill", "receipt", "inv"]):
        category = "Invoice"
        form_fields = {
            "Invoice Number": f"INV-{uuid.uuid4().hex[:6].upper()}",
            "Invoice Date": "October 03, 2026",
            "Due Date": "November 02, 2026",
            "Vendor Name": "CloudScale Solutions LLC",
            "Vendor Address": "100 Innovation Way, Suite 400, Austin, TX 78701",
            "Subtotal": "$4,250.00",
            "Total Amount Due": "$4,600.62"
        }
        entities = [{"Text": "CloudScale Solutions LLC", "Type": "ORGANIZATION", "Score": 0.994}]
        key_phrases = [{"Text": "Total Amount Due", "Score": 0.998}]
        default_text_lines = ["INVOICE", "CloudScale Solutions LLC", f"Invoice Number: {form_fields['Invoice Number']}"]

    # 2. RESUME PATTERN
    elif any(k in lower_name for k in ["resume", "cv", "profile"]):
        category = "Resume"
        # Try to extract a name from the filename or real text
        name_guess = "Sarah Jenkins"
        if not filename.startswith("sample_"):
            import re
            parts = re.split(r'[_.-]', filename)
            if len(parts) >= 2:
                name_guess = f"{parts[0].capitalize()} {parts[1].capitalize()}"
        
        form_fields = {
            "Candidate Name": name_guess,
            "Target Role": "Local Sandbox Applicant",
            "Email": f"{name_guess.lower().replace(' ', '.')}@example.com",
            "Phone": "+1 (555) 000-0000"
        }
        entities = [{"Text": name_guess, "Type": "PERSON", "Score": 0.998}]
        key_phrases = [{"Text": "Local Sandbox Applicant", "Score": 0.996}]
        default_text_lines = [name_guess.upper(), "Local Sandbox Applicant", "SUMMARY:", "This is a locally processed sandbox fallback."]

    # 3. ID / GOVERNMENT FORM PATTERN
    else:
        category = "ID / Form"
        form_fields = {
            "Document Type": "Local Offline Document",
            "ID / License Number": f"D{uuid.uuid4().hex[:8].upper()}"
        }
        entities = [{"Text": "Local Offline Document", "Type": "OTHER", "Score": 0.994}]
        key_phrases = [{"Text": "Local Offline Document", "Score": 0.997}]
        default_text_lines = ["LOCAL OFFLINE DOCUMENT", f"ID: {form_fields['ID / License Number']}"]

    full_text = real_text.strip() if real_text.strip() else "\n".join(default_text_lines)
    return {
        "category": category,
        "form_fields": form_fields,
        "entities": entities,
        "key_phrases": key_phrases,
        "extracted_text": full_text,
        "word_count": len(full_text.split())
    }

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "aws_connected": HAS_AWS,
        "region": AWS_REGION,
        "s3_bucket": S3_BUCKET or "doc-processor-uploads (sandbox)",
        "dynamodb_table": DYNAMODB_TABLE,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

@app.get("/api/documents")
def list_documents():
    """Retrieve all processed documents."""
    docs = load_local_db()
    return {"documents": docs, "count": len(docs)}

@app.get("/api/documents/{doc_id}")
def get_document(doc_id: str):
    docs = load_local_db()
    for d in docs:
        if d.get("document_id") == doc_id:
            return d
    raise HTTPException(status_code=404, detail="Document not found")

@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    simulate: bool = Form(False)
):
    """Upload document, triggers Textract & Comprehend pipeline, stores in DB."""
    start_time = time.time()
    file_id = f"doc_{uuid.uuid4().hex[:8]}"
    saved_filename = f"{file_id}_{file.filename}"
    file_path = UPLOAD_DIR / saved_filename

    # Save file locally for preview
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    doc_record = None

    # Check if we should run Live AWS or Sandbox Mode
    if HAS_AWS and not simulate:
        try:
            textract_client = boto3.client('textract', region_name=AWS_REGION)
            comprehend_client = boto3.client('comprehend', region_name=AWS_REGION)

            # 1 & 2. AWS Textract (S3 or Direct Bytes)
            if S3_BUCKET:
                s3_client = boto3.client('s3', region_name=AWS_REGION)
                s3_key = f"uploads/{saved_filename}"
                s3_client.upload_file(str(file_path), S3_BUCKET, s3_key)
                
                try:
                    textract_response = textract_client.analyze_document(
                        Document={'S3Object': {'Bucket': S3_BUCKET, 'Name': s3_key}},
                        FeatureTypes=['FORMS']
                    )
                except Exception:
                    textract_response = textract_client.detect_document_text(
                        Document={'S3Object': {'Bucket': S3_BUCKET, 'Name': s3_key}}
                    )
            else:
                s3_key = f"local/{saved_filename}"
                with open(file_path, "rb") as f:
                    doc_bytes = f.read()
                
                try:
                    textract_response = textract_client.analyze_document(
                        Document={'Bytes': doc_bytes},
                        FeatureTypes=['FORMS']
                    )
                except Exception:
                    textract_response = textract_client.detect_document_text(
                        Document={'Bytes': doc_bytes}
                    )

            blocks = textract_response.get('Blocks', [])
            raw_lines = [b['Text'] for b in blocks if b['BlockType'] == 'LINE']
            full_text = "\n".join(raw_lines) or "(No text extracted)"

            # 3. Call AWS Comprehend
            entities_resp = comprehend_client.detect_entities(
                Text=full_text[:4800],
                LanguageCode='en'
            )
            entities = [
                {"Text": e['Text'], "Type": e['Type'], "Score": round(float(e['Score']), 3)}
                for e in entities_resp.get('Entities', [])
            ]

            phrases_resp = comprehend_client.detect_key_phrases(
                Text=full_text[:4800],
                LanguageCode='en'
            )
            key_phrases = [
                {"Text": p['Text'], "Score": round(float(p['Score']), 3)}
                for p in phrases_resp.get('KeyPhrases', [])[:15]
            ]

            duration_ms = int((time.time() - start_time) * 1000)
            doc_record = {
                "document_id": file_id,
                "filename": file.filename,
                "saved_filename": saved_filename,
                "s3_bucket": S3_BUCKET,
                "s3_key": s3_key,
                "category": "AWS Live Extraction",
                "processed_at": datetime.utcnow().isoformat() + "Z",
                "processing_time_ms": duration_ms,
                "status": "COMPLETED",
                "mode": "AWS_LIVE",
                "word_count": len(full_text.split()),
                "extracted_text": full_text,
                "form_fields": parse_textract_forms(blocks),
                "entities": entities,
                "key_phrases": key_phrases
            }

            # Write to DynamoDB
            try:
                if S3_BUCKET and DYNAMODB_TABLE:
                    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
                    table = dynamodb.Table(DYNAMODB_TABLE)
                    table.put_item(Item=doc_record)
            except Exception as dbe:
                print(f"DynamoDB save warning: {dbe}")

        except Exception as aws_err:
            print(f"Live AWS pipeline failed ({aws_err}), falling back to Sandbox Mode")

    # If no AWS or Sandbox requested or AWS failed, run sandbox pipeline
    if not doc_record:
        sandbox_res = generate_sandbox_analysis(file.filename, str(file_path))
        duration_ms = int((time.time() - start_time) * 1000) + 120  # realistic latency
        doc_record = {
            "document_id": file_id,
            "filename": file.filename,
            "saved_filename": saved_filename,
            "s3_bucket": S3_BUCKET or "doc-processor-sandbox",
            "s3_key": f"uploads/{saved_filename}",
            "category": sandbox_res["category"],
            "processed_at": datetime.utcnow().isoformat() + "Z",
            "processing_time_ms": duration_ms,
            "status": "COMPLETED",
            "mode": "SANDBOX_SIMULATOR",
            "word_count": sandbox_res["word_count"],
            "extracted_text": sandbox_res["extracted_text"],
            "form_fields": sandbox_res["form_fields"],
            "entities": sandbox_res["entities"],
            "key_phrases": sandbox_res["key_phrases"]
        }

    # Save to local database
    docs = load_local_db()
    docs.insert(0, doc_record)
    save_local_db(docs)

    return doc_record

@app.post("/api/load-sample")
def load_sample(sample_type: str = Form("invoice")):
    """Quick load pre-built business samples for demoing."""
    sample_files = {
        "invoice": "invoice_sample_2026.png",
        "resume": "sarah_jenkins_resume.txt",
        "id_card": "state_drivers_license_id.png"
    }
    filename = sample_files.get(sample_type, "invoice_sample_2026.png")
    file_id = f"sample_{sample_type}_{uuid.uuid4().hex[:6]}"
    
    sandbox_res = generate_sandbox_analysis(filename, "")
    record = {
        "document_id": file_id,
        "filename": filename,
        "saved_filename": filename,
        "s3_bucket": "intelligent-doc-processor-uploads",
        "s3_key": f"uploads/{filename}",
        "category": sandbox_res["category"],
        "processed_at": datetime.utcnow().isoformat() + "Z",
        "processing_time_ms": 340,
        "status": "COMPLETED",
        "mode": "DEMO_SAMPLE",
        "word_count": sandbox_res["word_count"],
        "extracted_text": sandbox_res["extracted_text"],
        "form_fields": sandbox_res["form_fields"],
        "entities": sandbox_res["entities"],
        "key_phrases": sandbox_res["key_phrases"]
    }
    docs = load_local_db()
    docs.insert(0, record)
    save_local_db(docs)
    return record

@app.delete("/api/documents")
def clear_documents():
    save_local_db([])
    return {"message": "All documents cleared"}

# Serve uploads folder for document previews
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Serve frontend web assets
WEB_DIR = BASE_DIR / "web"
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
