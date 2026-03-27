# AutoProcure System Architecture

## Overview

AutoProcure is an event-driven, AI-powered procurement reconciliation system that automates document processing and 3-way matching using two autonomous agents.

### System Philosophy

- **Event-Driven**: Components communicate through events, not direct calls
- **Cloud-Native**: S3 for storage, SQS for messaging, MongoDB for data
- **AI-First**: GPT-4o handles classification, extraction, and reconciliation
- **Autonomous**: Agents run independently without manual intervention
- **Type-Safe**: Pydantic models ensure data integrity

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         User/System                           │
│                    Uploads PDF to S3                          │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                    AWS S3 Raw Bucket                          │
│              s3://autoprocure-raw/incoming/                   │
│                                                                │
│  Event Notification → SQS Queue                               │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│         AGENT 1: Classification & Extraction Agent            │
│                                                                │
│  • Polls SQS for S3 events                                    │
│  • Downloads PDF from S3                                      │
│  • Classifies document type (GPT-4o Vision)                   │
│  • Extracts structured data (GPT-4o Vision)                   │
│  • Inserts to MongoDB                                         │
│  • Moves PDF to processed bucket                              │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                      MongoDB Atlas                            │
│                                                                │
│  Collections:                                                 │
│  • purchase_orders                                            │
│  • invoices                                                   │
│  • goods_receipts                                             │
│  • reconciliation_results                                     │
│  • reconciliation_decisions                                   │
│                                                                │
│  Change Streams → Event Notifications                         │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│              AGENT 2: Reconciliation Agent                    │
│                                                                │
│  • Watches MongoDB change streams                             │
│  • Detects document insert/update events                      │
│  • Identifies affected PO(s)                                  │
│  • Fetches related documents                                  │
│  • Performs 3-way matching (GPT-4o)                           │
│  • Calculates approval amounts                                │
│  • Assesses risk and generates recommendations                │
│  • Stores reconciliation results                              │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                            │
│                                                                │
│  • Serves reconciliation results                              │
│  • Handles approval decisions                                 │
│  • Generates S3 presigned URLs for PDFs                       │
│  • Provides analytics endpoints                               │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                   Frontend (Web UI)                           │
│                                                                │
│  • Displays reconciliation dashboard                          │
│  • Shows AI analysis and recommendations                      │
│  • Approval workflow (Approve/Reject/Dispute)                 │
│  • Search and filtering                                       │
└──────────────────────────────────────────────────────────────┘
```

---

## Agent 1: Classification & Extraction

### Purpose
Monitors S3 for new PDF uploads, classifies document type, extracts structured data using AI, and organizes files.

### Technology Stack
- **Language**: Python 3.11+
- **AWS SDK**: boto3
- **AI Model**: OpenAI GPT-4o Vision
- **Validation**: Pydantic
- **Database**: MongoDB (pymongo)

### File
`src/classification_extraction_agent.py`

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│        Classification & Extraction Agent (Daemon)            │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. SQS Event Listener                               │   │
│  │     - Long polling (20 seconds)                      │   │
│  │     - Batch processing (up to 10 messages)           │   │
│  │     - Filter: s3:ObjectCreated:* events              │   │
│  └────────────────────┬─────────────────────────────────┘   │
│                       │                                      │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  2. S3 Download                                       │   │
│  │     - Download PDF to /tmp                           │   │
│  │     - Validate file (size, format)                   │   │
│  └────────────────────┬─────────────────────────────────┘   │
│                       │                                      │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  3. AI Classification & Extraction                   │   │
│  │     - Convert PDF to base64                          │   │
│  │     - Call GPT-4o Vision API                         │   │
│  │     - Classify: PO, Invoice, or GRN                  │   │
│  │     - Extract: All fields and line items             │   │
│  │     - Validate with Pydantic models                  │   │
│  └────────────────────┬─────────────────────────────────┘   │
│                       │                                      │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  4. MongoDB Insert                                    │   │
│  │     - Insert to appropriate collection               │   │
│  │     - Store S3 URI reference                         │   │
│  │     - Add metadata (extracted_at, etc.)              │   │
│  └────────────────────┬─────────────────────────────────┘   │
│                       │                                      │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  5. S3 Organization                                   │   │
│  │     - Copy to processed bucket with prefix:          │   │
│  │       • PO → s3://processed/purchase_orders/         │   │
│  │       • Invoice → s3://processed/invoices/           │   │
│  │       • GRN → s3://processed/goods_receipts/         │   │
│  │     - Optional: Delete from raw bucket               │   │
│  └────────────────────┬─────────────────────────────────┘   │
│                       │                                      │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  6. SQS Cleanup                                       │   │
│  │     - Delete message from queue                      │   │
│  │     - Log success/failure                            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Key Functions

```python
import boto3
import json
from typing import Dict, Any
from openai import OpenAI
from processor import extract_document_data

