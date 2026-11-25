"""Test isolation for AeroMind backend tests.

Why: the app's settings default every data directory to the git-tracked
backend/data_repository/. Tests must never write there (doc/06-engineering/safety-rules.md),
so before any app module is imported we point every path setting at a
throwaway directory via environment variables (pydantic-settings reads them).
"""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="aeromind-tests-"))
for _key, _sub in {
    "DATA_DIR": "data",
    "UPLOADS_DIR": "data/uploads",
    "PAGE_IMAGES_DIR": "data/page_images",
    "TRACES_DIR": "data/traces",
    "QDRANT_PATH": "data/qdrant_db",
    "PDF_DIR": "pdfs",
}.items():
    os.environ[_key] = str(_TMP / _sub)

# Never reach cloud services from tests.
os.environ.pop("LANGCHAIN_API_KEY", None)
os.environ.pop("LANGSMITH_API_KEY", None)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
# Deterministic hardware tier for tests unless a test overrides it.
os.environ.setdefault("AEROMIND_HW_TIER", "cpu_lite")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure backend/venv site-packages is discoverable by system python3 tests
_venv_site = Path(__file__).resolve().parent.parent / "venv" / "lib" / "python3.13" / "site-packages"
if _venv_site.exists() and str(_venv_site) not in sys.path:
    sys.path.insert(1, str(_venv_site))


def pytest_addoption(parser):
    """Add custom CLI options for AeroMind test suite."""
    parser.addoption(
        "--tier",
        action="store",
        default="cpu_lite",
        help="Hardware tier to test (default: cpu_lite)",
    )


import pytest

@pytest.fixture
def hardware_tier(request):
    """Returns the hardware tier specified via --tier or environment."""
    tier = request.config.getoption("--tier", default=None) or os.environ.get("AEROMIND_HW_TIER", "cpu_lite")
    os.environ["AEROMIND_HW_TIER"] = tier
    return tier

