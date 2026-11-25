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

        if settings.USE_OLLAMA:
            self._load_ollama()
        elif settings.USE_LLAMA_CPP:
            self._load_gguf()
        else:
            self._load_transformers()

        self.is_loaded = True
        print(f"[AeroMind] ✓ Model loaded. Backend: {self.model_type}")

    def _load_ollama(self):
        """Ollama requires no local loading, just a health check."""
        import httpx
        try:
            res = httpx.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=5.0)
            if res.status_code == 200:
                self.model_type = "ollama"
                print(f"[AeroMind] Connected to Ollama using model: {settings.OLLAMA_MODEL}")
            else:
                raise Exception("Ollama returned non-200 status")
        except Exception as e:
            raise Exception(f"Failed to connect to Ollama. Is it running? {e}")

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
        Builds a grounded, high-precision technical response prompt.
        Adapts dynamically whether the document is a registered airframe or arbitrary technical document/syllabus.
        """
        raw_name = aircraft.replace(".pdf", "").replace(".PDF", "").replace("_", " ").replace("-", " ")
        is_fighter = any(f in aircraft.lower() for f in ["mig21", "mig-21", "su27", "f16", "f18", "fighter", "interceptor"])

        # Limit context depth
        context_messages = messages[-(settings.MAX_CONTEXT_TURNS + 1) :]
        prior_turns = context_messages[:-1]
        current_message = context_messages[-1] if context_messages else None

        history_lines = []
        for msg in prior_turns:
            role = msg.get("role", "")
            content = msg.get("content", "").strip()
            if role == "user":
                history_lines.append(f"User: {content}")
            elif role == "assistant":
                truncated = content[:400] + "…" if len(content) > 400 else content
                history_lines.append(f"Assistant: {truncated}")

        context_block = ""
        if history_lines:
            context_block = "PRIOR CONVERSATION HISTORY:\n" + "\n".join(history_lines) + "\n\n"

        query = current_message.get("content", "") if current_message else ""

        if is_fighter:
            system_directives = (
                "You are Aeromind Flight Systems Intelligence — an authoritative aviation systems specialist.\n"
                "Deliver clear operational guidance grounded strictly in the flight manual and telemetry.\n"
                "1. Deliver actionable instructions with exact switch names, panel locations, and gauge indicators.\n"
                "2. Structure procedures in clear numbered steps.\n"
                "3. Include prominent [WARNING] or [CAUTION] directives if safety risks or limits are involved.\n"
                "4. Cite the relevant manual page or schematic diagram.\n"
                "5. NO-GUESSING RULE: Every number (speed, altitude, angle, RPM, time, quantity) and every procedure step MUST appear in the DOCUMENT CONTEXT below. Copy numbers with their original units. Never convert units or invent values. If the context does not contain the requested information, say exactly that and name the pages you checked instead of guessing."
            )
            doc_header = f"Aircraft: {raw_name.upper()}"
        else:
            system_directives = (
                "You are Aeromind — an intelligent technical document and manual assistant.\n"
                "Your objective is to provide accurate, comprehensive, and thoroughly grounded answers based directly on the provided document text, figures, and content.\n\n"
                "RESPONSE REQUIREMENTS:\n"
                "1. Answer the user's question directly and thoroughly using the exact terms, concepts, definitions, topics, or steps from the document.\n"
                "2. Structure your response with clean headings, bullet points, and numbered lists where appropriate.\n"
                "3. If the query asks for a syllabus, list of topics, steps, or definitions, provide the complete relevant outline from the document.\n"
                "4. Cite the document page numbers where the information is found.\n"
                "5. Only use [WARNING] or [CAUTION] if the document explicitly contains hazards or safety rules.\n"
                "6. Ground all statements in the provided context without making false assumptions.\n"
                "7. NO-GUESSING RULE: Every number (speed, altitude, angle, RPM, time, quantity) and every procedure step MUST appear in the DOCUMENT CONTEXT below. Copy numbers with their original units. Never convert units or invent values. If the context does not contain the requested information, say exactly that and name the pages you checked instead of guessing."
            )
            doc_header = f"Active Document: {raw_name}"

        context_section = ""
        if context:
            context_section = f"DOCUMENT CONTEXT & EXTRACTED PAGES:\n{context}\n\n"

        return (
            f"### System:\n{system_directives}\n\n"
            f"### Instruction:\n"
            f"{doc_header}\n"
            f"{context_section}"
            f"{context_block}"
            f"User Query: {query}\n\n"
            f"### Response:\n"
        )

    # ─────────────────────────────────────────────────────────────
    # MODEL AVAILABILITY (QW1)
    # ─────────────────────────────────────────────────────────────
    async def check_configured_models(self) -> Dict:
        """Compare every configured role model with what Ollama actually has.

        Why: a configured-but-missing model used to be swapped silently for the
        default one, so the UI named a model that never ran. Surfacing the gap
        in /api/health makes the mismatch visible before a query hits it.
        """
        import httpx

        configured = dict(settings.AGENT_MODEL_MAP)
        result = {"configured": configured, "installed": None, "missing": None, "error": None}
        if not settings.USE_OLLAMA:
            result["error"] = "Ollama backend disabled"
            return result
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{settings.OLLAMA_HOST}/api/tags")
            res.raise_for_status()
            installed = sorted(m.get("name", "") for m in res.json().get("models", []))
        except Exception as e:  # report, don't guess
            result["error"] = f"Could not list Ollama models: {e}"
            return result
        installed_set = set(installed)
        # Ollama treats "name" and "name:latest" as the same model.
        def _present(tag: str) -> bool:
            return tag in installed_set or (":" not in tag and f"{tag}:latest" in installed_set)
        result["installed"] = installed
        result["missing"] = sorted({tag for tag in configured.values() if not _present(tag)})
        return result

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
        self,
        aircraft: str,
        messages: List[Dict],
        context: str = "",
        images: Optional[List[str]] = None,
        model_name: Optional[str] = None,
        capability: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Async generator that yields tokens one-by-one.
        Dispatches to Ollama, GGUF, or transformers backend based on config.
        Supports multimodal visual inputs (base64 images) for ColPali VLM inference.
        """
        if not self.is_loaded:
            if self.is_loading:
                yield "⏳ Model is still loading, please wait a moment and retry."
            else:
                yield "❌ Model not loaded. Check backend logs."
            return

        # Resolve model via explicit map override, ModelRouter (ADR-0005), or model_name
        if capability:
            if capability in settings.AGENT_MODEL_MAP:
                resolved_model = settings.AGENT_MODEL_MAP[capability]
            else:
                try:
                    from router.router import router
                    resolved_model = router.get_model_tag(capability)
                except Exception:
                    resolved_model = settings.AGENT_MODEL_MAP.get("synthesis", settings.OLLAMA_MODEL)
        elif model_name:
            resolved_model = model_name
        else:
            try:
                from router.router import router
                resolved_model = router.get_model_tag("drafting")
            except Exception:
                resolved_model = settings.AGENT_MODEL_MAP.get("synthesis", settings.OLLAMA_MODEL)

        prompt = self._build_prompt(aircraft, messages, context)
        print(f"[AeroMind Debug] Model: {resolved_model} (Capability: {capability}), Prompt length: {len(prompt)} chars, Images attached: {len(images) if images else 0}")
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

        # ── Ollama backend (with Multimodal Image Support) ────────
        async def _run_ollama_async():
            import httpx
            import json
            
            selected_model = resolved_model or settings.OLLAMA_MODEL
            supports_vision = any(v in selected_model.lower() for v in ["gemma4", "llava", "vision", "vl", "moondream", "bakllava", "minicpm"])
            is_multimodal = bool(images and supports_vision)
            print(f"[AeroMind Debug] Starting Ollama stream for {selected_model} (Multimodal: {is_multimodal})...")
            
            timeout = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
            
            generate_payload = {
                "model": selected_model,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": settings.TEMPERATURE,
                    "top_p": settings.TOP_P,
                    "stop": settings.STOP_TOKENS,
                    "num_predict": settings.MAX_NEW_TOKENS,
                    "num_thread": os.cpu_count() or 8,
                    # Was hard-coded to 2048, silently truncating prompts built
                    # for N_CTX (8192 in .env). Use the configured value.
                    "num_ctx": settings.N_CTX,
                },
            }
            if is_multimodal:
                generate_payload["images"] = images
            
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    # One streamed request per call. (Previously a non-streamed
                    # POST ran a full generation first just to probe for 404,
                    # doubling latency on every call — QW2.)
                    async with client.stream(
                        "POST",
                        f"{settings.OLLAMA_HOST}/api/generate",
                        json=generate_payload,
                    ) as response:
                        if response.status_code == 404:
                            # Fail closed (QW1, plan pitfall §11.5): never answer
                            # with a different model than the one requested.
                            await response.aread()
                            print(f"[AeroMind] Model '{selected_model}' is not installed in Ollama; refusing to substitute another model.")
                            await queue.put(
                                f"\n[Generation error: model '{selected_model}' is not installed in Ollama (HTTP 404). "
                                f"No fallback model was used. Install it with `ollama pull {selected_model}` or change the configured model.]"
                            )
                            return
                        if response.status_code != 200:
                            error_text = await response.aread()
                            print(f"[AeroMind Debug] Ollama error {response.status_code}: {error_text.decode()}")
                            await queue.put(f"\n[Generation error: Ollama returned {response.status_code}]")
                            return

                        print(f"[AeroMind Debug] Ollama connected, streaming tokens...")
                        token_count = 0
                        async for line in response.aiter_lines():
                            if line:
                                try:
                                    data = json.loads(line)
                                    if "response" in data and data["response"]:
                                        token_count += 1
                                        await queue.put(data["response"])
                                except json.JSONDecodeError:
                                    pass
                        print(f"[AeroMind Debug] Ollama finished. Tokens: {token_count}")
                        
            except httpx.ReadTimeout:
                print(f"[AeroMind Debug] Ollama ReadTimeout after 300s")
                await queue.put("\n[Generation error: Model timeout — CPU inference too slow for this prompt size.]")
            except httpx.ConnectError as e:
                print(f"[AeroMind Debug] Ollama ConnectError: {e}")
                await queue.put(f"\n[Generation error: Cannot connect to Ollama at 127.0.0.1:11434]")
            except Exception as e:
                import traceback
                print(f"[AeroMind Debug] Ollama Exception:\n{traceback.format_exc()}")
                await queue.put(f"\n[Generation error: {str(e) or type(e).__name__}]")
            finally:
                await queue.put(None)

        # Dispatch
        if self.model_type == "ollama":
            # Run async loop for ollama
            loop.create_task(_run_ollama_async())
        else:
            target_fn = _run_gguf if self.model_type == "gguf" else _run_transformers
            t = threading.Thread(target=target_fn, daemon=True)
            t.start()

        while True:
            token = await queue.get()
            if token is None:
                break
            yield token