class ClassificationExtractionAgent:
    def __init__(self):
        self.s3 = boto3.client('s3')
        self.sqs = boto3.client('sqs')
        self.mongo_client = MongoClient(MONGO_URI)
        self.db = self.mongo_client[MONGO_DB]
        self.openai = OpenAI(api_key=OPENAI_API_KEY)
        
    def start(self):
        """Start polling SQS for S3 events"""
        logger.info("Starting Classification & Extraction Agent...")
        
        while self.running:
            messages = self.poll_sqs()
            for message in messages:
                self.process_message(message)
    
    def poll_sqs(self) -> list:
        """Long poll SQS for messages"""
        response = self.sqs.receive_message(
            QueueUrl=SQS_QUEUE_URL,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20
        )
        return response.get('Messages', [])
    
    def process_message(self, message: dict):
        """Process single SQS message"""
        try:
            # Parse S3 event
            event = json.loads(message['Body'])
            if 'Message' in event:  # SNS wrapper
                event = json.loads(event['Message'])
            
            # Extract S3 info
            for record in event.get('Records', []):
                bucket = record['s3']['bucket']['name']
                key = record['s3']['object']['key']
                
                if key.endswith('.pdf'):
                    self.process_document(bucket, key)
            
            # Delete message after successful processing
            self.sqs.delete_message(
                QueueUrl=SQS_QUEUE_URL,
                ReceiptHandle=message['ReceiptHandle']
            )
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def process_document(self, bucket: str, key: str):
        """Download, classify, extract, store, and organize"""
        temp_file = f"/tmp/{os.path.basename(key)}"
        
        try:
            # Download from S3
            self.s3.download_file(bucket, key, temp_file)
            logger.info(f"Downloaded s3://{bucket}/{key}")
            
            # AI Classification & Extraction
            extraction = extract_document_data(temp_file)
            doc_type = extraction.document_type
            
            # Insert to MongoDB
            collection_name = {
                'PURCHASE_ORDER': 'purchase_orders',
                'INVOICE': 'invoices',
                'GOODS_RECEIPT': 'goods_receipts'
            }[doc_type.value]
            
            doc_data = {
                extraction.document_type.value.lower(): extraction.get_document().dict(),
                'source_pdf_path': f"s3://{PROCESSED_BUCKET}/{collection_name}/{os.path.basename(key)}",
                'extracted_at': datetime.utcnow().isoformat()
            }
            
            result = self.db[collection_name].insert_one(doc_data)
            logger.info(f"Inserted to {collection_name}: {result.inserted_id}")
            
            # Copy to processed bucket
            dest_key = f"{collection_name}/{os.path.basename(key)}"
            self.s3.copy_object(
                CopySource={'Bucket': bucket, 'Key': key},
                Bucket=PROCESSED_BUCKET,
                Key=dest_key
            )
            logger.info(f"Copied to s3://{PROCESSED_BUCKET}/{dest_key}")
            
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
```

### Configuration

```bash
# AWS Configuration
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_REGION=us-east-1

# S3 Buckets
export S3_RAW_BUCKET=autoprocure-raw
export S3_PROCESSED_BUCKET=autoprocure-processed

# SQS Queue
export SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789/autoprocure-s3-events

# OpenAI
export OPENAI_API_KEY=sk-...

# MongoDB
export MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/
export MONGO_DB=autoprocure
```

### Running

```bash
# Start the agent
python src/classification_extraction_agent.py

# Or with systemd (production)
sudo systemctl start classification-extraction-agent

# Or with Docker
docker run -d --name classification-agent \
  -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  autoprocure/classification-agent:latest
