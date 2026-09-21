# AeroMind 2.0 — Multi-Agent SLM & ColPali Visual RAG Defense Intelligence Platform

AeroMind 2.0 is a production-grade, local-first defense intelligence platform designed for military aviation, flight systems diagnostics, and technical manual operations.

---

## 🚀 Key Features

- 🧠 **Multi-Agent SLM Architecture**: Dynamic Supervisor SLM executing parallel & sequential Directed Acyclic Graphs (DAGs) across specialized worker agents:
  - **Mission Commander / Supervisor SLM**: Query analysis & dynamic task decomposition.
  - **ColPali Visual Schematic Agent**: Layout-aware diagram parsing, cockpit blueprint extraction, and visual groundings.
  - **Avionics Math & Physics Engine**: Deterministic flight calculations (Mach to TAS, fuel burn, endurance, unit conversions) with zero hallucination.
  - **Tabular & Logistics Agent**: Multi-format queries across parts manifests and ammunition spreadsheets.
  - **Flight Safety & SOP Validator**: Military emergency protocol validation and mandatory warning/caution injection.
  - **Command Synthesis SLM**: High-structure tactical briefings.
- 📐 **ColPali-Inspired Multimodal Visual RAG**: High-DPI page rendering with interactive blueprint zoom modals and synchronous PDF page jumping.
- 🗄️ **Universal Multi-Dataset Ingestion**: Support for enterprise defense repositories:
  - **PDF** (Aviation manuals & blueprints)
  - **DOCX** (Standard Operating Procedures & checklists)
  - **CSV / XLSX** (Logistics & ammunition manifests)
  - **JSON** (Avionics schemas & telemetry)
  - **Images** (Cockpit photos & inspection graphics)
- 🎙️ **Tactical Voice Interface**:
  - **Voice Input (STT)**: Web Speech recognition with live pulse animation.
  - **Voice Output (TTS)**: Tactical radio voice synthesizer with step-by-step reading.
- 🔬 **LangSmith Tracing & Real-Time Evaluation**:
  - Full LangSmith Cloud integration (`LANGCHAIN_TRACING_V2=true`).
  - Real-time application evaluation scorecards (Faithfulness %, Citation Grounding %, Safety Compliance).
  - In-app Prompt & Execution Trace Inspector.
- ⚡ **Jargon-Free Live HUD**: Visual representation of active agent actions without confusing technical terms.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Node.js 18+
- Ollama with `gemma4:e4b` or local HuggingFace weights

### 2. Environment Configuration
Copy `.env.example` to `backend/.env` and optionally add your LangSmith API key:
```bash
cp backend/.env.example backend/.env
```

### 3. Start Backend
```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000
```

### 4. Start Frontend
```bash
cd frontend
npm run dev
```

---

## 🏗 System Architecture

```
aeromind/
├── backend/
│   ├── main.py                     # FastAPI Endpoints & Multi-Agent SSE Stream
│   ├── config.py                   # Settings (LangSmith, Multi-Agent, ColPali)
│   ├── agent_orchestrator.py       # Multi-Agent SLM DAG & Avionics Math Engine
│   ├── visual_rag_service.py       # ColPali-inspired Visual Document & Page Renderer
│   ├── universal_ingestion_service.py # Multi-format dataset parser (PDF, DOCX, CSV, JSON)
│   ├── langsmith_service.py        # LangSmith Cloud Tracing & Local Inspection Log
│   ├── evaluation_service.py       # Real-Time Quality & Safety Scorecards
│   ├── pdf_service.py              # Aircraft registry & manual manager
│   ├── pdfs/                       # Flight manuals
│   └── data_repository/            # Ingested datasets, visual renders, traces
└── frontend/
    └── src/
        ├── components/
        │   ├── AgentActivityHUD.jsx      # Live multi-agent HUD (jargon-free)
        │   ├── VisualDiagramCard.jsx     # ColPali schematic cards & zoom modal
        │   ├── VoiceController.jsx       # Tactical STT & TTS Voice HUD
        │   ├── EvaluationScorecard.jsx   # Military quality & safety scorecards
        │   ├── UniversalDocumentManager.jsx # Army data center modal
        │   ├── PromptInspectorModal.jsx  # LangSmith trace & prompt inspector
        │   ├── TopBar.jsx                # Navigation & system status telemetry
        │   ├── ChatPanel.jsx             # Left intelligence chat panel
        │   └── PdfViewer.jsx             # Right PDF reader with synced jump
        ├── hooks/
        │   ├── useChat.js                # Multi-Agent SSE stream parser
        │   └── useAircraft.js            # Aircraft manual state
        └── App.jsx                       # Root application wiring
```
