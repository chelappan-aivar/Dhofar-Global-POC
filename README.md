# AutoProcure - Intelligent Procurement Reconciliation System

AutoProcure is an AI-powered procurement document processing and reconciliation system that automates the three-way matching of Purchase Orders (POs), Invoices, and Goods Receipt Notes (GRNs).

## 🌟 Features

### Document Processing
- **AI-Powered Document Extraction**: Uses AWS Bedrock (Claude) with vision-style PDF rendering to extract structured data from PDF documents
- **Multi-Language Support**: Handles documents in English, Japanese, German, Swedish, and more
- **Document Upload**: Drag-and-drop or browse to upload multiple PDFs simultaneously
- **Auto-Classification**: Automatically identifies document type (PO, Invoice, or GRN)
- **Batch Processing**: Upload and process multiple documents at once with progress tracking

### Reconciliation Engine
- **AI-Powered Reconciliation**: Uses AWS Bedrock with Pydantic-guided JSON for intelligent 3-way matching
- **Zero Hardcoded Rules**: AI analyzes documents and makes intelligent decisions without fixed logic
- **Type-Safe Validation**: Pydantic models ensure structured, validated responses
- **Agent-Based Processing**: Background reconciliation agent for high-performance matching
- **Incremental Updates**: Only processes changed POs for real-time efficiency
- **Pre-Computed Results**: Instant reconciliation view with MongoDB-stored results
- **Comprehensive Analysis**: AI checks quantities, prices, descriptions, deliveries, and suspicious patterns
- **Smart Deductions**: AI calculates recommended payment amounts with itemized deductions
- **Risk Assessment**: Automatic risk level classification (low/medium/high)
- **Actionable Recommendations**: AI suggests specific actions to resolve issues

### Approval Workflow
- **Three-Way Decision**: Approve, Reject, or Dispute reconciliation records
- **Comment System**: Add notes and explanations for audit trail
- **Status Tracking**: Real-time visibility of approval status
- **Auto-Navigation**: Uploaded POs automatically open in reconciliation view

### Search & Filtering
- **Universal Search**: Search across all document types (POs, Invoices, GRNs)
- **Smart Filtering**: Search by document number, vendor name, or reference PO
- **Real-Time Results**: Instant filtering as you type
- **Context-Aware**: Search placeholder adapts to current view

### Analytics & Reporting
- **Real-Time Dashboard**: Document counts, match status, and approval metrics
- **Financial Overview**: Total PO value, invoice amounts, approved/pending payments
- **Vendor Scoring**: Performance metrics based on delivery and pricing
- **Outflow Analysis**: Cash flow insights by buyer and time period

### User Interface
- **Modern Design**: Clean, professional interface built with TailwindCSS
- **Responsive Layout**: Works on desktop, tablet, and mobile
- **PDF Viewer**: In-app PDF viewing with modal popup
- **Collapsible Navigation**: Space-saving sidebar with icon-only mode
- **Vendor Branding**: Colored avatars with vendor initials
- **Enhanced Details**: Rich document views with vendor info, delivery locations, and inspection status
- **Multi-Currency Support**: Convert and display amounts in different currencies

## 📋 Prerequisites

- **Python 3.12+**
- **MongoDB** (local or remote instance)
- **AWS account** with **Amazon Bedrock** access for the configured Claude model (and `aws configure` or equivalent credentials)
- **Poppler** (for PDF to image conversion)
- **Node.js** (optional, for frontend development)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone <repository-url>
cd autoprocure
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

**Required packages:**
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `pymongo` - MongoDB driver
- `boto3` - AWS SDK (Bedrock runtime)
- `pdf2image` - PDF processing
- `reportlab` - PDF generation
- `pydantic` - Data validation
- `python-dotenv` - Environment variable management

### 3. Install System Dependencies

#### macOS (using Homebrew)
```bash
brew install poppler
```

#### Ubuntu/Debian
```bash
sudo apt-get install poppler-utils
```

