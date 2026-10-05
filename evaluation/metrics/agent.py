"""Score one Harbor item from a turn result."""

from __future__ import annotations

from dataclasses import dataclass

from agent.state.schema import TurnResult
from evaluation.datasets.controlled.load import Question


@dataclass
class ItemScore:
    item_id: str
    system: str
    task_completion: bool
    route_ok: bool | None
    grounded: bool
    citation_ok: bool
    error: bool
    tool_success: float


def score_item(item: Question, result: TurnResult, system: str) -> ItemScore:
    answer = result.answer.casefold()
    required = all(point.casefold() in answer for point in item.required_points)
    forbidden = any(point.casefold() in answer for point in item.forbidden_points)
    retrieved = {str(row.get("id")) for row in result.memories if row.get("id")}
    retrieved |= {str(row.get("chunk_id")) for row in result.chunks if row.get("chunk_id")}
    citation_ok = set(result.citations).issubset(retrieved)
    grounded = result.grounding in item.acceptable_grounding and citation_ok
    route_ok: bool | None
    if system == "A":
        route_ok = None
    else:
        route_ok = result.route == item.expects_route
    tools = result.tool_ok
    tool_success = (sum(1 for item_ok in tools if item_ok) / len(tools)) if tools else 1.0
    return ItemScore(
        item_id=item.id,
        system=system,
        task_completion=required and not forbidden,
        route_ok=route_ok,
        grounded=grounded,
        citation_ok=citation_ok,
        error=bool(result.error) or answer.startswith("mcp-unavailable"),
        tool_success=tool_success,
    )
