from pathlib import Path

from evaluation.experiments.compare import render_comparison, run_comparison, write_report


def test_offline_comparison_scores_a_b_c(tmp_path: Path) -> None:
    result = run_comparison(tmp_path, question_ids=["q01", "q07", "q18"])
    systems = {row.system for row in result["scores"]}
    assert systems == {"A", "B", "C"}
    assert result["prompts"]["answer.md"]
    b_routes = [row for row in result["scores"] if row.system == "B"]
    assert all(row.route_ok for row in b_routes)
    markdown = render_comparison(result)
    assert "Task completion" in markdown
    path = write_report(result, tmp_path / "comparison.md")
    assert path.read_text(encoding="utf-8").startswith("# Harbor")