```

### AWS Infrastructure Setup

```yaml
# S3 Buckets
Resources:
  RawBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: autoprocure-raw
      NotificationConfiguration:
        QueueConfigurations:
          - Event: s3:ObjectCreated:*
            Queue: !GetAtt EventQueue.Arn
            Filter:
              S3Key:
                Rules:
                  - Name: suffix
                    Value: .pdf
  
  ProcessedBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: autoprocure-processed
      VersioningConfiguration:
        Status: Enabled

  # SQS Queue
  EventQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: autoprocure-s3-events
      VisibilityTimeout: 300
      MessageRetentionPeriod: 1209600  # 14 days
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt DeadLetterQueue.Arn
        maxReceiveCount: 3
  
  DeadLetterQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: autoprocure-s3-events-dlq
```

---

## Agent 2: Reconciliation

### Purpose
Watches MongoDB for document changes, performs AI-powered 3-way matching, calculates approval amounts, and provides risk assessments.

### Technology Stack
- **Language**: Python 3.11+
- **AI Model**: OpenAI GPT-4o with Structured Outputs
- **Validation**: Pydantic
- **Database**: MongoDB with Change Streams
- **Concurrency**: Threading

### File
`src/reconciliation_agent.py`

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│           Reconciliation Agent (Daemon)                      │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  1. MongoDB Change Stream Watcher                    │   │
│  │     - Watch 3 collections simultaneously:            │   │
│  │       • purchase_orders                              │   │
│  │       • invoices                                     │   │
│  │       • goods_receipts                               │   │
│  │     - Filter: insert and update operations           │   │
│  │     - Multi-threaded processing                      │   │
│  └────────────────────┬─────────────────────────────────┘   │
│                       │                                      │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  2. Event Handler                                     │   │
│  │     - Parse change event                             │   │
│  │     - Extract affected PO number(s):                 │   │
│  │       • PO inserted → reconcile that PO              │   │
│  │       • Invoice inserted → reconcile reference_po    │   │
│  │       • GRN inserted → reconcile reference_po        │   │
│  └────────────────────┬─────────────────────────────────┘   │
│                       │                                      │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  3. Fetch Related Documents                          │   │
│  │     - Query MongoDB for:                             │   │
│  │       • PO by po_number                              │   │
│  │       • All invoices with reference_po               │   │
│  │       • All GRNs with reference_po                   │   │
│  └────────────────────┬─────────────────────────────────┘   │
│                       │                                      │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  4. AI Reconciliation Analysis                       │   │
│  │     - Prepare comprehensive context (JSON)           │   │
│  │     - Call GPT-4o with Pydantic schema               │   │
│  │     - Perform 3-way matching:                        │   │
│  │       • Compare PO vs Invoice items                  │   │
│  │       • Compare PO vs GRN quantities                 │   │
│  │       • Detect price changes                         │   │
│  │       • Identify missing items                       │   │
│  │       • Calculate deductions                         │   │
│  │     - Assess risk level (low/medium/high)            │   │
│  │     - Generate recommendations                       │   │
│  │     - Provide action items                           │   │
│  └────────────────────┬─────────────────────────────────┘   │
│                       │                                      │
│                       ▼                                      │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  5. Store Results                                     │   │
│  │     - Upsert to reconciliation_results               │   │
│  │     - Include AI analysis and recommendations        │   │
│  │     - Add timestamp                                  │   │
│  │     - Log completion                                 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Pydantic Models

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class ApprovalCalculation(BaseModel):
    """Approval amount calculation with deductions"""
    po_amount: float = Field(description="Purchase order grand total")
    invoice_amount: float = Field(description="Invoice grand total")
    recommended_amount: float = Field(description="Amount to approve after deductions")
    total_deductions: float = Field(description="Sum of all deductions")
    deduction_details: List[str] = Field(description="Itemized deductions with reasons")
    calculation_notes: List[str] = Field(description="Explanation notes")

class AIAnalysis(BaseModel):
    """AI-powered analysis and recommendations"""
    risk_level: str = Field(description="Risk level: low, medium, or high")
    recommendation: str = Field(description="Recommendation: approve, reject, investigate, or dispute")
    reasoning: str = Field(description="Brief explanation of the recommendation")
    action_items: List[str] = Field(description="Specific actions to take")
    estimated_impact: str = Field(description="Financial impact description")

class ReconciliationResult(BaseModel):
    """Complete reconciliation result from AI"""
    status: str = Field(description="Status: matched, amount_mismatch, missing_invoice, missing_goods_receipt, etc.")
    issues: List[str] = Field(default_factory=list, description="List of specific issues found")
    approval_calculation: ApprovalCalculation
    ai_analysis: Optional[AIAnalysis] = Field(default=None)
```

