"""QW3 / pitfall §11.16: uploads can't escape their directories; size and archive limits hold."""
import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from config import settings

client = TestClient(main.app)  # no lifespan: no model load, no indexing at startup

TRAVERSAL_NAMES = ["../../x.pdf", "..%2f..%2fx.pdf", "/etc/passwd", "a/../../b.pdf", "..\\..\\x.pdf", ".hidden.pdf"]


def _all_files_outside(roots):
    tmp_root = Path(settings.DATA_DIR).parent
    found = []
    for p in tmp_root.rglob("*"):
        if p.is_file() and not any(Path(r).resolve() in p.resolve().parents for r in roots):
            found.append(p)
    return found


def _upload(url, name, data=b"%PDF-1.4 fake", extra=None):
    return client.post(url, files={"file": (name, data, "application/octet-stream")}, data=extra or {})


@pytest.mark.parametrize("name", TRAVERSAL_NAMES)
@pytest.mark.parametrize("url", ["/api/documents/upload", "/api/documents/session-upload"])
def test_traversal_filenames_rejected(url, name):
    before = set(Path(settings.DATA_DIR).parent.rglob("*"))
    res = _upload(url, name)
    assert res.status_code == 400, res.text
    after = set(Path(settings.DATA_DIR).parent.rglob("*"))
    assert after == before, f"files written for rejected upload: {after - before}"
    assert not Path("/etc/x.pdf").exists()


@pytest.mark.parametrize("sess", ["../../etc", "a/b", "..", "x" * 200])
def test_bad_session_id_rejected(sess):
    res = _upload("/api/documents/session-upload", "ok.txt", b"hello", {"session_id": sess})
    assert res.status_code == 400, res.text


def test_bad_aircraft_id_rejected():
    res = _upload("/api/pdf/upload/..", "x.pdf")
    assert res.status_code in (400, 404)


def test_oversized_upload_rejected(monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    res = _upload("/api/documents/session-upload", "big.txt", b"0" * (2 * 1024 * 1024))
    assert res.status_code == 413


def _zip_bytes(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_zip_bomb_rejected(monkeypatch):
    # Limit lowered to keep the fixture small; same code path as the 500 MB default.
    monkeypatch.setattr(settings, "ZIP_MAX_UNCOMPRESSED_MB", 1)
    bomb = _zip_bytes({"zeros.txt": b"\0" * (20 * 1024 * 1024)})
    assert len(bomb) < 100 * 1024
    res = _upload("/api/documents/session-upload", "bomb.zip", bomb)
    assert res.status_code == 400 and "limit" in res.text


def test_too_many_members_rejected(monkeypatch):
    monkeypatch.setattr(settings, "ZIP_MAX_MEMBERS", 3)
    res = _upload("/api/documents/session-upload", "many.zip", _zip_bytes({f"f{i}.txt": b"x" for i in range(5)}))
    assert res.status_code == 400


def test_nested_zip_rejected():
    inner = _zip_bytes({"a.txt": b"hi"})
    res = _upload("/api/documents/session-upload", "nested.zip", _zip_bytes({"inner.zip": inner}))
    assert res.status_code == 400 and "Nested" in res.text


def test_zip_member_traversal_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        info = zipfile.ZipInfo("../../escape.txt")
        zf.writestr(info, b"pwned")
    res = _upload("/api/documents/session-upload", "slip.zip", buf.getvalue())
    assert res.status_code == 400
    assert not (Path(settings.DATA_DIR).parent / "escape.txt").exists()
