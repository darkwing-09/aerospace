"""
main.py
─────────────────────────────────────────────────────────────────
FastAPI application for AeroMind Tactical Defense Platform.
Multi-Agent SLM Orchestration, ColPali Visual RAG, Universal Ingestion,
Session-Scoped Document Uploads, LangSmith Tracing, and Evaluation.
"""

import os
import re
import asyncio
import json
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from pydantic import BaseModel

from config import settings, HARDWARE
from security.paths import UnsafePathError, safe_filename, safe_identifier, safe_join
from ingestion_adapter import UnsafeArchiveError
from model_service import ModelService
from pdf_service import pdf_svc
from visual_rag_service import visual_rag_service
from universal_ingestion_service import universal_ingestion
from ingestion_adapter import ingestion_adapter
from agent_orchestrator import multi_agent_orchestrator
from langsmith_service import langsmith_service
from evaluation_service import evaluation_service


# ── Singletons ───────────────────────────────────────────────────
model_svc = ModelService()


# ── Lifespan — auto-load model on startup ────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[AeroMind] Initializing Defense Avionics Platform…")
    print(f"[AeroMind] Hardware tier: {HARDWARE['label']} ({HARDWARE['tier']}) — {HARDWARE['reason']}")
    # Initialize visual RAG index for default manual in background if present
    mig_path = Path(settings.PDF_DIR) / "mig21bis.pdf"
    if mig_path.exists():
        asyncio.create_task(
            asyncio.to_thread(visual_rag_service.index_document, mig_path, "mig21bis")
        )
    asyncio.create_task(model_svc.load_model())
    yield
    print("[AeroMind] Avionics Platform shutdown.")