#### Windows
Download and install Poppler from: https://github.com/oschwartz10612/poppler-windows/releases/

### 4. Set Up MongoDB

#### Option A: Local MongoDB
```bash
# macOS
brew tap mongodb/brew
brew install mongodb-community
brew services start mongodb-community

# Ubuntu
sudo apt-get install mongodb
sudo systemctl start mongodb
```

#### Option B: MongoDB Atlas (Cloud)
1. Create account at https://www.mongodb.com/cloud/atlas
2. Create a free cluster
3. In Atlas: **Connect → Drivers** and copy the SRV connection string (replace the placeholder password Atlas shows, or use **Database Access** to create an app user).
4. Put the URI only in `.env` or your shell — do not commit it. Optional: set `MONGO_USER` and `MONGO_PASSWORD` in `.env` and use a URI without embedded credentials; see `src/mongo_connection.py`.
```bash
export MONGO_URI="(paste your Atlas URI here)"
```

### 5. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# AWS Bedrock (see also startup.md)
MODEL_PROVIDER=bedrock
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20240620-v1:0
# Optional: BEDROCK_INFERENCE_PROFILE_ARN=...

# MongoDB Configuration (optional, defaults shown)
MONGO_URI=mongodb://localhost:27017
MONGO_DB=ema
```

Or export directly:
```bash
export MODEL_PROVIDER=bedrock
export AWS_REGION=us-east-1
export MONGO_URI="mongodb://localhost:27017"
export MONGO_DB="ema"
```

### 6. Generate Sample Data

```bash
cd data
python datagen.py
```

This creates 30 sample transaction sets (POs, Invoices, GRNs) in `data/simulated_data_lake/incoming/`

### 7. Process and Ingest Documents

```bash
cd ../src
python ingest_to_mongo.py
```

The optional first positional argument is **deprecated** and ignored.

This will:
- Process PDFs under the configured data lake path (default under `data/simulated_data_lake`)
- Extract structured data using Bedrock
- Store in MongoDB
- Move processed files to respective folders (`purchase_orders/`, `invoices/`, `goods_receipts/`)

### 8. Run AI-Powered Reconciliation Agent

Generate pre-computed reconciliation results using AI:

```bash
cd src
python reconciliation_agent.py
```

This will:
- Use Bedrock-backed `LLMClient` to analyze all POs, Invoices, and GRNs
- Perform intelligent 3-way matching with zero hardcoded rules
- Calculate approval amounts and deductions using AI
- Assess risk levels and provide recommendations
- Store structured results in MongoDB for instant retrieval
- Create indexes for fast queries

**Incremental Mode** (process specific POs only):
```bash
python reconciliation_agent.py PO-12345 PO-67890
```

**Note**: The agent runs automatically in the background when documents are uploaded (incremental mode), but you should run it manually once initially for full reconciliation.

### 9. Start the Application

```bash
cd src/app
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

### 10. Access the Application

Open your browser and navigate to:
```
http://localhost:8080
```

### 11. Upload Documents (Optional)

You can upload new documents directly through the UI:
1. Click the "Upload Document" button in the header
2. Drag and drop PDF files or click to browse
3. Select multiple files for batch upload
4. System automatically extracts data, classifies documents, and runs reconciliation
5. Uploaded POs automatically open in the reconciliation view

## 📁 Project Structure

```
autoprocure/
├── data/
│   ├── datagen.py                    # PDF generator script
│   ├── invoices/                     # Processed invoices
│   ├── purchase_orders/              # Processed POs
│   ├── goods_receipts/               # Processed GRNs
│   └── simulated_data_lake/
│       └── incoming/                 # Unprocessed PDFs
├── src/
│   ├── app/
│   │   ├── app.py                    # FastAPI application & API endpoints
│   │   └── static/
│   │       ├── index.html            # Main UI template
│   │       └── main.js               # Frontend logic & interactions
│   ├── processor.py                  # Bedrock document extraction
│   ├── ingest_to_mongo.py           # Batch ingestion script
│   ├── reconciliation_agent.py      # AI-powered reconciliation agent
│   └── RECONCILIATION_AGENT.md      # Agent documentation
├── .env                              # Environment variables (create this)
├── .env.example                      # Environment template
├── .gitignore                        # Git ignore rules
├── requirements.txt                  # Python dependencies
├── ARCHITECTURE.md                   # System architecture documentation
└── README.md                         # This file
```

