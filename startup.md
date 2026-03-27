Use this exact checklist on another computer after unzipping the project.

## 1) Unzip and enter project

```bash
cd /path/where/you/unzipped/autoprocure
```

## 2) Create and activate venv

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 3) Install Python dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 4) Install system dependency (Poppler)

### macOS (with Homebrew)
```bash
brew install poppler
```

### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install -y poppler-utils
```

Verify:
```bash
pdftoppm -v
```

## 5) Create `.env` in project root

Set `MONGO_URI` from Atlas **Connect → Drivers** (or use `MONGO_USER` + `MONGO_PASSWORD` per `src/mongo_connection.py`). Do not commit real values.

```env
MODEL_PROVIDER=bedrock
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-20250514-v1:0
BEDROCK_INFERENCE_PROFILE_ARN=us.anthropic.claude-sonnet-4-20250514-v1:0
MONGO_URI=
MONGO_DB=ema
```

## 6) Configure AWS credentials

```bash
aws configure
```

(Use keys from an IAM user/role that has Bedrock invoke permissions and model access enabled.)

## 7) Run ingestion and reconciliation

```bash
cd src
python ingest_to_mongo.py
python reconciliation_agent.py
```

## 8) Start API/UI

```bash
cd app
uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

Open:
- `http://localhost:8080`

---

## One-command quick start (after `.env` + AWS configured)

```bash
cd /path/to/autoprocure && python3 -m venv .venv && source .venv/bin/activate && pip install -U pip && pip install -r requirements.txt && cd src && python ingest_to_mongo.py && python reconciliation_agent.py && cd app && uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

If you want, I can also give you a Windows version (`venv\Scripts\activate`, Chocolatey poppler, etc.).