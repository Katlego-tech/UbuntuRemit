"""The §8 contract test.

"Every language binding of these entities is a subset of §3 (no extra fields)."

§5 states the rule this enforces: a **narrower** projection is allowed where a
context genuinely doesn't need a field; **adding a field the diagram doesn't
have is not**, and the fix for a missing field is to change the design document
first. So this asserts a subset, not equality.

The expected sets below are transcribed from the class diagram by hand. They
must never be derived from the code -- that would make the test agree with the
implementation by construction.
"""

import dataclasses
import re

import pytest
from ubunturemit_domain import (
    ComplianceDeclaration,
    Corridor,
    FxQuote,
    Money,
    Party,
    Transfer,
    TransferQuote,
)

# Attribute names exactly as drawn in domain-model.md §3, in camelCase.
DRAWN: dict[type, set[str]] = {
    Money: {"minorUnits", "currency"},
    Corridor: {"source", "target", "papssEligible"},
    FxQuote: {"corridor", "rate", "guaranteed", "capturedAt", "expiresAt", "source"},
    TransferQuote: {"send", "fee", "recipientReceives", "fx"},
    Party: {"fullName", "accountNumber", "bic", "country"},
    ComplianceDeclaration: {"purpose", "sourceOfFunds"},
    Transfer: {
        "id",
        "reference",
        "sender",
        "recipient",
        "quote",
        "declaration",
        "state",
        "rail",
        "createdAt",
        "settlementSeconds",
    },
}


def to_camel(snake: str) -> str:
    head, *tail = snake.split("_")
    return head + "".join(word.capitalize() for word in tail)


ENTITIES = pytest.mark.parametrize(
    ("entity", "drawn"),
    DRAWN.items(),
    ids=lambda v: getattr(v, "__name__", ""),
)


@ENTITIES
def test_no_entity_carries_a_field_the_diagram_does_not_draw(entity: type, drawn: set[str]):
    actual = {to_camel(f.name) for f in dataclasses.fields(entity)}
    assert actual <= drawn, (
        f"{entity.__name__} has {actual - drawn} which §3 does not draw. "
        "Change docs/design/domain-model.md first, then the code."
    )


@ENTITIES
def test_every_entity_is_frozen(entity: type, drawn: set[str]):
    # §3: "Transfer.quote is immutable once state != INITIATED", and a re-quote
    # produces a new TransferQuote. Frozen throughout is how that is kept true
    # without a per-field guard.
    assert entity.__dataclass_params__.frozen  # type: ignore[attr-defined]


def test_camel_case_helper_matches_the_diagram():
    # Guard on the guard: if to_camel were wrong, every subset check above
    # would pass vacuously by producing names that are in no expected set.
    assert to_camel("minor_units") == "minorUnits"
    assert to_camel("recipient_receives") == "recipientReceives"
    assert to_camel("id") == "id"


def test_the_docstring_of_every_entity_cites_the_design_doc():
    # Cheap, but it is what keeps the code discoverable from the diagram and
    # the diagram discoverable from the code.
    for entity in DRAWN:
        assert entity.__doc__, f"{entity.__name__} has no docstring"
        assert re.search(r"domain-model\.md", entity.__doc__), (
            f"{entity.__name__} does not cite domain-model.md"
        )
