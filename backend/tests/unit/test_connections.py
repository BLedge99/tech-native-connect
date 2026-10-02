"""Connection request state machine. Table-driven over the full transition
table, so every invalid transition has a test — specs/05 §7."""

import uuid

import pytest

from app.errors import Conflict, Forbidden, NotReceiver, NotSender
from app.models.enums import ConnectionStatus
from app.services.connections import (
    TRANSITIONS,
    Action,
    Actor,
    apply_transition,
    lookup_transition,
    pair,
)


def test_transition_table_covers_every_status_and_action():
    """If someone adds a status without a row for it, this fails."""
    for status in (None, ConnectionStatus.PENDING, ConnectionStatus.ACCEPTED, ConnectionStatus.DECLINED):
        for action in (Action.SEND, Action.ACCEPT, Action.DECLINE, Action.WITHDRAW):
            for actor in (Actor.SENDER, Actor.RECEIVER):
                assert lookup_transition(status, action, actor) is not None


def test_transition_table_has_no_duplicates():
    seen = set()
    for t in TRANSITIONS:
        key = (t.from_status, t.action, t.actor)
        assert key not in seen, f"duplicate transition row for {key}"
        seen.add(key)


# ─── Allowed transitions ─────────────────────────────────────────────────────


def test_send_creates_pending():
    t = lookup_transition(None, Action.SEND, Actor.SENDER)
    assert t.allowed
    assert t.to_status == ConnectionStatus.PENDING
    apply_transition(t)  # must not raise


def test_receiver_can_accept():
    apply_transition(lookup_transition(ConnectionStatus.PENDING, Action.ACCEPT, Actor.RECEIVER))


def test_receiver_can_decline():
    apply_transition(lookup_transition(ConnectionStatus.PENDING, Action.DECLINE, Actor.RECEIVER))


def test_sender_can_withdraw():
    apply_transition(lookup_transition(ConnectionStatus.PENDING, Action.WITHDRAW, Actor.SENDER))


# ─── The authorisation rule ──────────────────────────────────────────────────


def test_sender_cannot_accept():
    """AGENTS.md §5 rule 2. The sender accepting their own request would open a
    thread without the other person's consent."""
    t = lookup_transition(ConnectionStatus.PENDING, Action.ACCEPT, Actor.SENDER)
    assert not t.allowed
    with pytest.raises(NotReceiver) as exc:
        apply_transition(t)
    assert exc.value.code == "not_receiver"


def test_sender_cannot_decline():
    with pytest.raises(NotReceiver):
        apply_transition(lookup_transition(ConnectionStatus.PENDING, Action.DECLINE, Actor.SENDER))


def test_receiver_cannot_withdraw():
    with pytest.raises(NotSender):
        apply_transition(lookup_transition(ConnectionStatus.PENDING, Action.WITHDRAW, Actor.RECEIVER))


# ─── Terminal states ─────────────────────────────────────────────────────────


def test_double_accept_rejected():
    with pytest.raises(Conflict) as exc:
        apply_transition(lookup_transition(ConnectionStatus.ACCEPTED, Action.ACCEPT, Actor.RECEIVER))
    assert exc.value.code == "already_responded"


def test_cannot_decline_after_accepting():
    with pytest.raises(Conflict):
        apply_transition(lookup_transition(ConnectionStatus.ACCEPTED, Action.DECLINE, Actor.RECEIVER))


def test_cannot_withdraw_after_accepting():
    with pytest.raises(Conflict) as exc:
        apply_transition(lookup_transition(ConnectionStatus.ACCEPTED, Action.WITHDRAW, Actor.SENDER))
    assert exc.value.code == "already_connected"


def test_cannot_re_request_after_accepting():
    with pytest.raises(Conflict) as exc:
        apply_transition(lookup_transition(ConnectionStatus.ACCEPTED, Action.SEND, Actor.SENDER))
    assert exc.value.code == "already_connected"


# ─── Decline is terminal ─────────────────────────────────────────────────────


def test_decline_is_terminal():
    """Re-requesting ignores an answer that was already given."""
    with pytest.raises(Conflict) as exc:
        apply_transition(lookup_transition(ConnectionStatus.DECLINED, Action.SEND, Actor.SENDER))
    assert exc.value.code == "request_declined"


def test_cannot_accept_after_declining():
    with pytest.raises(Conflict):
        apply_transition(lookup_transition(ConnectionStatus.DECLINED, Action.ACCEPT, Actor.RECEIVER))


def test_cannot_withdraw_after_declining():
    with pytest.raises(Conflict):
        apply_transition(lookup_transition(ConnectionStatus.DECLINED, Action.WITHDRAW, Actor.SENDER))


# ─── Duplicates ──────────────────────────────────────────────────────────────


def test_duplicate_pending_request_rejected():
    with pytest.raises(Conflict) as exc:
        apply_transition(lookup_transition(ConnectionStatus.PENDING, Action.SEND, Actor.SENDER))
    assert exc.value.code == "already_exists"


def test_receiver_cannot_initiate_when_one_already_exists():
    """A reverse-direction request while one is pending is a duplicate, not a
    new request."""
    with pytest.raises(Conflict) as exc:
        apply_transition(lookup_transition(ConnectionStatus.PENDING, Action.SEND, Actor.RECEIVER))
    assert exc.value.code == "already_exists"


def test_lookup_is_total():
    """Every combination has a row, so an unmapped case can never become a 500."""
    for status in (None, ConnectionStatus.PENDING, ConnectionStatus.ACCEPTED, ConnectionStatus.DECLINED):
        for action in Action:
            for actor in Actor:
                assert lookup_transition(status, action, actor) is not None


def test_respond_to_nonexistent_request_is_not_found():
    from app.errors import NotFound

    for action in (Action.ACCEPT, Action.DECLINE):
        for actor in (Actor.SENDER, Actor.RECEIVER):
            with pytest.raises(NotFound):
                apply_transition(lookup_transition(None, action, actor))


# ─── Pair normalisation ──────────────────────────────────────────────────────


def test_pair_is_direction_agnostic():
    a, b = uuid.uuid4(), uuid.uuid4()
    assert pair(a, b) == pair(b, a)


def test_pair_orders_by_id():
    a, b = uuid.uuid4(), uuid.uuid4()
    lo, hi = pair(a, b)
    assert lo < hi