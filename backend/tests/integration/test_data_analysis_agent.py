"""
Integration tests for Data Analysis Agent (Task 1.8 / PLAN §7.2, §11.7).
Verifies:
1. Spreadsheet query returns the exact number and cites the row range.
2. Ground truth spreadsheet Q/A pairs from fixtures match precisely.
3. render_chart outputs compliant visual chart specifications.
4. End-to-end graph integration: verified tabular citations PASS the Critic.
"""

from pathlib import Path
import pytest

from agents.data_analysis_agent import DataAnalysisAgent, render_chart
from orchestration.graph import run_task

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
MESSY_XLSX = FIXTURES_DIR / "messy_avionics_data.xlsx"


def test_spreadsheet_fuel_burn_query_cites_row_range():
    """Query on Leg 1 taxi fuel burn returns 120 kg and cites row 1."""
    agent = DataAnalysisAgent()
    res = agent.query_table(
        query="How much fuel was burned during taxi in Leg 1?",
        file_path=MESSY_XLSX,
        workspace_id="ws_avionics",
    )

    assert res["succeeded"] is True
    assert "120 kg" in res["answer"]
    assert "rows=" in res["citation"]
    assert len(res["evidence_refs"]) > 0
    ref = res["evidence_refs"][0]
    assert ref["tag"] == "observed"
    assert ref["confidence"] == 1.0


def test_spreadsheet_qa_pairs_ground_truth():
    """Tests the remaining ground-truth spreadsheet questions."""
    agent = DataAnalysisAgent()

    # Q14: What was the altitude for Leg 2 climb? -> 5000 m
    res_q14 = agent.query_table(
        query="What was the altitude for Leg 2 climb?",
        file_path=MESSY_XLSX,
    )
    assert res_q14["succeeded"] is True
    assert "5000 m" in res_q14["answer"]

    # Q16: What was the cruise speed during Leg 3? -> Mach 0.85
    res_q16 = agent.query_table(
        query="What was the cruise speed during Leg 3?",
        file_path=MESSY_XLSX,
    )
    assert res_q16["succeeded"] is True
    assert "Mach 0.85" in res_q16["answer"]

    # Q18: What was the touchdown speed during Leg 5 landing? -> 280 km/h
    res_q18 = agent.query_table(
        query="What was the touchdown speed during Leg 5 landing?",
        file_path=MESSY_XLSX,
    )
    assert res_q18["succeeded"] is True
    assert "280 km/h" in res_q18["answer"]


def test_render_chart_specification():
    """Verifies chart generator creates valid structured specification."""
    chart = render_chart(
        chart_type="bar",
        title="Fuel Burn Profile",
        labels=["Taxi", "Climb", "Cruise", "Descent", "Landing"],
        values=[120.0, 450.0, 800.0, 150.0, 80.0],
        x_axis="Flight Phase",
        y_axis="Fuel (kg)",
    )

    assert chart["chart_type"] == "bar"
    assert len(chart["labels"]) == 5
    assert chart["datasets"][0]["data"] == [120.0, 450.0, 800.0, 150.0, 80.0]
    assert chart["options"]["responsive"] is True


def test_graph_data_analysis_passes_critic():
    """Graph execution on spreadsheet question cites rows and PASSes the Critic."""
    state = run_task(
        task="How much fuel was burned during taxi in Leg 1 from the flight leg spreadsheet?",
        attachments=[str(MESSY_XLSX)],
    )

    assert state["task_type"] == "data_analysis"
    assert len(state["evidence"]) > 0
    assert state["evaluation"] is not None
    assert state["evaluation"]["verdict"] == "PASS"
    assert "120 kg" in state["result"]
    assert "rows=" in state["result"]

