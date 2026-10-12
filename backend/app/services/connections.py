from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.domain import ConnectionRequest, Profile
from app.services.notifications import notify
from app.web import ApiError

TRANSITIONS = {
    ("pending", "accept"): "accepted",
    ("pending", "decline"): "declined",
}


def transition_status(status: str, action: str, actor_id: UUID, sender_id: UUID, receiver_id: UUID) -> str:
    if actor_id not in (sender_id, receiver_id):
        raise ApiError(404, "not_found", "Connection request not found.")
    if action not in {"accept", "decline"}:
        raise ApiError(422, "validation_error", "Choose accept or decline.", {"action": "Invalid action."})
    if status != "pending":
        raise ApiError(409, "already_responded", "This request has already been answered.")
    if actor_id == sender_id:
        raise ApiError(403, "not_receiver", "Only the recipient can answer this request.")
    if actor_id != receiver_id:
        raise ApiError(403, "not_receiver", "Only the recipient can answer this request.")
    return TRANSITIONS[(status, action)]


async def send_request(db: AsyncSession, sender: User, receiver_id: UUID, message: str | None) -> ConnectionRequest:
    if sender.id == receiver_id:
        raise ApiError(422, "validation_error", "You cannot send a request to yourself.", {"receiver_id": "Choose another user."})
    sender_profile = await db.scalar(select(Profile).where(Profile.user_id == sender.id))
    if sender_profile is None or not sender_profile.profile_complete:
        raise ApiError(403, "profile_incomplete", "Choose a role and add at least one skill before connecting.")
    receiver = await db.scalar(select(User).where(User.id == receiver_id, User.is_active.is_(True)))
    if receiver is None:
        raise ApiError(404, "not_found", "User not found.")
    receiver_profile = await db.scalar(select(Profile).where(Profile.user_id == receiver.id))
    if receiver_profile is None or not receiver_profile.profile_complete:
        raise ApiError(422, "receiver_profile_incomplete", "This person is still completing their profile.")

    previous = await db.scalar(
        select(ConnectionRequest)
        .where(
            or_(
                and_(ConnectionRequest.sender_id == sender.id, ConnectionRequest.receiver_id == receiver_id),
                and_(ConnectionRequest.sender_id == receiver_id, ConnectionRequest.receiver_id == sender.id),
            )
        )
        .with_for_update()
    )
    if previous:
        code = {
            "pending": "already_exists",
            "accepted": "already_connected",
            "declined": "request_declined",
        }[previous.status]
        message_text = {
            "already_exists": "A connection request already exists.",
            "already_connected": "You are already connected.",
            "request_declined": "This person has already declined a connection request.",
        }[code]
        raise ApiError(409, code, message_text)

    connection = ConnectionRequest(sender_id=sender.id, receiver_id=receiver_id, message=message)
    db.add(connection)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ApiError(409, "already_exists", "A connection request already exists.") from exc
    await notify(
        db,
        receiver_id,
        "connection_requested",
        sender,
        connection_id=connection.id,
        text=f"{sender.display_name} wants to connect",
    )
    return connection


async def transition_request(
    db: AsyncSession, connection_id: UUID, actor: User, action: str
) -> ConnectionRequest:
    connection = await db.scalar(
        select(ConnectionRequest).where(ConnectionRequest.id == connection_id).with_for_update()
    )
    if connection is None or actor.id not in (connection.sender_id, connection.receiver_id):
        raise ApiError(404, "not_found", "Connection request not found.")
    connection.status = transition_status(
        connection.status, action, actor.id, connection.sender_id, connection.receiver_id
    )
    connection.responded_at = datetime.now(UTC)
    connection.responded_by = actor.id
    sender = await db.get(User, connection.sender_id)
    if sender is not None:
        accepted = action == "accept"
        await notify(
            db,
            connection.sender_id,
            "connection_accepted" if accepted else "connection_declined",
            actor,
            connection_id=connection.id,
            text=f"{actor.display_name} {'accepted' if accepted else 'declined'} your request",
        )
    await db.flush()
    return connection


async def withdraw_request(db: AsyncSession, connection_id: UUID, actor: User) -> None:
    connection = await db.scalar(
        select(ConnectionRequest).where(ConnectionRequest.id == connection_id).with_for_update()
    )
    if connection is None or actor.id not in (connection.sender_id, connection.receiver_id):
        raise ApiError(404, "not_found", "Connection request not found.")
    if actor.id != connection.sender_id:
        raise ApiError(403, "not_sender", "Only the sender can withdraw this request.")
    if connection.status != "pending":
        raise ApiError(409, "already_responded", "Only pending requests can be withdrawn.")
    await db.delete(connection)


async def request_payload(db: AsyncSession, connection: ConnectionRequest, viewer_id: UUID) -> dict:
    sender = await db.get(User, connection.sender_id)
    receiver = await db.get(User, connection.receiver_id)
    sender_profile = await db.scalar(select(Profile).where(Profile.user_id == connection.sender_id))
    receiver_profile = await db.scalar(select(Profile).where(Profile.user_id == connection.receiver_id))

    def summary(user: User | None, profile: Profile | None) -> dict | None:
        if user is None:
            return None
        return {
            "id": str(user.id),
            "display_name": user.display_name,
            "has_photo": bool(profile and profile.photo_id),
            "photo_url": f"/api/v1/users/{user.id}/photo" if profile and profile.photo_id else None,
        }

    other_id = connection.receiver_id if viewer_id == connection.sender_id else connection.sender_id
    other = receiver if other_id == connection.receiver_id else sender
    other_profile = receiver_profile if other_id == connection.receiver_id else sender_profile
    return {
        "id": str(connection.id),
        "status": connection.status,
        "sender": summary(sender, sender_profile),
        "receiver": summary(receiver, receiver_profile),
        "other": summary(other, other_profile),
        "message": connection.message,
        "created_at": connection.created_at,
        "responded_at": connection.responded_at,
        "responded_by": str(connection.responded_by) if connection.responded_by else None,
        "viewer_is_sender": viewer_id == connection.sender_id,
    }


async def connection_counts(db: AsyncSession, user_id: UUID) -> dict[str, int]:
    received = await db.scalar(
        select(func.count()).select_from(ConnectionRequest).where(
            ConnectionRequest.receiver_id == user_id, ConnectionRequest.status == "pending"
        )
    )
    sent = await db.scalar(
        select(func.count()).select_from(ConnectionRequest).where(
            ConnectionRequest.sender_id == user_id, ConnectionRequest.status == "pending"
        )
    )
    connected = await db.scalar(
        select(func.count()).select_from(ConnectionRequest).where(
            ConnectionRequest.status == "accepted",
            or_(ConnectionRequest.sender_id == user_id, ConnectionRequest.receiver_id == user_id),
        )
    )
    return {"received_pending": int(received or 0), "sent_pending": int(sent or 0), "connected": int(connected or 0)}