app = FastAPI(
    title="AeroMind Defense Intelligence API",
    description="Multi-Agent SLM & ColPali Visual RAG Aviation System",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ──────────────────────────────────────────────────────
class Message(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    aircraft_id: Optional[str] = None
    session_id: Optional[str] = None
    doc_id: Optional[str] = None
    messages: List[Message]


# ── Core Endpoints ───────────────────────────────────────────────

@app.get("/api/health")
async def health():
    models = await model_svc.check_configured_models()
    return {
        "status": "ok",
        "model_loaded": model_svc.is_loaded,
        "model_loading": model_svc.is_loading,
        "model_type": model_svc.model_type,
        "multi_agent_enabled": settings.ENABLE_MULTI_AGENT,
        "langsmith_cloud_enabled": langsmith_service.is_cloud_enabled(),
        "visual_rag_enabled": settings.ENABLE_VISUAL_RAG,
        "document_count": len(universal_ingestion.list_all_documents()),
        # QW11 / ADR-0007: which device tier was selected at startup and why.
        "hardware": HARDWARE,
        # QW1: configured models that Ollama doesn't have (they now fail loudly).
        "models": models,
    }


def _max_upload_bytes() -> int:
    return settings.MAX_UPLOAD_MB * 1024 * 1024


async def _read_upload_limited(file: UploadFile) -> bytes:
    """Read an upload, refusing anything over MAX_UPLOAD_MB (QW3)."""
    limit = _max_upload_bytes()
    content = await file.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(413, f"File exceeds the {settings.MAX_UPLOAD_MB} MB upload limit.")
    return content


@app.get("/api/aircraft")
async def list_aircraft():
    return pdf_svc.list_aircraft()


@app.get("/api/model/status")
async def model_status():
    status = model_svc.get_status()
    status["langsmith_synced"] = langsmith_service.is_cloud_enabled()
    status["multi_agent"] = settings.ENABLE_MULTI_AGENT
    return status


@app.post("/api/model/load")
async def trigger_model_load(background_tasks: BackgroundTasks):
    if model_svc.is_loaded:
        return {"message": "Model already active", "loaded": True}
    if model_svc.is_loading:
        return {"message": "Model is currently initializing", "loading": True}
    background_tasks.add_task(model_svc.load_model)
    return {"message": "Model load dispatched", "loading": True}


# ── Universal Document Endpoints ─────────────────────────────────

@app.get("/api/documents/list")
async def list_documents(category: Optional[str] = None):
    return universal_ingestion.list_all_documents(category=category)


@app.get("/api/documents/{doc_id}")
async def get_document_meta(doc_id: str):
    doc = universal_ingestion.get_document(doc_id)
    if not doc:
        raise HTTPException(404, f"Document '{doc_id}' not found.")
    return doc


@app.post("/api/documents/upload")
async def upload_universal_file(
    file: UploadFile = File(...),
    category: str = Form("AIRCRAFT_MANUAL"),
    custom_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
):
    try:
        filename = safe_filename(file.filename)
        content = await _read_upload_limited(file)
        result = await universal_ingestion.ingest_file(
            file_obj=content,
            filename=filename,
            category=category,
            custom_name=custom_name,
            description=description,
        )
        return {"success": True, "document": result}
    except (UnsafePathError, UnsafeArchiveError) as e:
        raise HTTPException(400, f"Rejected upload: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Ingestion error: {str(e)}")


@app.post("/api/documents/session-upload")
async def session_document_upload(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
):
    """
    Session-scoped chat upload endpoint.
    Accepts PDF, DOCX, XLSX, CSV, PNG, JPG, ZIP dropped directly in chat.
    Normalizes to standardized document package and indexes in ColPali.
    """
    try:
        filename = safe_filename(file.filename)
        sess = safe_identifier(session_id, "session_id") if session_id else str(uuid.uuid4())[:8]
        stem = Path(filename).stem.lower().replace(" ", "_").replace("-", "_")
        doc_id = safe_identifier(f"sess_{sess}_{stem}", "document id")

        temp_uploads = Path(settings.UPLOADS_DIR)
        temp_uploads.mkdir(parents=True, exist_ok=True)
        dest_path = safe_join(temp_uploads, f"{doc_id}_{filename}")

        content = await _read_upload_limited(file)
        with open(dest_path, "wb") as f:
            f.write(content)

        pkg = ingestion_adapter.normalize_to_pdf_or_image(
            input_path=dest_path,
            doc_id=doc_id,
            session_id=sess,
        )

        # Register in document store so it can be served/viewed
        pdf_target = pkg.get("pdf_path")
        universal_ingestion.documents[doc_id] = {
            "id": doc_id,
            "name": filename,
            "filename": filename,
            "file_path": str(pdf_target or dest_path),
            "file_type": pkg.get("file_type", "pdf"),
            "category": "SESSION_UPLOAD",
            "session_id": sess,
            "description": f"Session-uploaded document: {file.filename}",
            "size_mb": round(len(content) / (1024 * 1024), 2),
            "total_pages": pkg.get("total_pages", 1),
            "accent_color": "#e8780a",
            "created_at": "2026-08-31",
        }
        universal_ingestion._save_registry()

        # Trigger ColPali indexing if PDF is available
        if pdf_target and Path(pdf_target).exists():
            index_meta = visual_rag_service.index_document(Path(pdf_target), doc_id)
            try:
                from colpali_retrieval_service import colpali_retrieval_service
                pages_meta = index_meta.get("pages", [])
                image_paths = {
                    p["page_number"]: visual_rag_service.get_page_image_path(doc_id, p["page_number"])
                    for p in pages_meta
                }
                colpali_retrieval_service.index_document_pages(doc_id, pages_meta, image_paths)
            except Exception as ci_err:
                print(f"[SessionUpload] ColPali index note: {ci_err}")

        return {
            "success": True,
            "doc_id": doc_id,
            "session_id": sess,
            "name": filename,
            "total_pages": pkg.get("total_pages", 1),
            "file_type": pkg.get("file_type", "pdf"),
        }
    except (UnsafePathError, UnsafeArchiveError) as e:
        raise HTTPException(400, f"Rejected upload: {e}")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[SessionUpload Error]:\n{traceback.format_exc()}")
        raise HTTPException(500, f"Session upload failed: {str(e)}")


@app.get("/api/documents/{doc_id}/page/{page_num}/image")
async def get_page_image(doc_id: str, page_num: int):
    """Serve ColPali rendered page image."""
    img_path = visual_rag_service.get_page_image_path(doc_id, page_num)
    if not img_path.exists():
        doc_info = universal_ingestion.get_document(doc_id)
        if doc_info and Path(doc_info["file_path"]).exists():
            img_path = visual_rag_service.render_and_cache_page_image(
                Path(doc_info["file_path"]), doc_id, page_num
            )

    if not img_path or not img_path.exists():
        raise HTTPException(404, f"Page image {page_num} not found for '{doc_id}'.")

    return FileResponse(str(img_path), media_type="image/png")


@app.get("/api/documents/{doc_id}/page/{page_num}/thumb")
async def get_page_thumb(doc_id: str, page_num: int):
    """Serve lightweight thumbnail."""
    thumb_path = visual_rag_service.get_page_thumb_path(doc_id, page_num)
    if not thumb_path.exists():
        doc_info = universal_ingestion.get_document(doc_id)
        if doc_info and Path(doc_info["file_path"]).exists():
            visual_rag_service.render_and_cache_page_image(
                Path(doc_info["file_path"]), doc_id, page_num
            )

    if not thumb_path or not thumb_path.exists():
        raise HTTPException(404, "Thumbnail not found.")

    return FileResponse(str(thumb_path), media_type="image/jpeg")


# ── PDF Manual Endpoint ──────────────────────────────────────────

@app.get("/api/pdf/{aircraft_id}")
async def serve_pdf(aircraft_id: str):
    # Check session/universal document store first
    doc_info = universal_ingestion.get_document(aircraft_id)
    if doc_info and Path(doc_info.get("file_path", "")).exists():
        path = Path(doc_info["file_path"])
    else:
        path = pdf_svc.get_pdf_path(aircraft_id)

    if not path or not path.exists():
        raise HTTPException(404, f"PDF for '{aircraft_id}' not found.")

    return FileResponse(
        str(path),
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "public, max-age=3600",
        },
    )


@app.post("/api/pdf/upload/{aircraft_id}")
async def upload_pdf(aircraft_id: str, file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "File must be a PDF.")
    try:
        safe_identifier(aircraft_id, "aircraft_id")
        content = await _read_upload_limited(file)
    except UnsafePathError as e:
        raise HTTPException(400, f"Rejected upload: {e}")
    result = await pdf_svc.save_pdf(aircraft_id, content)
    return result


# ── Prompt & Trace Inspection Endpoints (LangSmith) ──────────────

@app.get("/api/prompts/inspect")
async def inspect_traces(limit: int = 10):
    return {
        "cloud_enabled": langsmith_service.is_cloud_enabled(),
        "project": settings.LANGCHAIN_PROJECT,
        "recent_traces": langsmith_service.get_recent_traces(limit=limit),
    }


# ── Multi-Agent Chat Streaming Endpoint ──────────────────────────

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    SSE endpoint powered by Multi-Agent SLM Orchestrator.
    Emits live agent status, visual citations, math findings, token stream,
    evaluation scorecards, and synchronized page references.
    """
    if not req.messages:
        raise HTTPException(400, "messages array cannot be empty.")

    target_id = req.doc_id or req.aircraft_id or "default"
    messages_dicts = [m.model_dump() for m in req.messages]

    async def event_generator():
        try:
            if getattr(settings, "ENABLE_GRAPH", False) or os.environ.get("ENABLE_GRAPH", "false").lower() == "true":
                from orchestration.graph import stream_graph_sse_async
                user_query = req.messages[-1].content
                async for event in stream_graph_sse_async(
                    task=user_query,
                    workspace_id=target_id,
                    conversation_id=req.session_id,
                ):
                    yield event
            elif settings.ENABLE_MULTI_AGENT:
                async for event in multi_agent_orchestrator.execute_query_stream(
                    target_id, messages_dicts, model_svc
                ):
                    yield event
            else:
                # Fallback single-stream mode
                user_query = req.messages[-1].content
                context = await asyncio.to_thread(
                    pdf_svc.get_relevant_context, target_id, user_query
                )
                async for token in model_svc.stream_response(
                    target_id, messages_dicts, context=context, capability="synthesis"
                ):
                    safe_token = token.replace("\n", "\\n")
                    yield f"data: {safe_token}\n\n"
        except Exception as e:
            import traceback
            print(f"[AeroMind Chat Stream Exception]:\n{traceback.format_exc()}")
            err_msg = str(e).strip() or "Model server connection timeout."
            yield f"data: [ERROR:{err_msg}]\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
