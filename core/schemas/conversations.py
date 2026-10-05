"""Normalized conversation transcripts. These are not memory records."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, model_validator

from core.safety import PROJECT_ID_RE
from core.schemas.memory import MemoryModel, _timestamp

MAX_TURNS = 200
MAX_TURN_CHARS = 16000


class Turn(MemoryModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1, max_length=MAX_TURN_CHARS)
    timestamp: str | None = None

    @model_validator(mode="after")
    def check_time(self) -> Turn:
        if self.timestamp is not None:
            self.timestamp = _timestamp(self.timestamp)
        return self


class ConversationFile(MemoryModel):
    id: str
    project_id: str
    source: Literal["app", "import"]
    origin_format: Literal["json", "markdown", "txt"]
    created_at: str
    title: str = Field(min_length=1, max_length=200)
    turns: list[Turn] = Field(min_length=1, max_length=MAX_TURNS)

    @model_validator(mode="after")
    def check(self) -> ConversationFile:
        if re.fullmatch(r"^conv_[0-9a-f]{12}$", self.id) is None:
            raise ValueError("invalid conversation id")
        if PROJECT_ID_RE.fullmatch(self.project_id) is None:
            raise ValueError("invalid project id")
        self.created_at = _timestamp(self.created_at)
        return self
