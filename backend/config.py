from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # HuggingFace
    HF_MODEL_ID: str = "varundevmishra09/My_Model"
    HF_TOKEN: str = ""

    # llama.cpp / GGUF
    USE_LLAMA_CPP: bool = True
    GGUF_PATH: str = "/home/darkwing/my_model_q4.gguf"
    N_CTX: int = 4096
    GPU_LAYERS: int = 0

    # Generation
    MAX_NEW_TOKENS: int = 1024
    TEMPERATURE: float = 0.1
    TOP_P: float = 0.9
    STOP_TOKENS: list = [
        "### Instruction:",
        "### Response:",
        "### System:",
        "###",
        "\n###",
        "<|endoftext|>",
        "<|im_end|>",
    ]

    # Paths
    PDF_DIR: str = str(Path(__file__).parent / "pdfs")
    MODELS_DIR: str = str(Path(__file__).parent / "models")

    # Max conversation turns to include in prompt context
    MAX_CONTEXT_TURNS: int = 6

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
