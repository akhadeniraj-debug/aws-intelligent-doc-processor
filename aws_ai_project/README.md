# 📄 AWS Intelligent Document Processor (Serverless IDP)

An event-driven, serverless intelligent document processing pipeline using **AWS S3, AWS Lambda, AWS Textract, AWS Comprehend, and Amazon DynamoDB**, complete with an interactive web dashboard.

---

## 🏗️ Architecture

```text
[Web Dashboard / User] 
       │
       ▼
 [S3 Upload Bucket] 
       │ (S3 ObjectCreated Event)
       ▼
 [AWS Lambda Function] (Python 3.12 + boto3)
       ├───► [AWS Textract]   (OCR, Table & Form Key-Value Extraction)
       ├───► [AWS Comprehend] (Named Entity Recognition: Person, Org, Date, Money)
       │
       ▼
 [Amazon DynamoDB] (ProcessedDocuments Catalog)
       │
       ▼
 [Interactive Web Dashboard] (Real-time Entity Visualizer & JSON Explorer)
```

---

## 🚀 Modes of Operation

This application intelligently switches between two modes depending on whether AWS credentials are provided:

### 1. Sandbox Simulator Mode (Local / Offline)
If you run the app without AWS credentials, it defaults to **Sandbox Mode**.
- **What it does:** It provides a mockup UI experience. It parses raw text locally using `pypdf`, but relies on hardcoded fallbacks and dummy form fields (like "Sarah Jenkins" or "Local Sandbox Applicant") instead of true machine learning extraction. 
- **Use case:** UI development and quick local testing without incurring AWS costs.

### 2. Live AWS Mode (Real-world usage)
When AWS credentials and resources are configured, the app seamlessly connects to the AWS Cloud.
- **What it does:** It sends uploaded files to **AWS Textract** for deep OCR / form field extraction and **AWS Comprehend** for AI-powered Named Entity Recognition (NER), storing the results in **Amazon DynamoDB**.
- **Use case:** Real-world parsing of custom resumes, invoices, and ID cards.

---

## ☁️ Real-World Setup (AWS Mode)

To use the app in the real world and dynamically extract deep details from your custom documents, you must connect it to an AWS Account.

### Step 1: Install Dependencies
Ensure you have the Python dependencies installed:
```bash
pip install -r requirements.txt
pip install pypdf
```

### Step 2: Configure AWS Credentials
If you haven't already, install the AWS CLI and configure your credentials (you will need an Access Key from your AWS Console):
```bash
aws configure
```
*Provide your Access Key ID, Secret Access Key, and set the region to `us-east-1`.*

### Step 3: Deploy Cloud Infrastructure
Deploy the full serverless stack (S3 bucket, Lambda function, IAM execution roles, and DynamoDB table) in 1 command:
```bash
python deploy.py
```
*(Note: This uses AWS SAM under the hood to securely build and deploy your stack).*

### Step 4: Start the Dashboard
Start the local FastAPI server:
```bash
uvicorn server.app:app --host 127.0.0.1 --port 8000
```
Open your browser to 👉 **[http://localhost:8000](http://localhost:8000)**

---

## 📂 Project Structure

```text
e:\aws_ai_project\
├── lambda/
│   └── processor.py           # Lambda handler (Textract + Comprehend + DynamoDB)
├── template.yaml              # AWS SAM / CloudFormation Infrastructure as Code
├── server/
│   └── app.py                 # FastAPI backend (Live AWS + Local Sandbox)
├── web/
│   ├── index.html             # Glassmorphism dark-mode IDP Dashboard
│   ├── style.css              # Modern UI design system
│   └── app.js                 # Pipeline stepper, upload, and NER visualizer
├── sample_documents/          # Real business test documents (Invoice, Resume, ID)
├── deploy.py                  # Automated 1-click CloudFormation deployer
└── requirements.txt           # Python dependencies
```