> 📖 **For detailed system architecture, data flow, and technical design, see [ARCHITECTURE.md](ARCHITECTURE.md)**

## 🤖 AI-Powered Reconciliation

### Architecture

AutoProcure uses a sophisticated AI-powered reconciliation system:

**Document Extraction:**
- Bedrock (via `LLMClient`) extracts structured data from rendered PDF pages
- Handles multi-language documents automatically
- Classifies document types (PO, Invoice, GRN)

**Reconciliation Analysis:**
- Bedrock with Pydantic JSON schema performs 3-way matching
- Zero hardcoded business rules - AI makes intelligent decisions
- Analyzes quantities, prices, deliveries, and patterns
- Calculates deductions and recommended approval amounts
- Assesses risk levels and provides actionable recommendations

**Technology Stack:**
- **Amazon Bedrock** (Anthropic Claude, model ID from env)
- **Pydantic**: Type-safe validation and schema enforcement
- **MongoDB**: Stores pre-computed reconciliation results
- **FastAPI**: High-performance async API
- **Incremental Processing**: Only reconciles changed documents

### AI Response Structure

```python
class ReconciliationResult(BaseModel):
    status: str  # matched, amount_mismatch, etc.
    issues: List[str]  # Specific problems detected
    approval_calculation: ApprovalCalculation
    ai_analysis: AIAnalysis  # Risk, recommendations, actions

class ApprovalCalculation(BaseModel):
    po_amount: float
    invoice_amount: float
    recommended_amount: float
    total_deductions: float
    deduction_details: List[str]
    calculation_notes: List[str]

class AIAnalysis(BaseModel):
    risk_level: str  # low, medium, high
    recommendation: str  # approve, reject, investigate, dispute
    reasoning: str
    action_items: List[str]
    estimated_impact: str
```

## 🔧 Configuration

### Data Generation

Edit `data/datagen.py` to customize:
- `NUM_TRANSACTIONS`: Number of transaction sets to generate (default: 30)
- `CHAOS_RATE`: Percentage of documents with intentional errors (default: 0.5 = 50%)
- Vendor catalogs, currencies, tax rates

### Document Processing

Edit `src/ingest_to_mongo.py` to customize:
- `--data-lake-path`: Path to PDF folder (default: `../data/simulated_data_lake`)
- `--limit`: Maximum number of PDFs to process (optional)
- `--mongo-uri`: MongoDB connection string
- `--db-name`: Database name

### Application Settings

Edit `src/app/app.py` to customize:
- API endpoints
- Reconciliation logic
- Decision workflow

## 🎯 Usage Guide

### Navigation

- **Reconciliation**: Three-way match dashboard with approval workflow
- **Purchase Orders**: View and search all POs
- **Invoices**: View and search all invoices
- **Goods Receipts**: View and search all GRNs
- **Vendors**: Vendor performance scores and metrics
- **Buyers**: Buyer outflow analysis and spending patterns

### Document Upload

1. Click **"Upload Document"** button in the header
2. **Drag and drop** PDF files or click to browse
3. Select **single or multiple** files (up to 10MB each)
4. System automatically:
   - Extracts data using GPT-4o Vision
   - Classifies document type (PO, Invoice, or GRN)
   - Stores in MongoDB
   - Triggers reconciliation agent
   - Opens uploaded PO in reconciliation view

### Search & Filter

