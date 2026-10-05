"""Storage failures. Codes match the MCP envelope, plus MALFORMED for bad files."""


class StorageError(Exception):
    """A refused or failed vault operation. Persistent state is left unchanged."""

    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}