### Key Functions

```python
import threading
from pymongo import MongoClient
from openai import OpenAI

class ReconciliationAgent:
    def __init__(self):
        self.mongo_client = MongoClient(MONGO_URI)
        self.db = self.mongo_client[MONGO_DB]
        self.openai = OpenAI(api_key=OPENAI_API_KEY)
        self.running = False
    
    def start_watching(self):
        """Start watching MongoDB change streams"""
        self.running = True
        logger.info("Starting Reconciliation Agent...")
        
        collections = ['purchase_orders', 'invoices', 'goods_receipts']
        threads = []
        
        for coll_name in collections:
            thread = threading.Thread(
                target=self.watch_collection,
                args=(coll_name,),
                daemon=True
            )
            thread.start()
            threads.append(thread)
        
        # Keep main thread alive
        for thread in threads:
            thread.join()
    
    def watch_collection(self, collection_name: str):
        """Watch a single collection for changes"""
        pipeline = [
            {'$match': {'operationType': {'$in': ['insert', 'update']}}}
        ]
        
        change_stream = self.db[collection_name].watch(pipeline)
        logger.info(f"Watching {collection_name} for changes...")
        
        for change in change_stream:
            try:
                self.handle_change(change, collection_name)
            except Exception as e:
                logger.error(f"Error handling change in {collection_name}: {e}")
    
    def handle_change(self, change: dict, collection_name: str):
        """Handle a single change event"""
        document = change['fullDocument']
        
        # Extract affected PO number
        if collection_name == 'purchase_orders':
            po_number = document['purchase_order']['po_number']
        elif collection_name == 'invoices':
            po_number = document['invoice']['reference_po']
        elif collection_name == 'goods_receipts':
            po_number = document['goods_receipt']['reference_po']
        
        logger.info(f"Change detected in {collection_name}, reconciling {po_number}")
        
        # Reconcile the affected PO
        self.reconcile_po(po_number)
    
    def reconcile_po(self, po_number: str):
        """Reconcile a single PO with AI"""
        # Fetch all related documents
        po_doc = self.db.purchase_orders.find_one(
            {"purchase_order.po_number": po_number}
        )
        
        if not po_doc:
            logger.warning(f"PO {po_number} not found")
            return
        
        invoices = list(self.db.invoices.find(
            {"invoice.reference_po": po_number}
        ))
        
        grns = list(self.db.goods_receipts.find(
            {"goods_receipt.reference_po": po_number}
        ))
        
        # Call AI for reconciliation
        result = self.reconcile_with_ai(po_doc, invoices, grns)
        
        # Store result
        self.db.reconciliation_results.update_one(
            {"po_number": po_number},
            {"$set": {
                **result,
                "po_number": po_number,
                "reconciled_at": datetime.utcnow().isoformat()
            }},
            upsert=True
        )
        
        logger.info(f"Reconciled {po_number}: {result['status']}")
    
    def reconcile_with_ai(self, po_doc, invoices, grns) -> dict:
        """Use GPT-4o to perform reconciliation"""
        # Prepare context
        context = {
            "purchase_order": po_doc['purchase_order'],
            "invoices": [inv['invoice'] for inv in invoices],
            "goods_receipts": [grn['goods_receipt'] for grn in grns]
        }
        
        prompt = f"""Perform 3-way reconciliation analysis.

PURCHASE ORDER:
{json.dumps(context['purchase_order'], indent=2)}

INVOICES ({len(invoices)}):
{json.dumps(context['invoices'], indent=2)}

GOODS RECEIPTS ({len(grns)}):
{json.dumps(context['goods_receipts'], indent=2)}

Analyze and return structured reconciliation result."""
        
        # Call GPT-4o with Pydantic structured outputs
        completion = self.openai.beta.chat.completions.parse(
            model="gpt-4o-2024-08-06",
            messages=[
                {"role": "system", "content": "You are a procurement reconciliation expert."},
                {"role": "user", "content": prompt}
            ],
            response_format=ReconciliationResult,
            temperature=0.2
        )
        
        result = completion.choices[0].message.parsed
        return result.model_dump()
```

