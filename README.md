# AeroMind — Local AI Aviation Platform

AeroMind is a production-grade, local-first aviation maintenance and diagnostics platform. It allows engineers to query aircraft manuals in natural language and receive structured step-by-step instructions synced with the exact PDF page.

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- HuggingFace Account & Token

### 2. Installation
```bash
# Clone the repository
git clone <repo_url>
cd aeromind

# Run setup
bash setup.sh
```

### 3. Model Download
```bash
python download_model.py --token YOUR_HF_TOKEN
```

### 4. Running the Platform
**Terminal 1 (Backend):**
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload
```

**Terminal 2 (Frontend):**
```bash
cd frontend
npm run dev
```

## 🏗 Architecture
- **Backend:** FastAPI (Python), Transformers, PyMuPDF
- **Frontend:** React 18, Vite, TailwindCSS, react-pdf
- **AI Model:** `varundevmishra09/My_Model` (Fine-tuned LLaMA/Mistral)

## 📁 Project Structure
```
aeromind/
├── backend/
│   ├── main.py          # API Endpoints
│   ├── model_service.py # AI Inference logic
│   ├── pdf_service.py   # PDF & Registry management
│   ├── pdfs/            # Put manuals here
│   └── models/          # HF weight cache
├── frontend/
│   ├── src/
│   │   ├── components/  # React UI
│   │   ├── hooks/       # SSE & API logic
│   │   └── App.jsx      # Layout & Wiring
└── download_model.py    # CLI tool
```

## 📋 Features
- **SSE Streaming:** Real-time AI token generation.
- **Split-Pane Sync:** PDF automatically jumps to relevant pages.
- **Local-First:** No data leaves the machine.
- **Industrial UI:** High-contrast military-industrial aesthetic.

## 🛠 Adding Aircraft
1. Place PDF in `backend/pdfs/`.
2. Add metadata to `AIRCRAFT_REGISTRY` in `backend/pdf_service.py`.
3. Restart backend.

---
Created by Antigravity AI.
