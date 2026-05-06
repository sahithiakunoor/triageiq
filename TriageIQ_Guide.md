# TriageIQ — End to End Guide
**Team 12 · University of Houston · AI Powered Ticket Intelligence System**

---

## Architecture

```
Layer 1  PostgreSQL · ChromaDB · Docker
Layer 2  DistilBERT (classifier) · XGBoost (priority) · spaCy (entities) · ChromaDB RAG · Llama 3.3-70B
Layer 3  FastAPI (backend) · Streamlit (frontend) · Human-in-the-Loop
```

---

## What You Need Before Starting

- Docker Desktop installed and running
- 15GB+ free disk space
- `jira_issues_50k.csv` dataset
- Groq API key (free at [console.groq.com](https://console.groq.com))
- Google Colab account (free) — for DistilBERT training

---

## Step 1 — Fine-Tune DistilBERT (Google Colab, One-Time)

The project does **not** ship with pre-trained model weights. You must run the Colab notebook once to generate them. This takes ~15 minutes on a free T4 GPU.

### 1.1 Open the notebook

Go to [colab.research.google.com](https://colab.research.google.com) → File → Upload notebook → upload `SupportIQ_DistilBERT_Finetune.ipynb`

### 1.2 Enable GPU
```
Runtime → Change runtime type → T4 GPU → Save
```

### 1.3 Run all cells in order

| Cell | What it does |
|---|---|
| Cell 1 | Install dependencies |
| Cell 2 | Upload `jira_issues_50k.csv` |
| Cell 3 | Load, clean, consolidate issue types (14+ → 5 categories) |
| Cell 4 | Balance classes (CAP=8000, MIN=500 oversampling) |
| Cell 5 | Tokenize with DistilBERT tokenizer (max_length=128) |
| Cell 6 | Fine-tune for 3 epochs (~15 min) with live progress bars |
| Cell 7 | Save label map + training metrics JSON |
| Cell 8 | Smoke test — verify predictions on 5 examples |
| Cell 9 | Zip and download `distilbert_classifier.zip` |

### 1.4 Place model in project
```bash
# Unzip into the backend folder
unzip distilbert_classifier.zip -d <path>/supportiq_v3/backend/

# Verify
ls <path>/supportiq_v3/backend/distilbert_classifier/
# Expected: config.json  label_map.json  model.safetensors
#           tokenizer.json  tokenizer_config.json  training_metrics.json
```

### Training details

| Setting | Value |
|---|---|
| Base model | `distilbert-base-uncased` |
| Dataset | 50K Jira issues (Apache/Spring/JBoss/CodeHaus) |
| Classes | Bug · New Feature · Improvement · Task · Test |
| Class balancing | CAP=8000, MIN=500 oversampling |
| Epochs | 3 |
| Batch size | 32 |
| Learning rate | 2e-5 |
| GPU | T4 (Google Colab free tier) |
| Training time | ~15 minutes |


### Why DistilBERT over plain BERT
- 40% smaller (66M vs 110M parameters)
- 60% faster inference
- 97% of BERT's accuracy on classification tasks
- Fits on free Colab T4 GPU

### Why ONNX Runtime
- 3-5x faster CPU inference vs PyTorch
- No GPU needed at inference time
- Reduces per-ticket analysis from ~60 seconds to ~1 second on CPU
- Converted automatically at first startup

---

## Step 2 — First Time Docker Setup

### 2.1 Create `.env` file
```bash
cd <path>/supportiq_v3
echo "GROQ_API_KEY=gsk_your_key_here" > .env
```

### 2.2 Build and start
```bash
docker-compose up --build
```

Wait for all three of these lines:
```
[Classifier] Loaded DistilBERT ✓
Application startup complete.
You can now view your Streamlit app in your browser.
```

Takes ~10 minutes on first build (spaCy compiles from source on ARM/Apple Silicon).

### 2.3 Open the app
```
http://localhost:8501
```

### 2.4 Train XGBoost Priority Model
1. Go to **Train Models** in sidebar
2. Upload `jira_issues_50k.csv`
3. Click **Train Priority Model / Refresh Training**
4. Wait ~5 minutes — both model cards update automatically with metrics

### 2.5 Seed Knowledge Base
```bash
docker exec supportiq_v3-backend-1 python seed_kb_docs.py
```

---

## Every Restart After That

```bash
cd <path>/supportiq_v3
docker-compose up
```

No `--build` needed. All models and data persist via Docker volumes. DistilBERT loads from the image, XGBoost loads from the volume.

---

## The Full User Flow

```
New Issue → Analyze → Inbox → Issue Detail → Approve/Reject → Analytics
```

### 1. New Issue

- Enter issue title + description (or click a quick example)
- Toggle **Run LLM evaluation** for quality scoring of the AI response
- Click **Analyze Issue →**
- All 5 pipeline layers run in sequence:
  - **DistilBERT** → classifies issue type (Bug/Feature/Improvement/Task/Test)
  - **XGBoost** → predicts priority (P1 Blocker → P5 Trivial)
  - **spaCy** → extracts entities (versions, error codes, frameworks)
  - **ChromaDB RAG** → retrieves relevant KB documents
  - **Llama 3.3-70B** → generates summary, clarifying questions, draft reply
- Results show on the right panel with all 5 layer outputs
- Click **Go to Inbox to Review →** to navigate to Inbox

### 2. LLM Evaluation (optional)

When "Run LLM evaluation" is toggled on, Llama 3.3-70B acts as a judge and evaluates the quality of its own draft reply across 4 dimensions:

| Dimension | What it measures |
|---|---|
| **Faithfulness** | Is the response grounded in the KB context retrieved? |
| **Relevance** | Does the response address the actual issue submitted? |
| **Completeness** | Does it cover all key aspects of the issue? |
| **Tone** | Is it professional and appropriate for an OSS maintainer? |

Each dimension is scored 1–5 (shown as filled/empty blocks). An overall score out of 5 is shown. A brief improvement suggestion is included. This helps maintainers assess whether the AI draft is trustworthy before approving it.

### 3. Inbox

- Shows all issues with category, priority, status, and assignee badges
- Sidebar shows **🔴 N pending** badge when issues need review
- Filter by status or priority using dropdowns
- Click **Open ticket for review →** to open full details

### 4. Issue Detail (Human-in-the-Loop)

- Full AI analysis on the left:
  - Original description
  - Extracted entities (spaCy)
  - AI summary (Llama 3.3-70B)
  - Clarifying questions
  - KB sources used
- Human Review panel on the right:
  - **Draft Reply** — editable AI-generated response
  - **Assign to** — optional maintainer assignment (reflects in Inbox badges)
  - **Notes** — internal notes for the team
  - **Approve** — marks as approved, finalises reply
  - **Save edit** — saves edited reply without final approval
  - **Reject** — marks issue as rejected
- Approved issues show "FINAL REPLY · APPROVED" with the finalised response

### 5. Analytics

- **Total issues** — all issues submitted
- **Resolved** — approved + rejected count
- **Approval rate** — percentage approved
- **P1/P2 critical** — high urgency issue count
- **Avg triage time** — average pipeline processing time in ms
- Issue type distribution chart
- Priority distribution chart
- Status breakdown (pending/approved/rejected)
- SLA performance panel (pending, high urgency, avg triage, resolution rate)
- **Reset DB** button — wipes all tickets for a fresh start

### 6. Train Models

- Status cards at top show current model metrics (source, model name, accuracy, Macro F1, Weighted F1)
- Upload CSV → EDA shown automatically:
  - Issue type distribution chart
  - Priority distribution chart
  - Class imbalance warning with oversampling details
  - Issue type consolidation explanation
- Click **Train Priority Model / Refresh Training** to retrain XGBoost
- DistilBERT is pre-trained in Colab — skipped automatically if detected
- Per-class precision/recall/F1 with support counts shown after training

---

## Models

| Model | Purpose | Trained where | Accuracy |
|---|---|---|---|
| DistilBERT (ONNX) | Issue type classifier | Google Colab T4 GPU | 0.617 |
| XGBoost | Priority predictor | Train Models page in app | 0.558 |
| spaCy en_core_web_sm | Entity extraction | Pre-trained (no training needed) | — |
| Llama 3.3-70B via Groq | Summary / questions / reply / evaluation | API — no training | — |

---

## Dataset

- **Source:** Jira Issue Reports v1 (Apache, Spring, JBoss, CodeHaus)
- **Total size:** 701K rows · 50K used for training
- **Issue type distribution:** Bug 54% · Improvement 17% · Task 8% · New Feature 5% · Test <1%
- **Priority distribution:** P3 Major 67% · P4 Minor 21% · P1 Blocker 3% · P2 Critical 4% · P5 Trivial 2%
- **Class imbalance handling:** Oversampling (CAP=8000, MIN=500) + `class_weight='balanced'`
- **Issue type consolidation** (14+ raw types → 5 categories):
  - Feature Request / Wish → **New Feature**
  - Enhancement / Refactoring / Optimization → **Improvement**
  - Sub-task / Story / Epic / Documentation / Component Upgrade → **Task**
  - Patch → **Bug**

---

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/analyze` | Run full 5-layer pipeline on an issue |
| POST | `/review` | Approve / edit / reject a ticket (HITL) |
| GET | `/tickets` | List all tickets with filters |
| GET | `/tickets/{id}` | Get single ticket details |
| GET | `/analytics` | Aggregate stats |
| POST | `/train/upload` | Upload CSV and start background training job |
| GET | `/train/status/{job_id}` | Poll training progress |
| GET | `/model/info` | Current model metrics |
| POST | `/reset` | Delete all tickets |
| GET | `/health` | Health check |

---

## Docker Volumes (what persists across restarts)

| Volume | Contains | Reset with |
|---|---|---|
| `pg_data` | All tickets in PostgreSQL | `docker-compose down -v` |
| `chroma_data` | KB vector embeddings | `docker-compose down -v` |
| `model_data` | XGBoost pkl files | `docker-compose down -v` |
| `kb_data` | KB text files | `docker-compose down -v` |

DistilBERT is baked into the Docker image — survives volume resets, only changes on `--build`.

---

## Sharing with Teammates

The project does **not** include model weights (268MB). Each person must:

1. Get the project zip — share via Google Drive
2. Run the Colab notebook once to generate `distilbert_classifier/`
3. Place the folder in `backend/` before building
4. Create `.env` with their own Groq API key
5. Run `docker-compose up --build`
6. Train XGBoost via the Train Models page
7. Run `seed_kb_docs.py` to seed the Knowledge Base

Never share the `.env` file — it contains your API key.

---

## Local Run (without Docker)

```bash
# Terminal 1 — Backend
conda activate supportiq
cd backend
export GROQ_API_KEY="gsk_..."
uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
conda activate supportiq
cd frontend
export BACKEND_URL="http://localhost:8000"
streamlit run app.py

# One-time: seed KB
cd backend && python seed_kb_docs.py

# One-time: convert DistilBERT to ONNX (faster inference)
cd backend && python convert_to_onnx.py
```

---

## Troubleshooting

| Issue | Fix |
|---|---|
| "Models not trained" on New Issue | Go to Train Models, upload CSV, click Train |
| Docker won't start | Reset to factory defaults in Docker Desktop → Settings → Troubleshoot |
| Docker disk full / corrupted | `docker system prune -af --volumes` then reinstall Docker Desktop |
| Backend slow to start | Wait 60 sec — DistilBERT loads into memory on startup |
| Inference slow (~5-10 sec) | ONNX not loaded, using PyTorch — wait for background conversion to finish then restart backend |
| ChromaDB telemetry errors | Harmless, ignore |
| spaCy version warning | Harmless, ignore |
| Colab training stuck (no progress bar) | Runtime → Interrupt → reduce EPOCHS to 2 → rerun |
| `distilbert_classifier` folder missing | Run Colab notebook first, place folder in `backend/` |
| XGBoost still shows not_trained after training | Wait for training to complete — it runs in background (~5 min) |
| Duplicate issue submission warning | Change the title or click a new example to clear the form |
| LLM evaluation shows error | Check GROQ_API_KEY is set correctly in `.env` |
