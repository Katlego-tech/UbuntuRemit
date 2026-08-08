"""The §8 state-machine test.

"Every transition **not** in §4 raises, enumerated exhaustively over
`TransferState × TransferState`." This is the test that makes "undrawn =
impossible" real, so the legal set below is written out by hand from the
diagram rather than imported from the implementation -- importing it would
make the test agree with the code by construction and prove nothing.
"""

import itertools

import pytest
from ubunturemit_domain import Transfer, TransferState

from .factories import a_transfer

# Read directly off the stateDiagram in domain-model.md §4.
LEGAL: frozenset[tuple[TransferState, TransferState]] = frozenset(
    {
        (TransferState.INITIATED, TransferState.VALIDATED),
        (TransferState.INITIATED, TransferState.REJECTED),
        (TransferState.VALIDATED, TransferState.SETTLING),
        (TransferState.VALIDATED, TransferState.REJECTED),
        (TransferState.SETTLING, TransferState.DELIVERED),
        (TransferState.SETTLING, TransferState.FAILED),
        (TransferState.FAILED, TransferState.SETTLING),
    }
)

ALL_PAIRS = list(itertools.product(TransferState, TransferState))


def test_the_matrix_is_exhaustive():
    # 6 states -> 36 ordered pairs. If a state is added to §5 without updating
    # §4, this is the test that notices.
    assert len(ALL_PAIRS) == 36
    assert len(LEGAL) == 7


@pytest.mark.parametrize(("start", "end"), ALL_PAIRS, ids=lambda s: s.name)
def test_every_pair_is_permitted_exactly_when_section_4_draws_it(
    start: TransferState, end: TransferState
):
    transfer = a_transfer(state=start)

    if (start, end) in LEGAL:
        moved = transfer.transition_to(end)
        assert moved.state is end
    else:
        with pytest.raises(ValueError, match="transition"):
            transfer.transition_to(end)


class TestTheRulesBehindTheDiagram:
    def test_no_state_transitions_to_itself(self):
        for state in TransferState:
            assert (state, state) not in LEGAL

    def test_terminal_states_go_nowhere(self):
        # §4: "there is no path from REJECTED to anything". A rejected
        # transfer that needs to proceed is a NEW transfer with a new id, so
        # the audit trail of the rejection survives intact.
        for terminal in (TransferState.DELIVERED, TransferState.REJECTED):
            assert not [pair for pair in LEGAL if pair[0] is terminal]

    def test_settling_is_unreachable_without_validated(self):
        # "no path that skips VALIDATED"
        into_settling = {start for (start, end) in LEGAL if end is TransferState.SETTLING}
        assert into_settling == {TransferState.VALIDATED, TransferState.FAILED}

    def test_failed_to_settling_is_the_only_cycle(self):
        # Compared as unordered pairs: a two-way edge appears in LEGAL twice,
        # once per direction, but it is still one cycle.
        cycles = {frozenset(pair) for pair in LEGAL if tuple(reversed(pair)) in LEGAL}
        assert cycles == {frozenset({TransferState.FAILED, TransferState.SETTLING})}


class TestTransitionSemantics:
    def test_returns_a_new_transfer_and_leaves_the_original_alone(self):
        # transitionTo(TransferState) Transfer -- it returns a Transfer, and
        # §3 requires the old quote to stay on the audit trail.
        original = a_transfer(state=TransferState.INITIATED)
        moved = original.transition_to(TransferState.VALIDATED)

        assert moved is not original
        assert original.state is TransferState.INITIATED
        assert isinstance(moved, Transfer)

    def test_carries_every_other_field_across_unchanged(self):
        original = a_transfer(state=TransferState.INITIATED)
        moved = original.transition_to(TransferState.VALIDATED)

        assert moved.id == original.id
        assert moved.reference == original.reference
        assert moved.quote == original.quote
        assert moved.sender == original.sender
        assert moved.recipient == original.recipient
        assert moved.declaration == original.declaration
        assert moved.created_at == original.created_at

    def test_rejects_a_state_that_is_not_a_transfer_state(self):
        with pytest.raises(TypeError, match="state"):
            a_transfer().transition_to("VALIDATED")  # type: ignore[arg-type]