### Configuration

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# MongoDB (must have replica set for change streams)
export MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/?replicaSet=rs0
export MONGO_DB=autoprocure
```

### Running

```bash
# Event-driven mode (production)
python src/reconciliation_agent.py --watch

# Full reconciliation (one-time)
python src/reconciliation_agent.py --full

# Manual reconciliation
python src/reconciliation_agent.py PO-12345 PO-67890
```

### MongoDB Setup

```bash
# Initialize replica set (required for change streams)
mongosh --eval "rs.initiate()"

# Create indexes
mongosh autoprocure --eval '
  db.purchase_orders.createIndex({"purchase_order.po_number": 1});
  db.invoices.createIndex({"invoice.reference_po": 1});
  db.goods_receipts.createIndex({"goods_receipt.reference_po": 1});
  db.reconciliation_results.createIndex({"po_number": 1});
'
```

---

## Data Flow

### Complete End-to-End Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: User uploads PDF to S3 raw bucket                   │
│         aws s3 cp invoice.pdf s3://autoprocure-raw/incoming/│
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ S3 Event Notification
┌─────────────────────────────────────────────────────────────┐
│ Step 2: S3 sends event to SQS queue                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ SQS Message
┌─────────────────────────────────────────────────────────────┐
│ Step 3: Agent 1 polls SQS and receives message              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ Download
┌─────────────────────────────────────────────────────────────┐
│ Step 4: Agent 1 downloads PDF from S3 to /tmp               │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ AI Processing
┌─────────────────────────────────────────────────────────────┐
│ Step 5: Agent 1 calls GPT-4o Vision                         │
│         - Classifies document type                           │
│         - Extracts all fields and line items                 │
│         - Returns structured data                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ Database Insert
┌─────────────────────────────────────────────────────────────┐
│ Step 6: Agent 1 inserts structured data to MongoDB          │
│         - Collection: invoices                               │
│         - Stores S3 URI reference                            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ File Organization
┌─────────────────────────────────────────────────────────────┐
│ Step 7: Agent 1 copies PDF to processed bucket              │
│         s3://autoprocure-processed/invoices/invoice.pdf     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ SQS Cleanup
┌─────────────────────────────────────────────────────────────┐
│ Step 8: Agent 1 deletes SQS message                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ Change Stream Event
┌─────────────────────────────────────────────────────────────┐
│ Step 9: MongoDB emits change stream event                   │
│         - Collection: invoices                               │
│         - Operation: insert                                  │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ Event Received
┌─────────────────────────────────────────────────────────────┐
│ Step 10: Agent 2 receives change stream event               │
│          - Extracts reference_po from invoice                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ Fetch Documents
┌─────────────────────────────────────────────────────────────┐
│ Step 11: Agent 2 fetches related documents                  │
│          - PO by po_number                                   │
│          - All invoices with reference_po                    │
│          - All GRNs with reference_po                        │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ AI Reconciliation
┌─────────────────────────────────────────────────────────────┐
│ Step 12: Agent 2 calls GPT-4o for reconciliation            │
│          - 3-way matching analysis                           │
│          - Calculates approval amounts                       │
│          - Assesses risk level                               │
│          - Generates recommendations                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ Store Results
┌─────────────────────────────────────────────────────────────┐
│ Step 13: Agent 2 stores reconciliation results              │
│          - Collection: reconciliation_results                │
│          - Includes AI analysis                              │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ API Query
┌─────────────────────────────────────────────────────────────┐
│ Step 14: Frontend queries FastAPI backend                   │
│          GET /api/reconciliation                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼ Display
┌─────────────────────────────────────────────────────────────┐
│ Step 15: User sees reconciliation results in UI             │
│          - Status, issues, AI analysis                       │
│          - Approval workflow available                       │
└─────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Storage** | AWS S3 | Object storage for PDFs (raw + processed buckets) |
| **Event Queue** | AWS SQS | S3 event notifications queue |
| **Database** | MongoDB Atlas | Document storage with change streams |
| **Backend** | FastAPI | REST API for frontend |
| **Frontend** | Vanilla JS + TailwindCSS | Web UI |
| **AI - Classification** | OpenAI GPT-4o Vision | Document classification and extraction |
| **AI - Reconciliation** | OpenAI GPT-4o (2024-08-06) | 3-way matching with structured outputs |
| **Validation** | Pydantic | Type-safe schemas |
| **Cloud SDK** | boto3 | AWS service integration |
| **Concurrency** | Threading | Multi-threaded event processing |
| **Language** | Python 3.11+ | All backend components |

---

## Deployment

### Local Development

```bash
# Terminal 1: Start MongoDB with replica set
mongod --replSet rs0 --dbpath /data/db
mongosh --eval "rs.initiate()"

