"""Shared fixtures and mocks for ASCO tests."""


class MockLLMClient:
    """Mock LLM client returning sequential responses or raising exceptions."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self.responses = list(responses)
        self.call_count = 0

    def complete(self, prompt: str, system_prompt: str) -> str:
        self.call_count += 1
        if not self.responses:
            raise RuntimeError("No more mocked responses available.")
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp
