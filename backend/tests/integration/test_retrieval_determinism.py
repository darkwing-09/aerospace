import json
import subprocess
import sys
from pathlib import Path


def test_deterministic_vectors_across_processes():
    """Verify that fallback multi-vectors and query vectors are identical across 3 separate Python processes (QW6 / §11.8)."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    venv_site = backend_dir / "venv" / "lib" / "python3.13" / "site-packages"

    script = f"""
import sys
from pathlib import Path

sys.path.insert(0, r"{str(venv_site)}")
sys.path.insert(0, r"{str(backend_dir)}")

from colpali_retrieval_service import colpali_retrieval_service
import json

q_vec = colpali_retrieval_service._generate_fallback_query_vector("cockpit layout schematic hydraulic")
doc_vec = colpali_retrieval_service._generate_fallback_multivector("MiG-21 hydraulic system emergency relight", is_schematic=True, is_diagram=False, seed_id=42)

print(json.dumps({{
    "q_vec_sample": q_vec[0][:10],
    "doc_vec_sample": doc_vec[0][:10],
}}))
"""
    results = []
    for _ in range(3):
        res = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
        )
        # Parse last line which contains the JSON output
        last_line = res.stdout.strip().splitlines()[-1]
        results.append(json.loads(last_line))

    assert results[0] == results[1] == results[2], f"Vectors differ across processes: {results}"
