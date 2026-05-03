"""
model_service.py
─────────────────────────────────────────────────────────────────
Loads fine-tuned model locally. Two backend options:

  DEFAULT (transformers):
    Downloads from HuggingFace on first run, caches to backend/models/
    Requires: HF_TOKEN in .env

  OPTIONAL (llama-cpp-python):
    Set USE_LLAMA_CPP=true and GGUF_PATH=/path/to/model.gguf in .env
    Faster on CPU, smaller RAM footprint

Prompt format: Alpaca — matches 100k training dataset exactly.

  ### Instruction:
  Aircraft: MIG-21BIS
  Prior conversation context:
  Q: <prior user turn>
  A: <prior assistant turn>

  <current user query>

  ### Response:
"""
import asyncio
import threading
import os
from typing import AsyncGenerator, List, Dict, Optional

from config import settings


class ModelService:
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.llama = None
        self.model_type: Optional[str] = None
        self.is_loaded: bool = False
        self.is_loading: bool = False
        self.load_error: Optional[str] = None

    # ─────────────────────────────────────────────────────────────
    # LOAD
    # ─────────────────────────────────────────────────────────────
    async def load_model(self):
        """Non-blocking — runs model load in thread pool so FastAPI stays responsive."""
        if self.is_loaded or self.is_loading:
            return
        self.is_loading = True
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._load_sync)
        except Exception as e:
            self.load_error = str(e)
            self.is_loading = False
            raise
        self.is_loading = False

    def _load_sync(self):
        import os
        os.makedirs(settings.MODELS_DIR, exist_ok=True)

        if settings.USE_LLAMA_CPP:
            self._load_gguf()
        else:
            self._load_transformers()

        self.is_loaded = True
        print(f"[AeroMind] ✓ Model loaded. Backend: {self.model_type}")



    def _load_gguf(self):
        """Load a GGUF file via llama-cpp-python."""
        import os
        from llama_cpp import Llama

        path = settings.GGUF_PATH
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"GGUF file not found: {path}\n"
                "Set GGUF_PATH in .env or run: python download_model.py --token <TOKEN>"
            )

        self.llama = Llama(
            model_path=path,
            n_ctx=settings.N_CTX,
            n_gpu_layers=settings.GPU_LAYERS,
            verbose=False,
        )
        self.model_type = "gguf"
        print(f"[AeroMind] Loaded GGUF from: {path}")

    def _load_transformers(self):
        """Download and cache from HuggingFace using transformers."""
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        model_id = settings.HF_MODEL_ID
        token = settings.HF_TOKEN or None

        print(f"[AeroMind] Loading tokenizer: {model_id}")
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_id,
            token=token,
            trust_remote_code=True,
            cache_dir=settings.MODELS_DIR,
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        print("[AeroMind] Loading model weights (first run may take 5–15 minutes)…")
        import torch
        # Optimize for CPU
        if not torch.cuda.is_available():
            torch.set_num_threads(os.cpu_count() or 4)
            print(f"[AeroMind] CPU optimization: set_num_threads({os.cpu_count() or 4})")

        self.model = AutoModelForCausalLM.from_pretrained(
            model_id,
            token=token,
            trust_remote_code=True,
            cache_dir=settings.MODELS_DIR,
            device_map="auto",
            torch_dtype=(
                torch.float16 if torch.cuda.is_available() else torch.float32
            ),
            low_cpu_mem_usage=True,
        )
        self.model.eval()
        self.model_type = "transformers"
        print(f"[AeroMind] Loaded: {model_id}")

    # ─────────────────────────────────────────────────────────────
    # PROMPT BUILDER — Alpaca format (matches training data exactly)
    # ─────────────────────────────────────────────────────────────
    @staticmethod
    def _build_prompt(aircraft: str, messages: List[Dict], context: str = "") -> str:
        """
        Build Alpaca-format prompt with conversation history.

        Training format was:
          ### Instruction:
          Aircraft: MIG-21BIS
          <query>

          ### Response:
          <structured answer with Steps>

        For multi-turn, prior turns are prepended as context block.
        Keep last MAX_CONTEXT_TURNS turns to avoid context overflow.
        """
        aircraft_label = aircraft.upper().replace("_", "-").replace("BIS", "BIS")

        # Limit context depth
        context_messages = messages[-(settings.MAX_CONTEXT_TURNS + 1) :]
        prior_turns = context_messages[:-1]
        current_message = context_messages[-1] if context_messages else None

        history_lines = []
        for msg in prior_turns:
            role = msg.get("role", "")
            content = msg.get("content", "").strip()
            if role == "user":
                history_lines.append(f"Q: {content}")
            elif role == "assistant":
                # Truncate long prior answers to save tokens
                truncated = content[:600] + "…" if len(content) > 600 else content
                history_lines.append(f"A: {truncated}")

        context_block = ""
        if history_lines:
            context_block = (
                "Prior conversation context:\n"
                + "\n".join(history_lines)
                + "\n\n"
            )

        query = current_message.get("content", "") if current_message else ""

        context_section = ""
        if context:
            context_section = (
                "Relevant Technical Manual Context:\n"
                f"{context}\n\n"
            )

        system_instruction = (
            "You are a technical assistant for the aircraft. "
            "IMPORTANT FORMATTING INSTRUCTION: If the query is an emergency, start your response with 'EMERGENCY'. "
            "If it is a mechanical issue, start your response with 'MECHANICAL ISSUE'.\n\n"
        )

        return (
            f"### Instruction:\n"
            f"Aircraft: {aircraft_label}\n"
            f"{system_instruction}"
            f"{context_section}"
            f"{context_block}"
            f"{query}\n\n"
            f"### Response:\n"
        )

    # ─────────────────────────────────────────────────────────────
    # STATUS
    # ─────────────────────────────────────────────────────────────
    def get_status(self) -> Dict:
        return {
            "loaded": self.is_loaded,
            "loading": self.is_loading,
            "model_type": self.model_type,
            "model_id": settings.HF_MODEL_ID,
            "error": self.load_error,
        }

    # ─────────────────────────────────────────────────────────────
    # STREAMING INFERENCE
    # ─────────────────────────────────────────────────────────────
    async def stream_response(
        self, aircraft: str, messages: List[Dict], context: str = ""
    ) -> AsyncGenerator[str, None]:
        """
        Async generator that yields tokens one-by-one.
        Dispatches to GGUF or transformers backend based on config.
        """
        if not self.is_loaded:
            if self.is_loading:
                yield "⏳ Model is still loading, please wait a moment and retry."
            else:
                yield "❌ Model not loaded. Check backend logs."
            return

        prompt = self._build_prompt(aircraft, messages, context)
        print(f"[AeroMind Debug] Prompt length: {len(prompt)} chars")
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        # ── GGUF backend ─────────────────────────────────────────
        def _run_gguf():
            try:
                for chunk in self.llama(
                    prompt,
                    max_tokens=settings.MAX_NEW_TOKENS,
                    stream=True,
                    temperature=settings.TEMPERATURE,
                    top_p=settings.TOP_P,
                    stop=settings.STOP_TOKENS,
                ):
                    token = chunk["choices"][0]["text"]
                    loop.call_soon_threadsafe(queue.put_nowait, token)
            except Exception as e:
                loop.call_soon_threadsafe(
                    queue.put_nowait, f"\n[Generation error: {e}]"
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        # ── Transformers backend ──────────────────────────────────
        def _run_transformers():
            from transformers import TextIteratorStreamer
            import torch

            try:
                inputs = self.tokenizer(
                    prompt,
                    return_tensors="pt",
                    truncation=True,
                    max_length=settings.N_CTX - settings.MAX_NEW_TOKENS,
                ).to(self.model.device)

                streamer = TextIteratorStreamer(
                    self.tokenizer,
                    skip_prompt=True,
                    skip_special_tokens=True,
                )

                gen_kwargs = dict(
                    **inputs,
                    streamer=streamer,
                    max_new_tokens=settings.MAX_NEW_TOKENS,
                    temperature=settings.TEMPERATURE,
                    do_sample=False,
                    top_p=settings.TOP_P,
                    pad_token_id=self.tokenizer.eos_token_id,
                )

                gen_thread = threading.Thread(
                    target=self.model.generate, kwargs=gen_kwargs
                )
                gen_thread.start()

                accumulated = ""
                for token_text in streamer:
                    accumulated += token_text
                    
                    # Check for stop token
                    stop_hit = False
                    for stop in settings.STOP_TOKENS:
                        if stop in accumulated:
                            # We found a stop token! 
                            # Send only what was before the stop token
                            stop_hit = True
                            break
                    
                    if stop_hit:
                        break
                        
                    loop.call_soon_threadsafe(queue.put_nowait, token_text)

                gen_thread.join()

            except Exception as e:
                loop.call_soon_threadsafe(
                    queue.put_nowait, f"\n[Generation error: {e}]"
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        # Dispatch
        target_fn = _run_gguf if self.model_type == "gguf" else _run_transformers
        t = threading.Thread(target=target_fn, daemon=True)
        t.start()

        while True:
            token = await queue.get()
            if token is None:
                break
            yield token
