import os
from pathlib import Path
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── HuggingFace & Local Weights ────────────────────────────────
    HF_MODEL_ID: str = "varundevmishra09/My_Model"
    HF_TOKEN: str = ""

    # ── llama.cpp / GGUF ───────────────────────────────────────────
    USE_LLAMA_CPP: bool = False
    GGUF_PATH: str = str(Path.home() / "model.gguf")
    GPU_LAYERS: int = 0

    # ── Ollama (SLMs / VLMs) ───────────────────────────────────────
    USE_OLLAMA: bool = True
    OLLAMA_HOST: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    N_CTX: int = 8192

    # ── Multi-Agent SLM Roles & Capability Registry ──────────────
    ENABLE_MULTI_AGENT: bool = True
    AGENT_MODEL_MAP: dict = {
        "orchestrator": os.getenv("ORCHESTRATOR_MODEL", "qwen2.5:3b"),
        "math": os.getenv("MATH_MODEL", "qwen2.5:3b"),
        "vision_table": os.getenv("VISION_MODEL", "qwen2.5:3b"),
        "reasoning": os.getenv("REASONING_MODEL", "qwen2.5:3b"),
        "verification": os.getenv("VERIFICATION_MODEL", "qwen2.5:3b"),
        "synthesis": os.getenv("SYNTHESIS_MODEL", "qwen2.5:3b"),
    }

    # ── LangSmith Tracing & Observability ──────────────────────────
    LANGSMITH_TRACING: bool = True
    LANGCHAIN_TRACING_V2: str = "true"
    LANGCHAIN_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "aeromind-defense-intel"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str = ""

    # ── ColPali & Visual Document RAG ──────────────────────────────
    ENABLE_VISUAL_RAG: bool = True
    PAGE_DPI: int = 150
    MAX_VISUAL_PAGES: int = 3
    MAX_DIAGRAM_SNIPPETS: int = 4
    COLPALI_MODEL_NAME: str = os.getenv("COLPALI_MODEL_NAME", "vidore/colqwen2-v1.0")
    COLPALI_DEVICE: str = os.getenv("COLPALI_DEVICE", "cpu")
    COLPALI_BATCH_SIZE: int = int(os.getenv("COLPALI_BATCH_SIZE", "4"))
    COLPALI_DIMENSION: int = 128  # ColQwen2 multi-vector projection dimension

    # ── Qdrant Vector Store ────────────────────────────────────────
    QDRANT_HOST: str = os.getenv("QDRANT_HOST", "")
    QDRANT_PORT: int = int(os.getenv("QDRANT_PORT", "6333"))
    QDRANT_URL: str = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    QDRANT_PATH: str = str(Path(__file__).parent / "data_repository" / "qdrant_db")

    # ── Generation Parameters ──────────────────────────────────────
    MAX_NEW_TOKENS: int = 300
    TEMPERATURE: float = 0.1
    TOP_P: float = 0.9
    STOP_TOKENS: List[str] = [
        "### Instruction:",
        "### Response:",
        "### System:",
        "###",
        "\n###",
        "<|endoftext|>",
        "<|im_end|>",
    ]

    # ── Storage & Directory Paths ──────────────────────────────────
    BASE_DIR: str = str(Path(__file__).parent)
    PDF_DIR: str = str(Path(__file__).parent / "pdfs")
    MODELS_DIR: str = str(Path(__file__).parent / "models")
    DATA_DIR: str = str(Path(__file__).parent / "data_repository")
    UPLOADS_DIR: str = str(Path(__file__).parent / "data_repository" / "uploads")
    PAGE_IMAGES_DIR: str = str(Path(__file__).parent / "data_repository" / "page_images")
    TRACES_DIR: str = str(Path(__file__).parent / "data_repository" / "traces")

    # ── Context turns ──────────────────────────────────────────────
    MAX_CONTEXT_TURNS: int = 6

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

# Ensure required directories exist
for directory in [
    settings.PDF_DIR,
    settings.MODELS_DIR,
    settings.DATA_DIR,
    settings.UPLOADS_DIR,
    settings.PAGE_IMAGES_DIR,
    settings.TRACES_DIR,
]:
    Path(directory).mkdir(parents=True, exist_ok=True)