# Terminal 2: Start Agent 1
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export S3_RAW_BUCKET=autoprocure-raw
export S3_PROCESSED_BUCKET=autoprocure-processed
export SQS_QUEUE_URL=https://sqs...
export OPENAI_API_KEY=sk-...
export MONGO_URI=mongodb://localhost:27017/?replicaSet=rs0

python src/classification_extraction_agent.py

# Terminal 3: Start Agent 2
export OPENAI_API_KEY=sk-...
export MONGO_URI=mongodb://localhost:27017/?replicaSet=rs0

python src/reconciliation_agent.py --watch

# Terminal 4: Start FastAPI
cd src/app
uvicorn app:app --reload --port 8080

# Terminal 5: Test upload
aws s3 cp test.pdf s3://autoprocure-raw/incoming/
```

### Production Deployment

#### Option 1: EC2/ECS

```yaml
# docker-compose.yml
version: '3.8'

services:
  classification-agent:
    image: autoprocure/classification-agent:latest
    environment:
      - AWS_ACCESS_KEY_ID
      - AWS_SECRET_ACCESS_KEY
      - S3_RAW_BUCKET
      - S3_PROCESSED_BUCKET
      - SQS_QUEUE_URL
      - OPENAI_API_KEY
      - MONGO_URI
    restart: always
    
  reconciliation-agent:
    image: autoprocure/reconciliation-agent:latest
    environment:
      - OPENAI_API_KEY
      - MONGO_URI
    command: ["--watch"]
    restart: always
    
  api:
    image: autoprocure/api:latest
    ports:
      - "8080:8080"
    environment:
      - MONGO_URI
      - S3_PROCESSED_BUCKET
    restart: always
```

#### Option 2: AWS Lambda (Serverless)

```python
# Agent 1 as Lambda function
def lambda_handler(event, context):
    """Triggered by SQS"""
    agent = ClassificationExtractionAgent()
    
    for record in event['Records']:
        agent.process_message(record)
    
    return {'statusCode': 200}

# Agent 2 as Lambda function
def lambda_handler(event, context):
    """Triggered by MongoDB Atlas Triggers"""
    agent = ReconciliationAgent()
    
    for change in event['changes']:
        agent.handle_change(change)
    
    return {'statusCode': 200}
```

#### Option 3: Kubernetes

```yaml
# k8s/classification-agent-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: classification-agent
spec:
  replicas: 2
  selector:
    matchLabels:
      app: classification-agent
  template:
    metadata:
      labels:
        app: classification-agent
    spec:
      containers:
      - name: agent
        image: autoprocure/classification-agent:latest
        env:
        - name: AWS_ACCESS_KEY_ID
          valueFrom:
            secretKeyRef:
              name: aws-credentials
              key: access-key-id
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: openai-credentials
              key: api-key
```

---

## Monitoring & Observability

### Logging

```python
import logging
import structlog

# Structured logging
logger = structlog.get_logger()

# Agent 1 logs
logger.info("document_processed", 
    bucket=bucket,
    key=key,
    doc_type=doc_type,
    processing_time=elapsed
)

# Agent 2 logs
logger.info("reconciliation_completed",
    po_number=po_number,
    status=status,
    risk_level=risk_level,
    processing_time=elapsed
)
```

### Metrics

```python
from prometheus_client import Counter, Histogram, Gauge

