import json

from agent.llm import PURPOSE_ANSWER
from agent.nodes.answer import answer_node


class _JsonChat:
    def complete(self, purpose: str, system: str, user: str) -> str:
        assert purpose == PURPOSE_ANSWER
        return json.dumps(
            {
                "answer": "SQLite exact search",
                "grounding": "known_from_documents",
                "citations": [],
            }
        )


def test_answer_keeps_exact_cosine_from_memory() -> None:
    state = {
        "user_message": "What architecture did I decide for the retrieval system?",
        "task": "retrieval architecture",
        "memories": [
            {
                "id": "decision_a11ce0000001",
                "snippet": "Use exact cosine search over float32 vectors stored in SQLite.",
            }
        ],
        "chunks": [],
        "trace": [],
    }
    result = answer_node(_JsonChat())(state)
    assert "exact cosine" in result["answer"]
    assert "SQLite" in result["answer"]
    assert result["grounding"] == "known_from_memory"
    assert result["citations"] == ["decision_a11ce0000001"]


def test_answer_leaves_an_unrelated_fact_alone() -> None:
    state = {
        "user_message": "How much RAM does the Harbor workstation have?",
        "task": "Harbor RAM",
        "memories": [
            {
                "id": "fact_8ba000000001",
                "snippet": "The Harbor workstation has 8 GB of RAM and no discrete GPU.",
            },
            {
                "id": "decision_a11ce0000001",
                "snippet": "Use exact cosine search over float32 vectors stored in SQLite.",
            },
        ],
        "chunks": [],
        "trace": [],
    }

    class _RamChat:
        def complete(self, purpose: str, system: str, user: str) -> str:
            return json.dumps(
                {
                    "answer": "The Harbor workstation has 8 GB of RAM.",
                    "grounding": "known_from_memory",
                    "citations": ["fact_8ba000000001"],
                }
            )

    result = answer_node(_RamChat())(state)
    assert result["answer"] == "The Harbor workstation has 8 GB of RAM."
    assert "cosine" not in result["answer"].casefold()


def test_answer_reads_a_truncated_json_object() -> None:
    state = {
        "user_message": "How much RAM does the Harbor workstation have?",
        "task": "Harbor RAM",
        "memories": [
            {
                "id": "fact_8ba000000001",
                "snippet": "The Harbor workstation has 8 GB of RAM and no discrete GPU.",
            }
        ],
        "chunks": [],
        "trace": [],
    }

    class _CutOff:
        def complete(self, purpose: str, system: str, user: str) -> str:
            return (
                '{"answer": "8 GB", "grounding": "known_from_memory", '
                '"citations": ["fact_8ba000000001"'
            )

    result = answer_node(_CutOff())(state)
    assert result["answer"] == "8 GB"
    assert result["grounding"] == "known_from_memory"
    assert result["citations"] == ["fact_8ba000000001"]
