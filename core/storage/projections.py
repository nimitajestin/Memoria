"""Generated Markdown views. They are not parsed back into records."""

from __future__ import annotations

from core.schemas.memory import DecisionRecord, StatusRecord


def render_status(record: StatusRecord) -> str:
    lines = [
        "# Status",
        "",
        f"- id: {record.id}",
        f"- status: {record.status}",
        f"- revision: {record.revision}",
        f"- updated_at: {record.updated_at}",
        f"- phase: {record.phase}",
        "",
        record.summary,
        "",
        "## Blockers",
        "",
    ]
    if record.blockers:
        lines.extend(f"- {item}" for item in record.blockers)
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def render_decisions(records: list[DecisionRecord]) -> str:
    lines = ["# Decisions", ""]
    if not records:
        lines.extend(["No decisions recorded.", ""])
        return "\n".join(lines)
    ordered = sorted(records, key=lambda item: (item.updated_at, item.id), reverse=True)
    for record in ordered:
        lines.extend(
            [
                f"## {record.id}",
                "",
                f"- status: {record.status}",
                f"- revision: {record.revision}",
                f"- updated_at: {record.updated_at}",
                f"- topic: {record.topic}",
                "",
                record.decision,
                "",
                "Reason:",
                "",
                record.reason,
                "",
            ]
        )
    return "\n".join(lines)