# Agent 1 metrics
documents_processed = Counter('documents_processed_total', 'Total documents processed', ['doc_type'])
processing_time = Histogram('document_processing_seconds', 'Document processing time')
extraction_errors = Counter('extraction_errors_total', 'Extraction errors')

# Agent 2 metrics
reconciliations_completed = Counter('reconciliations_completed_total', 'Total reconciliations', ['status'])
reconciliation_time = Histogram('reconciliation_seconds', 'Reconciliation time')
ai_api_calls = Counter('ai_api_calls_total', 'AI API calls', ['model'])
```

### Health Checks

```python
# Agent 1 health check
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "sqs_connected": check_sqs_connection(),
        "s3_accessible": check_s3_access(),
        "mongo_connected": check_mongo_connection(),
        "last_processed": last_processed_timestamp
    }

# Agent 2 health check
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "mongo_connected": check_mongo_connection(),
        "change_streams_active": check_change_streams(),
        "last_reconciled": last_reconciled_timestamp
    }
```

---

## Security

### AWS IAM Policies

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:CopyObject"
      ],
      "Resource": [
        "arn:aws:s3:::autoprocure-raw/*",
        "arn:aws:s3:::autoprocure-processed/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:us-east-1:123456789:autoprocure-s3-events"
    }
  ]
}
```

### MongoDB Security

```javascript
// Create application user with limited permissions
db.createUser({
  user: "autoprocure_app",
  pwd: "secure_password",
  roles: [
    { role: "readWrite", db: "autoprocure" }
  ]
})

// Enable authentication
mongod --auth --replSet rs0
```

### API Key Management

```bash
# Use AWS Secrets Manager
aws secretsmanager create-secret \
  --name autoprocure/openai-api-key \
  --secret-string "sk-..."

# Retrieve in application
import boto3
secrets = boto3.client('secretsmanager')
response = secrets.get_secret_value(SecretId='autoprocure/openai-api-key')
OPENAI_API_KEY = response['SecretString']
```

---

## Cost Optimization

### S3 Lifecycle Policies

```json
{
  "Rules": [
    {
      "Id": "ArchiveRawFiles",
      "Status": "Enabled",
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        },
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ]
    }
  ]
}
```

### OpenAI API Optimization

- **Agent 1**: Uses GPT-4o Vision (~$0.01 per document)
- **Agent 2**: Uses GPT-4o with structured outputs (~$0.02 per reconciliation)
- **Caching**: Store results to avoid re-processing
- **Batch Processing**: Process multiple documents in parallel

### MongoDB Optimization

- **Indexes**: Ensure proper indexes on query fields
- **TTL**: Set TTL on old reconciliation results
- **Compression**: Enable compression for storage savings

---

## Troubleshooting

### Agent 1 Issues

**Problem**: Documents not being processed

```bash
# Check SQS queue
aws sqs get-queue-attributes \
  --queue-url $SQS_QUEUE_URL \
  --attribute-names ApproximateNumberOfMessages

# Check S3 event notifications
aws s3api get-bucket-notification-configuration \
  --bucket autoprocure-raw

# Check agent logs
tail -f logs/classification_agent.log
```

**Problem**: Extraction errors

```bash
# Test extraction locally
python -c "
from processor import extract_document_data
result = extract_document_data('test.pdf')
print(result)
"
```

### Agent 2 Issues

**Problem**: Reconciliations not running

```bash
# Check MongoDB change streams
mongosh --eval "
  db.getMongo().watch([
    {\$match: {operationType: 'insert'}}
  ]).hasNext()
"

# Check replica set status
mongosh --eval "rs.status()"

# Check agent logs
tail -f logs/reconciliation_agent.log
```

---

## Future Enhancements

### Short Term
- [ ] WebSocket for real-time UI updates
- [ ] Email notifications for reconciliation results
- [ ] Batch upload with progress tracking
- [ ] Export reports (PDF/Excel)

### Medium Term
- [ ] Multi-tenant support
- [ ] Role-based access control
- [ ] Audit trail and history
- [ ] Advanced analytics dashboard

### Long Term
- [ ] Machine learning for anomaly detection
- [ ] Predictive analytics for issues
- [ ] ERP system integration
- [ ] Mobile application

---

**Document Version**: 2.0  
**Last Updated**: December 8, 2024  
**Architecture**: Event-Driven with Two Autonomous Agents
