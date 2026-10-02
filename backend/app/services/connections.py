"""Connection requests. The state machine is DATA, not scattered ifs.

Table-driven so adding a state means adding a row, and every invalid transition
has a test. specs/05_connection_requests.md §3.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import (
    Conflict,
    NotFound,
    NotReceiver,
    NotSender,
    ValidationFailed,
)
from app.models import ConnectionRequest, NotificationType, User
from app.models.enums import ConnectionStatus
from app.services.notifications import notify


class Action(StrEnum):
    SEND = "send"
    ACCEPT = "accept"
    DECLINE = "decline"
    WITHDRAW = "withdraw"


class Actor(StrEnum):
    SENDER = "sender"
    RECEIVER = "receiver"


@dataclass(frozen=True)
class Transition:
    from_status: str | None  # None = no existing row (send)
    action: str
    to_status: str | None  # None = row deleted (withdraw)
    actor: str
    allowed: bool
    error_status: int = 409
    error_code: str = "already_responded"


# The authority for the service and its tests. Every (status, action, actor)
# combination is present, so lookup_transition is total and an unmapped
# combination can never surface as a KeyError-turned-500.
TRANSITIONS: tuple[Transition, ...] = (
    # From None — no row exists yet, so only SEND makes sense.
    Transition(None, Action.SEND, ConnectionStatus.PENDING, Actor.SENDER, True),
    Transition(None, Action.SEND, None, Actor.RECEIVER, False, 409, "already_exists"),
    Transition(None, Action.ACCEPT, None, Actor.SENDER, False, 404, "not_found"),
    Transition(None, Action.ACCEPT, None, Actor.RECEIVER, False, 404, "not_found"),
    Transition(None, Action.DECLINE, None, Actor.SENDER, False, 404, "not_found"),
    Transition(None, Action.DECLINE, None, Actor.RECEIVER, False, 404, "not_found"),
    Transition(None, Action.WITHDRAW, None, Actor.SENDER, False, 404, "not_found"),
    Transition(None, Action.WITHDRAW, None, Actor.RECEIVER, False, 404, "not_found"),
    # From pending
    Transition(ConnectionStatus.PENDING, Action.ACCEPT, ConnectionStatus.ACCEPTED, Actor.RECEIVER, True),
    # Only the receiver can respond. The sender accepting their own request would
    # open a thread without the other person's consent — AGENTS.md §5 rule 2.
    Transition(ConnectionStatus.PENDING, Action.ACCEPT, None, Actor.SENDER, False, 403, "not_receiver"),
    Transition(ConnectionStatus.PENDING, Action.DECLINE, ConnectionStatus.DECLINED, Actor.RECEIVER, True),
    Transition(ConnectionStatus.PENDING, Action.DECLINE, None, Actor.SENDER, False, 403, "not_receiver"),
    Transition(ConnectionStatus.PENDING, Action.WITHDRAW, None, Actor.SENDER, True),
    Transition(ConnectionStatus.PENDING, Action.WITHDRAW, None, Actor.RECEIVER, False, 403, "not_sender"),
    # Reverse direction while one is already pending.
    Transition(ConnectionStatus.PENDING, Action.SEND, None, Actor.RECEIVER, False, 409, "already_exists"),
    Transition(ConnectionStatus.PENDING, Action.SEND, None, Actor.SENDER, False, 409, "already_exists"),
    # From accepted (terminal)
    Transition(ConnectionStatus.ACCEPTED, Action.ACCEPT, None, Actor.RECEIVER, False, 409, "already_responded"),
    Transition(ConnectionStatus.ACCEPTED, Action.DECLINE, None, Actor.RECEIVER, False, 409, "already_responded"),
    Transition(ConnectionStatus.ACCEPTED, Action.WITHDRAW, None, Actor.SENDER, False, 409, "already_connected"),
    Transition(ConnectionStatus.ACCEPTED, Action.SEND, None, Actor.SENDER, False, 409, "already_connected"),
    # The sender/receiver labels invert once accepted: whoever is not the
    # original receiver is now acting as sender on a terminal row.
    Transition(ConnectionStatus.ACCEPTED, Action.SEND, None, Actor.RECEIVER, False, 409, "already_connected"),
    Transition(ConnectionStatus.ACCEPTED, Action.ACCEPT, None, Actor.SENDER, False, 403, "not_receiver"),
    Transition(ConnectionStatus.ACCEPTED, Action.DECLINE, None, Actor.SENDER, False, 403, "not_receiver"),
    Transition(ConnectionStatus.ACCEPTED, Action.WITHDRAW, None, Actor.RECEIVER, False, 403, "not_sender"),
    # From declined (terminal) — re-requesting would ignore an answer.
    Transition(ConnectionStatus.DECLINED, Action.SEND, None, Actor.SENDER, False, 409, "request_declined"),
    Transition(ConnectionStatus.DECLINED, Action.SEND, None, Actor.RECEIVER, False, 409, "request_declined"),
    Transition(ConnectionStatus.DECLINED, Action.ACCEPT, None, Actor.RECEIVER, False, 409, "already_responded"),
    Transition(ConnectionStatus.DECLINED, Action.DECLINE, None, Actor.RECEIVER, False, 409, "already_responded"),
    Transition(ConnectionStatus.DECLINED, Action.WITHDRAW, None, Actor.SENDER, False, 409, "request_declined"),
    Transition(ConnectionStatus.DECLINED, Action.ACCEPT, None, Actor.SENDER, False, 403, "not_receiver"),
    Transition(ConnectionStatus.DECLINED, Action.DECLINE, None, Actor.SENDER, False, 403, "not_receiver"),
    Transition(ConnectionStatus.DECLINED, Action.WITHDRAW, None, Actor.RECEIVER, False, 403, "not_sender"),
)


def lookup_transition(from_status: str | None, action: str, actor: str) -> Transition:
    for t in TRANSITIONS:
        if t.from_status == from_status and t.action == action and t.actor == actor:
            return t
    raise KeyError(f"No transition defined for {from_status}/{action}/{actor}")


def apply_transition(t: Transition) -> None:
    """Raise the documented error if the transition is not allowed."""
    if t.allowed:
        return
    if t.error_code == "not_found":
        from app.errors import NotFound

        raise NotFound("That request does not exist.")
    if t.error_code == "not_receiver":
        raise NotReceiver()
    if t.error_code == "not_sender":
        raise NotSender()
    if t.error_code == "already_exists":
        raise Conflict(
            "There is already a request between you.", code="already_exists"
        )
    if t.error_code == "already_connected":
        raise Conflict("You are already connected.", code="already_connected")
    if t.error_code == "request_declined":
        raise Conflict(
            "This request was previously declined.", code="request_declined"
        )
    raise Conflict("This request has already been answered.", code=t.error_code)


def actor_role(request: ConnectionRequest | None, viewer_id: uuid.UUID) -> str:
    if request is None:
        return Actor.SENDER
    return Actor.RECEIVER if request.receiver_id == viewer_id else Actor.SENDER


def pair(user_a: uuid.UUID, user_b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """LEAST/GREATEST normalise direction so the unique index catches both."""
    lo, hi = sorted([user_a, user_b])
    return lo, hi


# ─── Queries ─────────────────────────────────────────────────────────────────


async def find_request(
    db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID
) -> ConnectionRequest | None:
    lo, hi = pair(user_a, user_b)
    return await db.scalar(
        select(ConnectionRequest).where(
            ConnectionRequest.pair_lo == lo, ConnectionRequest.pair_hi == hi
        )
    )


async def get_request_or_404(db: AsyncSession, request_id: uuid.UUID) -> ConnectionRequest:
    request = await db.get(ConnectionRequest, request_id)
    if request is None:
        raise NotFound("That request does not exist.")
    return request


async def load_participant_requests(
    db: AsyncSession, user_id: uuid.UUID, *, connection_filter: str | None = None
) -> list[ConnectionRequest]:
    stmt = select(ConnectionRequest).where(
        (ConnectionRequest.sender_id == user_id)
        | (ConnectionRequest.receiver_id == user_id)
    )
    if connection_filter == "received":
        stmt = stmt.where(
            ConnectionRequest.receiver_id == user_id,
            ConnectionRequest.status == ConnectionStatus.PENDING,
        )
    elif connection_filter == "sent":
        stmt = stmt.where(
            ConnectionRequest.sender_id == user_id,
            ConnectionRequest.status == ConnectionStatus.PENDING,
        )
    elif connection_filter == "connected":
        stmt = stmt.where(ConnectionRequest.status == ConnectionStatus.ACCEPTED)
    stmt = stmt.order_by(ConnectionRequest.created_at.desc())
    return list(await db.scalars(stmt))


async def connection_state(
    db: AsyncSession, viewer_id: uuid.UUID, other_id: uuid.UUID
) -> str:
    """none | pending_incoming | pending_outgoing | connected | declined.

    Pending counts in BOTH directions — the most commonly missed exclusion in
    matching (specs/04 §5).
    """
    request = await find_request(db, viewer_id, other_id)
    if request is None:
        return "none"
    if request.status == ConnectionStatus.ACCEPTED:
        return "connected"
    if request.status == ConnectionStatus.PENDING:
        return (
            "pending_incoming"
            if request.receiver_id == viewer_id
            else "pending_outgoing"
        )
    return "declined"


async def summary(db: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    received = await db.scalar(
        select(func.count())
        .select_from(ConnectionRequest)
        .where(
            ConnectionRequest.receiver_id == user_id,
            ConnectionRequest.status == ConnectionStatus.PENDING,
        )
    )
    sent = await db.scalar(
        select(func.count())
        .select_from(ConnectionRequest)
        .where(
            ConnectionRequest.sender_id == user_id,
            ConnectionRequest.status == ConnectionStatus.PENDING,
        )
    )
    connected = await db.scalar(
        select(func.count())
        .select_from(ConnectionRequest)
        .where(
            ConnectionRequest.status == ConnectionStatus.ACCEPTED,
            (ConnectionRequest.sender_id == user_id)
            | (ConnectionRequest.receiver_id == user_id),
        )
    )
    return {
        "received_pending": received or 0,
        "sent_pending": sent or 0,
        "connected": connected or 0,
    }


# ─── Commands ────────────────────────────────────────────────────────────────


async def send_request(
    db: AsyncSession,
    sender: User,
    receiver_id: uuid.UUID,
    *,
    message: str | None = None,
) -> ConnectionRequest:
    if sender.id == receiver_id:
        raise ValidationFailed({"receiver_id": "You cannot connect with yourself."})

    # Sending is a 403 for the same reason browsing matches is: an incomplete
    # profile means the request lands in a context with nothing to explain.
    sender_profile = sender.profile
    if sender_profile is None or not sender_profile.profile_complete:
        from app.errors import ProfileIncomplete

        raise ProfileIncomplete()

    receiver = await db.get(User, receiver_id)
    if receiver is None or not receiver.is_active:
        raise NotFound("That person does not exist.")

    existing = await find_request(db, sender.id, receiver_id)
    actor = actor_role(existing, sender.id)
    apply_transition(lookup_transition(
        existing.status if existing else None, Action.SEND, actor
    ))

    # Matching cannot explain why to someone with no skills on their profile.
    receiver_profile = receiver.profile
    if receiver_profile is None or not receiver_profile.profile_complete:
        from app.errors import ReceiverProfileIncomplete

        raise ReceiverProfileIncomplete()

    lo, hi = pair(sender.id, receiver_id)
    request = ConnectionRequest(
        sender_id=sender.id,
        receiver_id=receiver_id,
        pair_lo=lo,
        pair_hi=hi,
        status=ConnectionStatus.PENDING,
        message=(message.strip() or None) if message else None,
    )
    db.add(request)
    await db.flush()

    await notify(
        db,
        user_id=receiver.id,
        notification_type=NotificationType.CONNECTION_REQUESTED,
        actor=sender,
        connection_request_id=request.id,
        url="/connections",
    )
    await db.commit()
    return request


async def respond(
    db: AsyncSession, request: ConnectionRequest, viewer: User, action: str
) -> ConnectionRequest:
    actor = actor_role(request, viewer.id)
    transition = lookup_transition(request.status, action, actor)
    apply_transition(transition)

    assert transition.to_status is not None
    # Guard on state, not a "have we notified?" flag. A flag is a second source
    # of truth that can desynchronise. specs/07_notifications.md §3.
    first_response = request.responded_at is None
    request.status = transition.to_status
    if first_response:
        request.responded_at = datetime.now(UTC)
        request.responded_by = viewer.id

    # Load the other party explicitly — a lazily-loaded relationship touched
    # here raises MissingGreenlet in async context.
    # If I am the receiver, the other party is the sender, and vice versa.
    other_id = request.sender_id if request.receiver_id == viewer.id else request.receiver_id
    other = await db.get(User, other_id)
    if first_response and other is not None:
        if action == Action.ACCEPT:
            await notify(
                db,
                user_id=other.id,
                notification_type=NotificationType.CONNECTION_ACCEPTED,
                actor=viewer,
                connection_request_id=request.id,
                url="/connections",
            )
        elif action == Action.DECLINE:
            await notify(
                db,
                user_id=other.id,
                notification_type=NotificationType.CONNECTION_DECLINED,
                actor=viewer,
                connection_request_id=request.id,
                url="/connections",
            )
    # Do NOT create a thread here — it is created lazily on first message.
    await db.commit()
    return request


async def withdraw(db: AsyncSession, request: ConnectionRequest, viewer: User) -> None:
    actor = actor_role(request, viewer.id)
    apply_transition(lookup_transition(request.status, Action.WITHDRAW, actor))
    await db.delete(request)
    # No notification: the receiver never saw it as pending.
    await db.commit()


async def accepted_request_for(
    db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID
) -> ConnectionRequest | None:
    lo, hi = pair(user_a, user_b)
    return await db.scalar(
        select(ConnectionRequest).where(
            ConnectionRequest.pair_lo == lo,
            ConnectionRequest.pair_hi == hi,
            ConnectionRequest.status == ConnectionStatus.ACCEPTED,
        )
    )


__all__ = [
    "Action",
    "Actor",
    "Transition",
    "TRANSITIONS",
    "lookup_transition",
    "apply_transition",
    "actor_role",
    "pair",
    "find_request",
    "get_request_or_404",
    "load_participant_requests",
    "connection_state",
    "summary",
    "send_request",
    "respond",
    "withdraw",
    "accepted_request_for",
]