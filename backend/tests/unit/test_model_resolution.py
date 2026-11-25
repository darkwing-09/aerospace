"""QW1 (fail-closed model resolution) and QW2 (single Ollama request per call)."""
import asyncio
import json

import httpx
import pytest

import model_service as ms
from config import settings


class _Recorder:
    def __init__(self, handler):
        self.requests = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)


@pytest.fixture
def patch_httpx(monkeypatch):
    def _install(handler):
        rec = _Recorder(handler)
        real = httpx.AsyncClient

        class _Client(real):
            def __init__(self, *a, **kw):
                kw["transport"] = httpx.MockTransport(rec)
                super().__init__(*a, **kw)

        monkeypatch.setattr(httpx, "AsyncClient", _Client)
        return rec
    return _install


def _loaded_service() -> ms.ModelService:
    svc = ms.ModelService()
    svc.is_loaded = True
    svc.model_type = "ollama"
    return svc


async def _collect(svc, **kw):
    return "".join([t async for t in svc.stream_response("doc", [{"role": "user", "content": "hi"}], **kw)])


def test_missing_model_fails_closed_without_fallback(patch_httpx, monkeypatch):
    monkeypatch.setitem(settings.AGENT_MODEL_MAP, "math", "nonexistent:1b")
    rec = patch_httpx(lambda req: httpx.Response(404, json={"error": "model 'nonexistent:1b' not found"}))

    out = asyncio.run(_collect(_loaded_service(), capability="math"))

    assert "nonexistent:1b" in out and "No fallback model was used" in out
    assert len(rec.requests) == 1, "exactly one request; no retry with a substitute model"
    sent = json.loads(rec.requests[0].content)
    assert sent["model"] == "nonexistent:1b"


def test_success_streams_with_single_request_and_configured_ctx(patch_httpx):
    lines = "\n".join(json.dumps({"response": t}) for t in ["Hel", "lo"]) + "\n"
    rec = patch_httpx(lambda req: httpx.Response(200, content=lines.encode()))

    out = asyncio.run(_collect(_loaded_service(), capability="synthesis"))

    assert out == "Hello"
    assert len(rec.requests) == 1, "QW2: no duplicate non-streamed generation"
    assert json.loads(rec.requests[0].content)["options"]["num_ctx"] == settings.N_CTX


def test_health_reports_missing_models(patch_httpx, monkeypatch):
    monkeypatch.setitem(settings.AGENT_MODEL_MAP, "math", "nonexistent:1b")
    installed = sorted(set(settings.AGENT_MODEL_MAP.values()) - {"nonexistent:1b"})
    patch_httpx(lambda req: httpx.Response(200, json={"models": [{"name": n} for n in installed]}))

    report = asyncio.run(ms.ModelService().check_configured_models())

    assert report["missing"] == ["nonexistent:1b"]
    assert report["error"] is None