Available in Reconciliation, Invoices, POs, and GRNs views:
- **Real-time search** as you type
- **Smart filtering** by document number, vendor name, or reference PO
- **Clear button** to reset search
- **Context-aware** placeholders guide your search

### Reconciliation Workflow

1. **View Status**: Each PO shows match status with color-coded badges:
   - **Matched** (green): All documents present and match
   - **Amount Mismatch** (amber): Discrepancies in quantities/prices
   - **Missing Invoice/GRN** (gray): Incomplete document set
   - **Ghost PO** (red): Invoice references non-existent PO

2. **Review AI Analysis**: Click a PO to see comprehensive AI-powered insights:
   - **AI Analysis Card**: Purple gradient card with intelligent recommendations
   - **Risk Level**: Low/Medium/High with color-coded badge
   - **Recommendation**: Approve/Reject/Investigate/Dispute
   - **Reasoning**: Clear explanation of AI's decision
   - **Action Items**: 2-3 specific steps to take
   - **Estimated Impact**: Financial implications
   - Full PO details with vendor and buyer information
   - Line items with quantities and prices
   - Linked invoices and GRNs
   - AI-detected issues and discrepancies
   - Smart approval calculation with itemized deductions

3. **Make Decision**: Three options available:
   - **Approve** (green): Accept reconciliation and approve payment
   - **Dispute** (orange): Flag for investigation or vendor discussion
   - **Reject** (red): Reject payment due to issues

4. **Add Comments**: Optional comments for audit trail and team communication

5. **Track Decisions**: View approval status in:
   - List view badges (Approved/Rejected/Dispute/Pending)
   - Analytics bar showing counts
   - Financial overview showing approved/pending amounts

### Analytics Dashboard

The header shows real-time metrics:
- **Documents**: Total count of POs, Invoices, and GRNs
- **Status**: Matched vs. Issues
- **Decisions**: Approved, Rejected, Pending counts
- **Financial**: PO value, Invoice amounts, Approved/Pending payments

### Enhanced Document Views

**Invoices:**
- Vendor avatar and contact info
- Bill To address
- Line items with pricing
- Tax breakdown
- Original currency display
- Notes section

**Goods Receipts:**
- Vendor avatar and delivery info
- Delivery location
- Inspection status summary
- Rejected items alert (if any)
- Receiver signature
- Delivery notes

**Purchase Orders:**
- Vendor details
- Ship To address
- Line items table
- Total amount breakdown
- PDF viewer

### PDF Viewing

Click **"View PDF"** on any document to open it in a modal viewer without leaving the page.

## 🔍 Troubleshooting

### MongoDB Connection Issues

```bash
# Check if MongoDB is running
mongosh

# If using Atlas, verify connection string
mongosh "mongodb+srv://cluster.mongodb.net/" --username <user>
```

### Bedrock / AWS errors

```bash
# Verify region and credentials
aws sts get-caller-identity

# Confirm Bedrock model access is enabled for the account in the AWS console
echo "$MODEL_PROVIDER $AWS_REGION $BEDROCK_MODEL_ID"
```

### PDF Processing Errors

```bash
# Verify Poppler installation
pdftoppm -v

# macOS: Reinstall if needed
brew reinstall poppler
```

### Port Already in Use

```bash
# Find process using port 8080
lsof -i :8080

# Kill the process
kill -9 <PID>

# Or use a different port
uvicorn app:app --port 8081
```

## 🧪 Development

### Running in Development Mode

```bash
# Backend with auto-reload
cd src/app
uvicorn app:app --reload --host 0.0.0.0 --port 8080

# Watch for file changes
# The --reload flag automatically restarts on code changes
```

### Adding New Document Types

1. Update `src/processor.py` to add new `DocumentType` enum
2. Create Pydantic model for the document structure
3. Update `src/ingest_to_mongo.py` collection mapping
4. Add UI rendering in `src/app/static/main.js`

### Customizing Reconciliation Logic

