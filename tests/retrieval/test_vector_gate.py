from pathlib import Path

from evaluation.experiments.vector_gate import LATENCY_BAR_MS, render_gate_report, run_exact_cosine_gate


def test_exact_cosine_meets_the_latency_bar(tmp_path: Path) -> None:
    result = run_exact_cosine_gate(tmp_path)
    assert result["keep_exact"] is True
    assert result["selected"] == "sqlite_float32_exact_cosine"
    assert result["median_latency_ms"] < LATENCY_BAR_MS
    assert result["recall_at_5"] == 1.0
    report = render_gate_report(result)
    assert "sqlite_float32_exact_cosine" in report
