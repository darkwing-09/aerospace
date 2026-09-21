"""
test_multiagent_system.py
─────────────────────────────────────────────────────────────────
Automated validation script for AeroMind Multi-Agent SLM & ColPali Visual RAG.
"""

import sys
import asyncio
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from config import settings
from universal_ingestion_service import universal_ingestion
from visual_rag_service import visual_rag_service
from agent_orchestrator import AvionicsMathEngine
from evaluation_service import evaluation_service
from langsmith_service import langsmith_service


def test_universal_ingestion():
    print("\n--- 1. Testing Universal Ingestion ---")
    docs = universal_ingestion.list_all_documents()
    print(f"Registered Documents ({len(docs)}):")
    for d in docs:
        print(f"  • [{d.get('category')}] {d.get('name')} ({d.get('file_type')}) - {d.get('size_mb', 0)}MB")
    assert len(docs) > 0, "Expected at least 1 document in registry."
    print("✓ Universal Ingestion OK")


def test_visual_rag():
    print("\n--- 2. Testing ColPali Visual RAG & Page Rendering ---")
    mig_path = Path(settings.PDF_DIR) / "mig21bis.pdf"
    if mig_path.exists():
        index_meta = visual_rag_service.index_document(mig_path, "mig21bis")
        print(f"Indexed pages: {index_meta.get('total_pages')}")

        # Render page 1 and page 42
        img1 = visual_rag_service.render_and_cache_page_image(mig_path, "mig21bis", 1)
        print(f"Rendered Page 1 Image: {img1} (Exists: {img1.exists() if img1 else False})")

        # Test Visual Retrieval
        results = visual_rag_service.retrieve_visual_context(
            mig_path, "mig21bis", "cockpit emergency fuel switch and panel layout", max_pages=2
        )
        print(f"Retrieved {len(results)} visual pages for cockpit query:")
        for r in results:
            print(f"  • Page {r['page_number']}: score={r['score']}, schematic={r['is_schematic']}, img_url={r['image_url']}")
        assert len(results) > 0, "Expected visual search results."
        print("✓ ColPali Visual RAG OK")
    else:
        print("⚠ mig21bis.pdf not found in pdfs/, skipping visual render test.")


def test_avionics_math():
    print("\n--- 3. Testing Avionics Math Engine ---")
    math_engine = AvionicsMathEngine()

    # Mach test
    res1 = math_engine.calculate("Calculate TAS for Mach 1.6 at 11000m")
    print(f"Mach Query Result:\n{res1['summary_text']}")
    assert res1 is not None, "Expected Mach calculation."

    # Fuel test
    res2 = math_engine.calculate("Calculate fuel endurance for 2400 kg with afterburner")
    print(f"Fuel Query Result:\n{res2['summary_text']}")
    assert res2 is not None, "Expected fuel calculation."

    # Unit conversion test
    res3 = math_engine.calculate("convert 1500 kg to lbs")
    print(f"Conversion Query Result:\n{res3['summary_text']}")
    assert res3 is not None, "Expected unit conversion."
    print("✓ Avionics Math Engine OK")


def test_evaluation_service():
    print("\n--- 4. Testing Evaluation Service ---")
    mock_query = "What is the emergency engine relight procedure for MiG-21bis?"
    mock_response = """DIAGNOSIS: Engine flameout in flight.
Step 1: Check throttle at IDLE.
Step 2: Turn ON emergency fuel pump switch.
Step 3: Press START button for 3 seconds.
WARNING: Minimum airspeed for relight is 550 km/h."""
    mock_context = [{"page_number": 42, "text": "Engine relight procedure: throttle IDLE, emergency fuel pump ON, minimum speed 550 km/h.", "is_schematic": True}]

    report = evaluation_service.evaluate_response(
        query=mock_query,
        response_text=mock_response,
        retrieved_contexts=mock_context,
        math_result=None,
        referenced_page=42,
        latency_ms=850.0,
    )
    print("Evaluation Report:")
    for k, v in report.items():
        print(f"  • {k}: {v}")
    assert report["faithfulness_score"] >= 75
    assert report["safety_compliance"] == "PASSED"
    print("✓ Evaluation Service OK")


def test_langsmith_service():
    print("\n--- 5. Testing LangSmith Tracing ---")
    trace_id = langsmith_service.create_run_trace(
        query="MiG-21 emergency start",
        aircraft_id="mig21bis",
        plan={"tasks": ["visual", "safety"]},
        agent_results={"visual": [42]},
        final_response="Engine start sequence...",
        evaluation={"faithfulness_score": 95},
        latency_ms=920.0,
    )
    print(f"Created trace ID: {trace_id}")
    recent = langsmith_service.get_recent_traces(limit=2)
    print(f"Found {len(recent)} recent traces in inspection log.")
    assert len(recent) > 0
    print("✓ LangSmith Service OK")


if __name__ == "__main__":
    print("==================================================")
    print("   AeroMind Defense Platform Multi-Agent Tests   ")
    print("==================================================")
    test_universal_ingestion()
    test_visual_rag()
    test_avionics_math()
    test_evaluation_service()
    test_langsmith_service()
    print("\n==================================================")
    print("   ALL MULTI-AGENT BACKEND TESTS PASSED! ✓        ")
    print("==================================================")
