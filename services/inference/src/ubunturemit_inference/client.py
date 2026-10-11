"""VllmChatClient -- docs/design/inference.md §3, §4.

Implements ubunturemit_asco.LLMClient over vLLM's OpenAI-compatible chat endpoint, with
the reply constrained to the agent's JSON Schema. It returns the model's text or raises;
it never repairs, trims or defaults a reply -- the agents parse and validate it.
"""

from collections.abc import Mapping
from typing import Any

import httpx
from ubunturemit_asco import InferenceTimeoutError

CHAT_COMPLETIONS_PATH = "/v1/chat/completions"


class InferenceResponseError(RuntimeError):
    """The server answered, or failed to, with something that is not a usable reply.

    The agents treat this as malformed output: re-ask once, then escalate.
    """


class VllmChatClient:
    """One client per agent, bound to that agent's schema at construction."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        response_schema: Mapping[str, Any],
        schema_name: str,
        timeout_s: float,
        seed: int,
        max_tokens: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not base_url.strip() or not model.strip() or not schema_name.strip():
            raise ValueError("base_url, model and schema_name are all required.")
        if not response_schema:
            raise ValueError("A client without a response schema would decode unconstrained.")
        if timeout_s <= 0 or max_tokens <= 0:
            raise ValueError("timeout_s and max_tokens must be positive.")
        self.base_url = base_url
        self.model = model
        self.response_schema = dict(response_schema)
        self.schema_name = schema_name
        self.timeout_s = timeout_s
        self.seed = seed
        self.max_tokens = max_tokens
        # httpx applies timeout_s to each phase (connect, read, write, pool). vLLM answers a
        # non-streaming request in one body, so the read phase is the wait for the model.
        # trust_env=False: the prompt carries KYC and PEP data, so it never follows an
        # HTTP(S)_PROXY from the environment to somewhere other than base_url.
        self._http = httpx.Client(
            base_url=base_url, timeout=timeout_s, transport=transport, trust_env=False
        )

    def request_body(self, prompt: str, system_prompt: str) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": self.schema_name,
                    "strict": True,
                    "schema": self.response_schema,
                },
            },
            "temperature": 0,
            "seed": self.seed,
            "max_tokens": self.max_tokens,
        }

    def complete(self, prompt: str, system_prompt: str) -> str:
        try:
            response = self._http.post(
                CHAT_COMPLETIONS_PATH, json=self.request_body(prompt, system_prompt)
            )
        except httpx.TimeoutException as err:
            # ubunturemit_asco's own class: the agents catch exactly this one and escalate.
            raise InferenceTimeoutError(
                f"{self.model} gave no reply within {self.timeout_s}s ({type(err).__name__})."
            ) from err
        except httpx.RequestError as err:  # transport errors, and an undecodable body
            raise InferenceResponseError(
                f"{self.model} unreachable: {type(err).__name__}: {err}"
            ) from err

        if response.status_code != 200:
            raise InferenceResponseError(f"{self.model} answered HTTP {response.status_code}.")
        try:
            choice = response.json()["choices"][0]
            finish_reason = choice["finish_reason"]
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as err:
            raise InferenceResponseError(
                f"{self.model} sent no reply in the body: {err!r}"
            ) from err

        # "length" is truncated JSON; "abort" or anything else means the model did not finish.
        if finish_reason != "stop":
            raise InferenceResponseError(
                f"{self.model} stopped with finish_reason={finish_reason!r}."
            )
        if not isinstance(content, str) or not content:
            raise InferenceResponseError(f"{self.model} finished with empty content.")
        return content

    def close(self) -> None:
        self._http.close()
