"""
main.py
─────────────────────────────────────────────────────────────────
FastAPI application — all routes, CORS, SSE streaming, startup.

Endpoints:
  GET  /api/health
  GET  /api/aircraft
  GET  /api/pdf/{aircraft_id}
  POST /api/pdf/upload/{aircraft_id}
  GET  /api/model/status
  POST /api/model/load
  POST /api/chat/stream             ← main SSE endpoint
"""
import re
import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from config import settings
from model_service import ModelService
from pdf_service import PDFService


# ── Singletons ───────────────────────────────────────────────────
model_svc = ModelService()
pdf_svc = PDFService()


# ── Lifespan — auto-load model on startup ────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[AeroMind] Starting up…")
    # Load model in background so health endpoint responds immediately
    asyncio.create_task(model_svc.load_model())
    yield
    print("[AeroMind] Shutting down.")


app = FastAPI(
    title="AeroMind API",
    description="Local aviation maintenance AI — MiG-21BIS and more",
    version="1.0.0",
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
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    aircraft_id: str
    messages: List[Message]


# ── Page reference extractor ─────────────────────────────────────
def extract_page_ref(text: str, aircraft_id: str = "mig21bis") -> int:
    """
    Extract the most relevant page number from model response text.

    Priority order:
    1. "REFERENCE: Part X, Page N"  (training format)
    2. "Reference: Part X, Page N"  (case-insensitive)
    3. "page N" anywhere in text
    4. "Page N" anywhere in text
    5. First standalone integer in range 1–330
    6. Fallback: page 1
    """
    # Max page for this aircraft
    aircraft_info = pdf_svc.get_aircraft_info(aircraft_id)
    max_page = aircraft_info.get("total_pages", 330) if aircraft_info else 330

    # Pattern 1 & 2: REFERENCE: Part X, Page N
    m = re.search(r"REFERENCE:\s+Part\s+\w+.*?Page\s+(\d+)", text, re.IGNORECASE)
    if m:
        page = int(m.group(1))
        if 1 <= page <= max_page:
            return page

    # Pattern 3 & 4: any "page N" or "Page N"
    matches = re.findall(r"[Pp]age\s+(\d+)", text)
    for match in matches:
        page = int(match)
        if 1 <= page <= max_page:
            return page

    # Pattern 5: first standalone integer in valid range
    numbers = re.findall(r"\b(\d{1,3})\b", text)
    for num in numbers:
        page = int(num)
        if 1 <= page <= max_page:
            return page

    return 1


# ── Routes ───────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": model_svc.is_loaded,
        "model_loading": model_svc.is_loading,
        "model_type": model_svc.model_type,
        "aircraft_count": len(pdf_svc.list_aircraft()),
    }


@app.get("/api/aircraft")
async def list_aircraft():
    return pdf_svc.list_aircraft()


@app.get("/api/model/status")
async def model_status():
    return model_svc.get_status()


@app.post("/api/model/load")
async def trigger_model_load(background_tasks: BackgroundTasks):
    if model_svc.is_loaded:
        return {"message": "Model already loaded", "loaded": True}
    if model_svc.is_loading:
        return {"message": "Model is currently loading", "loading": True}
    background_tasks.add_task(model_svc.load_model)
    return {"message": "Model load triggered", "loading": True}


@app.get("/api/pdf/{aircraft_id}")
async def serve_pdf(aircraft_id: str):
    path = pdf_svc.get_pdf_path(aircraft_id)
    if not path:
        raise HTTPException(
            404,
            detail=f"PDF for '{aircraft_id}' not found. "
                   f"Place the PDF at backend/pdfs/{aircraft_id}.pdf",
        )
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
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "File must be a PDF.")
    result = await pdf_svc.save_pdf(aircraft_id, file)
    return result


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    SSE endpoint — streams model response token by token.

    SSE event types:
      data: <token text>        ← each token as it's generated
      data: [PAGE_REF:N]        ← page reference after response completes
      data: [DONE]              ← signals end of stream
      data: [ERROR:<message>]   ← if something goes wrong
    """
    if not req.messages:
        raise HTTPException(400, "messages array cannot be empty.")

    messages_dicts = [m.model_dump() for m in req.messages]

    async def event_generator():
        full_response = ""
        try:
            # 1. Retrieve context from PDF (RAG) - run in thread to avoid blocking
            user_query = req.messages[-1].content if req.messages else ""
            print(f"[AeroMind] Query: {user_query[:80]}...")
            context, top_page = await asyncio.to_thread(
                pdf_svc.get_relevant_context, req.aircraft_id, user_query
            )
            print(f"[AeroMind] RAG context retrieved ({len(context)} chars), top_page={top_page}")

            # Immediately send top_page to frontend to trigger PDF auto-scroll
            if top_page:
                yield f"data: [PAGE_REF:{top_page}]\n\n"

            # 2. Stream from model with context — each token is a separate SSE event
            async for token in model_svc.stream_response(
                req.aircraft_id, messages_dicts, context=context
            ):
                full_response += token
                # Escape newlines for SSE transport (frontend will unescape)
                safe_token = token.replace("\n", "\\n")
                yield f"data: {safe_token}\n\n"

            # 3. Extract page reference from complete response
            page_ref = extract_page_ref(full_response, req.aircraft_id)
            print(f"[AeroMind] Response complete ({len(full_response)} chars), page_ref={page_ref}")
            yield f"data: [PAGE_REF:{page_ref}]\n\n"

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            print(f"[AeroMind Error] Chat Stream Exception:\n{error_detail}")
            err_msg = str(e).strip() or "Model server connection lost or timeout."
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
