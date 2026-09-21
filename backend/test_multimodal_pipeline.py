"""
test_multimodal_pipeline.py
─────────────────────────────────────────────────────────────────
Verifies that text + visual image inputs are properly extracted,
encoded as base64, and delivered to the model with live agent DAG telemetry.
Streams tokens live to the console in real-time.
"""

import sys
import json
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import settings
from visual_rag_service import visual_rag_service
from agent_orchestrator import multi_agent_orchestrator
from model_service import ModelService


async def test_pipeline():
    print("\n==================================================")
    print("  Testing Local Multimodal Text + Image Pipeline  ")
    print("==================================================")

    model_svc = ModelService()
    await model_svc.load_model()
    print(f"✓ Model service loaded (Backend: {model_svc.model_type})")

    # 1. Verify ColPali page image rendering and base64 retrieval
    mig_path = Path(settings.PDF_DIR) / "mig21bis.pdf"
    if mig_path.exists():
        print("\n1. Verifying Page Image Base64 Extraction...")
        b64_img = visual_rag_service.get_page_image_base64("mig21bis", 17)
        if b64_img:
            print(f"✓ Extracted Base64 Image for Page 17 (Length: {len(b64_img)} chars)")
            assert len(b64_img) > 1000, "Base64 image is unexpectedly small."
        else:
            print("⚠ Rendering and caching Page 17 image...")
            visual_rag_service.render_and_cache_page_image(mig_path, "mig21bis", 17)
            b64_img = visual_rag_service.get_page_image_base64("mig21bis", 17)
            print(f"✓ Generated Base64 Image for Page 17 (Length: {len(b64_img) if b64_img else 0} chars)")

    # 2. Test Multi-Agent Stream with Visual + Math Query
    print("\n2. Simulating Multi-Agent Streaming Execution...")
    messages = [
        {
            "role": "user",
            "content": "Show cockpit emergency fuel pump switch sequence and calculate TAS for Mach 1.5 at 10000m",
        }
    ]

    events_received = []
    has_dag_plan = False
    has_agent_status = False
    has_visual_ref = False
    has_math_step = False
    has_eval_report = False
    has_page_ref = False

    print("\n┌── LIVE MULTI-AGENT STREAM ───────────────────────")

    async for event in multi_agent_orchestrator.execute_query_stream("mig21bis", messages, model_svc):
        events_received.append(event)

        if event.startswith("data: "):
            payload = event[6:].rstrip("\n")

            if payload.startswith("[DAG_PLAN:"):
                has_dag_plan = True
                try:
                    plan_data = json.loads(payload[10:-1])
                    print(f"\n🗺️ [DAG Plan Planned]: Intent: {plan_data.get('intent')} ({len(plan_data.get('nodes', []))} nodes)")
                except Exception:
                    pass
            elif payload.startswith("[AGENT_STATUS:"):
                has_agent_status = True
                try:
                    status_data = json.loads(payload[14:-1])
                    model_tag = f" ({status_data.get('model', '').split(':')[0]})" if status_data.get('model') else ""
                    print(f"\n⚡ [{status_data.get('title', 'Agent')}{model_tag}]: {status_data.get('action', '')}")
                except Exception:
                    pass
            elif payload.startswith("[VISUAL_REF:"):
                has_visual_ref = True
                try:
                    v_data = json.loads(payload[12:-1])
                    print(f"📐 [Visual Citation]: Page {v_data.get('page')} (Schematic: {v_data.get('is_schematic')})")
                except Exception:
                    pass
            elif payload.startswith("[AGENT_STEP:"):
                has_math_step = True
                try:
                    m_data = json.loads(payload[12:-1])
                    print(f"📐 [Avionics Math]: {m_data.get('summary', '')}")
                except Exception:
                    pass
            elif payload.startswith("[EVAL_REPORT:"):
                has_eval_report = True
            elif payload.startswith("[PAGE_REF:"):
                has_page_ref = True
            elif payload.startswith("[AGENT_THOUGHT:") or payload == "[DONE]":
                pass
            else:
                # Live token streaming directly to stdout
                raw_token = payload.replace("\\n", "\n")
                sys.stdout.write(raw_token)
                sys.stdout.flush()

    print("\n└───────────────────────────────────────────────────")

    print(f"\nTotal SSE events streamed: {len(events_received)}")
    print(f"  • [DAG_PLAN] Dynamic Task Graph: {has_dag_plan}")
    print(f"  • [AGENT_STATUS] DAG events: {has_agent_status}")
    print(f"  • [VISUAL_REF] ColPali schematics: {has_visual_ref}")
    print(f"  • [AGENT_STEP] Deterministic Math: {has_math_step}")
    print(f"  • [EVAL_REPORT] Quality Scorecard: {has_eval_report}")
    print(f"  • [PAGE_REF] Synchronized PDF Page: {has_page_ref}")

    assert has_agent_status, "Missing AGENT_STATUS event"
    assert has_visual_ref, "Missing VISUAL_REF event"
    assert has_math_step, "Missing AGENT_STEP event"
    assert has_eval_report, "Missing EVAL_REPORT event"
    assert has_page_ref, "Missing PAGE_REF event"

    print("\n==================================================")
    print("  ALL MULTIMODAL PIPELINE CHECKS PASSED! ✓        ")
    print("==================================================")


if __name__ == "__main__":
    asyncio.run(test_pipeline())
