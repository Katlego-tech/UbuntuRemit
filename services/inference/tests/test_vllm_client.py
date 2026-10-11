"""T078 -- VllmChatClient against httpx.MockTransport (docs/design/inference.md §7).

No GPU and no server: the transport stands in for vLLM. A live call is T079.
"""

import json
from collections.abc import Callable
from decimal import Decimal

import httpx
import pytest
import ubunturemit_asco
from ubunturemit_asco import (
    ComplianceAssessmentInput,
    ComplianceSentinel,
    VerdictOutcome,
)
from ubunturemit_domain import CurrencyCode, Money, PaymentPurpose, SourceOfFunds, TransferId
from ubunturemit_inference import (
    CHAT_COMPLETIONS_PATH,
    COMPLIANCE_VERDICT_NAME,
    COMPLIANCE_VERDICT_SCHEMA,
    InferenceResponseError,
    VllmChatClient,
)

VALID_VERDICT = json.dumps(
    {
        "outcome": "PASS",
        "riskScore": 0.1,
        "citedRules": ["FICA s21"],
        "rationale": "Scripted reply from a mocked server.",
    }
)


def _reply(content: object = VALID_VERDICT, finish_reason: object = "stop") -> dict[str, object]:
    return {"choices": [{"message": {"content": content}, "finish_reason": finish_reason}]}


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> VllmChatClient:
    return VllmChatClient(
        base_url="http://inference.internal:8001",
        model="sentinel-model",
        response_schema=COMPLIANCE_VERDICT_SCHEMA,
        schema_name=COMPLIANCE_VERDICT_NAME,
        timeout_s=5.0,
        seed=1234,
        max_tokens=1024,
        transport=httpx.MockTransport(handler),
    )


def _raising(exc: type[httpx.TransportError]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc("simulated", request=request)

    return handler


def test_request_carries_schema_envelope_temperature_seed_and_max_tokens() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_reply())

    _client(handler).complete("the payload", "the system prompt")

    (request,) = seen
    assert request.method == "POST"
    assert request.url.path == CHAT_COMPLETIONS_PATH
    body = json.loads(request.content)
    assert body["model"] == "sentinel-model"
    assert body["messages"] == [
        {"role": "system", "content": "the system prompt"},
        {"role": "user", "content": "the payload"},
    ]
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": COMPLIANCE_VERDICT_NAME,
            "strict": True,
            "schema": COMPLIANCE_VERDICT_SCHEMA,
        },
    }
    assert body["temperature"] == 0
    assert body["seed"] == 1234
    assert body["max_tokens"] == 1024


def test_a_valid_reply_is_returned_byte_for_byte() -> None:
    odd_but_valid = VALID_VERDICT.replace(", ", ",   ")
    client = _client(lambda _: httpx.Response(200, json=_reply(odd_but_valid)))
    assert client.complete("p", "s") == odd_but_valid


@pytest.mark.parametrize("timeout", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout])
def test_every_timeout_is_ascos_own_inference_timeout_error(
    timeout: type[httpx.TransportError],
) -> None:
    with pytest.raises(ubunturemit_asco.InferenceTimeoutError) as caught:
        _client(_raising(timeout)).complete("p", "s")
    # The exact class the agents catch -- not a look-alike (inference.md §3).
    assert type(caught.value) is ubunturemit_asco.InferenceTimeoutError


@pytest.mark.parametrize(
    "handler",
    [
        _raising(httpx.ConnectError),  # connection refused / DNS failure
        lambda _: httpx.Response(500, text="internal error"),
        lambda _: httpx.Response(200, text="not json"),
        lambda _: httpx.Response(200, json={"choices": []}),
        lambda _: httpx.Response(200, json={"choices": [{"finish_reason": "stop"}]}),
        lambda _: httpx.Response(200, json=_reply(content=None)),
        lambda _: httpx.Response(200, json=_reply(content="")),
        lambda _: httpx.Response(200, json=_reply(finish_reason="length")),
        lambda _: httpx.Response(200, json=_reply(finish_reason="abort")),
    ],
    ids=[
        "refused",
        "http-500",
        "non-json-body",
        "no-choices",
        "no-message",
        "null-content",
        "empty-content",
        "truncated",
        "aborted",
    ],
)
def test_every_unusable_reply_is_an_inference_response_error(
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    with pytest.raises(InferenceResponseError):
        _client(handler).complete("p", "s")


@pytest.mark.parametrize(
    "overrides",
    [{"max_tokens": 0}, {"timeout_s": 0}, {"model": " "}, {"response_schema": {}}],
    ids=["no-max-tokens", "no-timeout", "no-model", "no-schema"],
)
def test_an_incomplete_client_refuses_to_exist(overrides: dict[str, object]) -> None:
    fields: dict[str, object] = {
        "base_url": "http://inference.internal:8001",
        "model": "m",
        "response_schema": COMPLIANCE_VERDICT_SCHEMA,
        "schema_name": COMPLIANCE_VERDICT_NAME,
        "timeout_s": 5.0,
        "seed": 1,
        "max_tokens": 1,
        **overrides,
    }
    with pytest.raises(ValueError):
        VllmChatClient(**fields)  # type: ignore[arg-type]


# --- through the real agent: the error classes land on the paths §4 draws ---------


def _assessment() -> ComplianceAssessmentInput:
    return ComplianceAssessmentInput(
        transfer_id=TransferId("TR-INF-001"),
        corridor_source=CurrencyCode.ZAR,
        corridor_target=CurrencyCode.GHS,
        amount=Money(minor_units=200000, currency=CurrencyCode.ZAR),
        purpose=PaymentPurpose.FAMILY_SUPPORT,
        source_of_funds=SourceOfFunds.EMPLOYMENT_SALARY,
        sender_kyc_tier="L3",
        sender_country="ZA",
        sender_is_pep=False,
        recipient_country="GH",
        recipient_account_age_days=412,
        prior_transfers_30d_count=0,
        prior_transfers_30d_minor_units=0,
    )


def test_sentinel_parses_a_reply_from_the_client() -> None:
    sentinel = ComplianceSentinel(llm_client=_client(lambda _: httpx.Response(200, json=_reply())))
    verdict, _, _ = sentinel.assess(_assessment())
    assert verdict.outcome == VerdictOutcome.PASS
    assert verdict.risk_score == Decimal("0.1")


def test_a_timeout_reaches_the_sentinel_as_a_timeout_not_as_malformed_output() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("simulated", request=request)

    verdict, _, _ = ComplianceSentinel(llm_client=_client(handler)).assess(_assessment())
    assert verdict.outcome == VerdictOutcome.ESCALATE
    assert verdict.cited_rules == ["INFERENCE_TIMEOUT_FAIL_CLOSED"]
    assert len(calls) == 1  # escalated at once -- no re-ask spent inside the RTGS window


def test_a_truncated_reply_is_re_asked_once_then_escalated() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_reply(finish_reason="length"))

    verdict, _, _ = ComplianceSentinel(llm_client=_client(handler)).assess(_assessment())
    assert verdict.outcome == VerdictOutcome.ESCALATE
    assert verdict.cited_rules == ["MALFORMED_OUTPUT_ESCALATE"]
    assert len(calls) == 2