Edit `src/app/app.py` in the `/api/reconciliation` endpoint:
- Modify matching criteria
- Add new validation rules
- Implement custom business logic

## 📊 Database Schema

### Collections

#### `purchase_orders`
```json
{
  "_id": ObjectId,
  "document_type": "purchase_order",
  "source_pdf_path": "/path/to/PO-12345.pdf",
  "purchase_order": {
    "po_number": "PO-12345",
    "date": "2024-12-01",
    "vendor": { "name": "...", "country": "..." },
    "items": [...],
    "grand_total": 1000.00
  }
}
```

#### `invoices`
```json
{
  "_id": ObjectId,
  "document_type": "invoice",
  "source_pdf_path": "/path/to/INV-67890.pdf",
  "invoice": {
    "invoice_number": "INV-67890",
    "reference_po": "PO-12345",
    "vendor": { "name": "...", "country": "..." },
    "items": [...],
    "grand_total": 1000.00
  }
}
```

#### `goods_receipts`
```json
{
  "_id": ObjectId,
  "document_type": "goods_receipt_note",
  "source_pdf_path": "/path/to/GRN-12345.pdf",
  "goods_receipt": {
    "grn_number": "GRN-12345",
    "reference_po": "PO-12345",
    "items": [...]
  }
}
```

#### `reconciliation_decisions`
```json
{
  "_id": ObjectId,
  "po_number": "PO-12345",
  "decision": "approved",  // or "rejected" or "dispute"
  "comment": "All documents match",
  "timestamp": "2024-12-07T01:00:00Z",
  "user": "JA"
}
```

#### `reconciliation_results`
Pre-computed reconciliation data for fast retrieval:
```json
{
  "_id": ObjectId,
  "po_number": "PO-12345",
  "po": { /* full PO document */ },
  "invoices": [ /* array of linked invoices */ ],
  "goods_receipts": [ /* array of linked GRNs */ ],
  "status": "matched",  // or "amount_mismatch", "missing_invoice", etc.
  "issues": [ /* array of detected issues */ ],
  "decision": { /* decision info if exists */ },
  "approval_calculation": {
    "po_amount": 1000.00,
    "invoice_amount": 1000.00,
    "recommended_amount": 950.00,
    "total_deductions": 50.00,
    "deduction_details": [ /* itemized deductions */ ]
  },
  "reconciled_at": "2024-12-07T06:00:00Z"
}
```

## 🔐 Security Considerations

- **API Keys**: Never commit API keys to version control
- **MongoDB**: Use authentication in production
- **CORS**: Configure allowed origins in production
- **File Uploads**: Validate and sanitize file paths
- **User Auth**: Implement authentication for production use

## 🚀 Production Deployment

### Using Docker (Recommended)

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y poppler-utils

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY src/ ./src/
COPY data/ ./data/

# Expose port
EXPOSE 8080

# Run application
CMD ["uvicorn", "src.app.app:app", "--host", "0.0.0.0", "--port", "8080"]
```

Build and run:
```bash
docker build -t autoprocure .
docker run -p 8080:8080 -e MONGO_URI -e AWS_REGION -e MODEL_PROVIDER=bedrock autoprocure
```

### Environment Variables for Production

```bash
# Supply via your host or secrets manager — never commit real values
MODEL_PROVIDER=bedrock
AWS_REGION=us-east-1
MONGO_URI=(Atlas or self-hosted URI from secure storage)
MONGO_DB=ema
```

## 📝 License

[Your License Here]

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📧 Support

For issues and questions:
- Create an issue on GitHub

## 🙏 Acknowledgments

- **Amazon Bedrock** for document and reconciliation models
- **Pydantic** for type-safe data validation
- **FastAPI** for the excellent async web framework
- **MongoDB** for flexible document storage
- **ReportLab** for PDF generation
- **TailwindCSS** for beautiful UI styling

---

**Built with ❤️ and AI for modern procurement teams**
