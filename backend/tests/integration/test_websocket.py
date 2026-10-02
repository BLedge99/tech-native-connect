"""WebSocket integration tests. specs/06_messaging.md §6.

These run against a **real uvicorn process**, not ASGITransport — httpx cannot
speak WebSocket, and the realtime layer is the one thing in this project that
cannot be proven through HTTP alone.

What is under test are the behaviours that only break live:
  - the recipient gets the message with no refresh
  - the sender does NOT get their own message back (the duplicate bug)
  - socket subscribe is authorised exactly like HTTP
  - the ack carries client_id so optimistic UI can reconcile
  - messages persist for someone who was offline
"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
import websockets

pytestmark = pytest.mark.anyio

RECV = 6.0      # how long to wait for a frame that should arrive
SILENCE = 1.5   # how long to wait to prove nothing arrives


# ─── Helpers ─────────────────────────────────────────────────────────────────


def cookie_header(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


async def recvn(socket, timeout: float = RECV) -> dict:
    return json.loads(await asyncio.wait_for(socket.recv(), timeout))


async def expect_silence(socket, seconds: float = SILENCE) -> bool:
    """True if nothing arrives. Used to prove the sender gets no echo."""
    try:
        await asyncio.wait_for(socket.recv(), seconds)
        return False
    except asyncio.TimeoutError:
        return True


async def sign_up(http, name: str) -> dict:
    """Registers through the real HTTP API and returns a signed-in session."""
    email = f"{name.lower()}-{uuid.uuid4().hex[:8]}@example.com"
    response = http.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse", "display_name": name},
    )
    assert response.status_code == 201, response.text
    me = http.get("/api/v1/users/me").json()
    return {
        "id": me["id"],
        "email": email,
        "cookies": dict(http.cookies),
        "csrf": {"X-CSRF-Token": me["csrf_token"]},
    }


async def complete_profile(http, session: dict, role: str = "business_developer") -> None:
    """A user needs a role and one skill before they can be connected with."""
    http.patch(
        "/api/v1/users/me",
        json={"role": role, "bio": f"{role} on this course."},
        headers=session["csrf"],
    )
    skill = http.get("/api/v1/skills").json()[0]["id"]
    http.patch("/api/v1/users/me", json={"skill_ids": [skill]}, headers=session["csrf"])


async def connect_pair(ws_client):
    """Two signed-in users with an accepted connection and an open thread."""
    http_a, http_b = ws_client(), ws_client()
    alice = await sign_up(http_a, "Alice")
    bob = await sign_up(http_b, "Bob")
    # Both need a complete profile: the sender is gated by rule 3 too.
    await complete_profile(http_a, alice, role="software_developer")
    await complete_profile(http_b, bob)

    sent = http_a.post(
        "/api/v1/connections", json={"receiver_id": bob["id"]}, headers=alice["csrf"]
    )
    assert sent.status_code == 201, sent.text
    cid = sent.json()["id"]

    accepted = http_b.patch(
        f"/api/v1/connections/{cid}", json={"action": "accept"}, headers=bob["csrf"]
    )
    assert accepted.status_code == 200, accepted.text

    thread = http_a.post(f"/api/v1/connections/{cid}/thread", headers=alice["csrf"])
    assert thread.status_code == 201, thread.text
    return alice, bob, thread.json()["id"], http_a, http_b


async def subscribe(ws_url: str, session: dict, thread_id: str):
    """Opens a socket and subscribes. Returns (socket, subscribe_reply)."""
    socket = await websockets.connect(
        ws_url, additional_headers={"Cookie": cookie_header(session["cookies"])}
    )
    await socket.send(json.dumps({"type": "subscribe", "thread_id": thread_id}))
    reply = await recvn(socket)
    return socket, reply


# ─── The six tests specified in spec 06 §6 ───────────────────────────────────


async def test_recipient_receives_message_live(live_server, ws_client, truncate_test_tables):
    """THE demo test: two sockets, one HTTP send, one live frame."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice, bob, tid, http_a, http_b = await connect_pair(ws_client)

    socket_a, reply = await subscribe(ws_url, alice, tid)
    assert reply["type"] == "subscribed"

    async with socket_a:
        send = http_b.post(
            f"/api/v1/threads/{tid}/messages",
            json={"body": "Hello from Bob"},
            headers=bob["csrf"],
        )
        assert send.status_code == 201, send.text

        frame = await recvn(socket_a)
        assert frame["type"] == "message"
        assert frame["data"]["body"] == "Hello from Bob"
        assert frame["data"]["thread_id"] == tid
        assert frame["data"]["sender_id"] == bob["id"]


async def test_sender_does_not_receive_own_broadcast(
    live_server, ws_client, truncate_test_tables
):
    """The duplicate-message bug. Only ever appears with optimistic UI."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice, bob, tid, http_a, http_b = await connect_pair(ws_client)

    socket_b, reply = await subscribe(ws_url, bob, tid)
    assert reply["type"] == "subscribed"

    async with socket_b:
        http_b.post(
            f"/api/v1/threads/{tid}/messages",
            json={"body": "mine, not yours"},
            headers=bob["csrf"],
        )
        assert await expect_silence(socket_b), "sender received their own message"


async def test_message_persists_if_receiver_offline(
    live_server, ws_client, truncate_test_tables
):
    """There is no durable queue; the client refetches on reconnect."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice, bob, tid, http_a, http_b = await connect_pair(ws_client)

    for index in range(3):
        http_b.post(
            f"/api/v1/threads/{tid}/messages",
            json={"body": f"while you were away {index}"},
            headers=bob["csrf"],
        )

    socket_a, _reply = await subscribe(ws_url, alice, tid)
    async with socket_a:
        history = http_a.get(f"/api/v1/threads/{tid}/messages").json()["items"]
        assert len(history) == 3
        assert {m["body"] for m in history} == {
            "while you were away 0",
            "while you were away 1",
            "while you were away 2",
        }


async def test_subscribe_to_foreign_thread_rejected(
    live_server, ws_client, truncate_test_tables
):
    """The most likely place for a permissions hole: a long-lived route that
    bypasses every HTTP guard."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice, bob, tid, http_a, http_b = await connect_pair(ws_client)
    carol = await sign_up(ws_client(), "Carol")

    async with await websockets.connect(
        ws_url, additional_headers={"Cookie": cookie_header(carol["cookies"])}
    ) as socket:
        await socket.send(json.dumps({"type": "subscribe", "thread_id": tid}))
        reply = await recvn(socket)
        assert reply["type"] == "error"
        assert reply["code"] == "forbidden"

        # And she must not receive anything that happens next.
        http_b.post(
            f"/api/v1/threads/{tid}/messages", json={"body": "private"}, headers=bob["csrf"]
        )
        assert await expect_silence(socket)


async def test_client_id_echoed_in_ack(live_server, ws_client, truncate_test_tables):
    """Optimistic reconciliation depends on this: the sender matches its own
    placeholder by client_id."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice, bob, tid, http_a, http_b = await connect_pair(ws_client)

    socket_b, _reply = await subscribe(ws_url, bob, tid)
    async with socket_b:
        await socket_b.send(
            json.dumps(
                {
                    "type": "send_message",
                    "thread_id": tid,
                    "body": "sent over the socket",
                    "client_id": "client-abc-123",
                }
            )
        )
        ack = await recvn(socket_b)
        assert ack["type"] == "ack"
        assert ack["data"]["client_id"] == "client-abc-123"
        assert ack["data"]["body"] == "sent over the socket"
        assert ack["data"]["id"], "ack must carry the saved message id"

    # Acked AND persisted — not one without the other.
    history = http_a.get(f"/api/v1/threads/{tid}/messages").json()["items"]
    assert any(m["body"] == "sent over the socket" for m in history)


async def test_ws_requires_session(live_server, truncate_test_tables):
    """An unauthenticated handshake is refused."""
    truncate_test_tables()
    _http_base, ws_url = live_server

    with pytest.raises(Exception):
        async with websockets.connect(ws_url):
            pass


# ─── Supporting behaviour ────────────────────────────────────────────────────


async def test_socket_send_reaches_the_other_party(
    live_server, ws_client, truncate_test_tables
):
    """The other direction: A sends over the socket, B receives it live."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice, bob, tid, http_a, http_b = await connect_pair(ws_client)

    socket_b, _ = await subscribe(ws_url, bob, tid)
    async with socket_b:
        socket_a, _ = await subscribe(ws_url, alice, tid)
        async with socket_a:
            await socket_b.send(
                json.dumps(
                    {"type": "send_message", "thread_id": tid, "body": "hi Alice"}
                )
            )
            ack = await recvn(socket_b)
            assert ack["type"] == "ack"

            frame = await recvn(socket_a)
            assert frame["type"] == "message"
            assert frame["data"]["body"] == "hi Alice"


async def test_socket_send_to_foreign_thread_is_refused(
    live_server, ws_client, truncate_test_tables
):
    """The socket send path checks participation too, not just subscribe."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice, bob, tid, http_a, http_b = await connect_pair(ws_client)
    carol = await sign_up(ws_client(), "Carol")

    async with await websockets.connect(
        ws_url, additional_headers={"Cookie": cookie_header(carol["cookies"])}
    ) as socket:
        await socket.send(
            json.dumps({"type": "send_message", "thread_id": tid, "body": "intruder"})
        )
        reply = await recvn(socket)
        assert reply["type"] == "error"
        # The frame carries the underlying error's own code, not a blanket one.
        assert reply["code"] in ("forbidden", "not_found")

    # Nothing was written.
    history = http_a.get(f"/api/v1/threads/{tid}/messages").json()["items"]
    assert not any(m["body"] == "intruder" for m in history)


async def test_unsubscribe_stops_delivery(live_server, ws_client, truncate_test_tables):
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice, bob, tid, http_a, http_b = await connect_pair(ws_client)

    socket_b, _ = await subscribe(ws_url, bob, tid)
    async with socket_b:
        await socket_b.send(json.dumps({"type": "unsubscribe", "thread_id": tid}))
        await asyncio.sleep(0.2)

        http_b.post(
            f"/api/v1/threads/{tid}/messages",
            json={"body": "should not arrive"},
            headers=bob["csrf"],
        )
        assert await expect_silence(socket_b)


async def test_notification_is_pushed_to_the_recipient(
    live_server, ws_client, truncate_test_tables
):
    """Notifications reach the user's own socket with no subscribe — a
    server-push on their own topic."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    http_a, http_b = ws_client(), ws_client()
    alice = await sign_up(http_a, "Alice")
    bob = await sign_up(http_b, "Bob")
    await complete_profile(http_a, alice, role="software_developer")
    await complete_profile(http_b, bob)

    async with await websockets.connect(
        ws_url, additional_headers={"Cookie": cookie_header(bob["cookies"])}
    ) as socket:
        http_a.post(
            "/api/v1/connections", json={"receiver_id": bob["id"]}, headers=alice["csrf"]
        )
        frame = await recvn(socket)
        assert frame["type"] == "notification"
        assert "wants to connect" in frame["data"]["text"]
        assert frame["data"]["actor_id"] == alice["id"]


async def test_ping_pong(live_server, ws_client, truncate_test_tables):
    """Trivial liveness check for the client reconnect logic."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice = await sign_up(ws_client(), "Alice")

    async with await websockets.connect(
        ws_url, additional_headers={"Cookie": cookie_header(alice["cookies"])}
    ) as socket:
        await socket.send(json.dumps({"type": "ping"}))
        assert (await recvn(socket))["type"] == "pong"


async def test_malformed_frame_does_not_kill_the_socket(
    live_server, ws_client, truncate_test_tables
):
    """One bad frame must not take down a live demo."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice, bob, tid, http_a, http_b = await connect_pair(ws_client)

    socket_b, _ = await subscribe(ws_url, bob, tid)
    async with socket_b:
        # Not valid JSON. The server answers with an error frame and carries on.
        await socket_b.send("this is not json")
        assert (await recvn(socket_b))["type"] == "error"

        # A valid frame with an unknown type is simply ignored.
        await socket_b.send(json.dumps({"type": "nonsense"}))

        # Proof the socket is still alive after both.
        await socket_b.send(json.dumps({"type": "ping"}))
        assert (await recvn(socket_b))["type"] == "pong"


async def test_socket_send_validates_like_http(
    live_server, ws_client, truncate_test_tables
):
    """Rule 5 applies to the socket too. HTTP rejects an empty or >2000-character
    body; the send frame must not be the way round it."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice, bob, tid, http_a, http_b = await connect_pair(ws_client)

    socket_a, _ = await subscribe(ws_url, alice, tid)
    async with socket_a:
        # A JSON array is a frame, but not one this protocol speaks.
        await socket_a.send(json.dumps([1, 2, 3]))
        assert (await recvn(socket_a))["type"] == "error"

        await socket_a.send(
            json.dumps({"type": "send_message", "thread_id": tid, "body": "x" * 2001})
        )
        assert (await recvn(socket_a))["type"] == "error"

        # Whitespace-only is trimmed to empty and refused too.
        await socket_a.send(
            json.dumps({"type": "send_message", "thread_id": tid, "body": "   "})
        )
        assert (await recvn(socket_a))["type"] == "error"

        # Nothing was stored, and the socket still works.
        assert http_b.get(f"/api/v1/threads/{tid}/messages").json()["items"] == []
        await socket_a.send(json.dumps({"type": "ping"}))
        assert (await recvn(socket_a))["type"] == "pong"

        # The HTTP cap is inclusive: exactly 2000 characters is valid.
        await socket_a.send(
            json.dumps({"type": "send_message", "thread_id": tid, "body": "x" * 2000})
        )
        ack = await recvn(socket_a)
        assert ack["type"] == "ack"
        assert len(ack["data"]["body"]) == 2000


async def test_two_tabs_for_the_same_user_both_receive(
    live_server, ws_client, truncate_test_tables
):
    """The registry is per-user, so a second tab also gets the message. This is
    the multi-tab case that a session-scoped socket would break."""
    truncate_test_tables()
    _http_base, ws_url = live_server
    alice, bob, tid, http_a, http_b = await connect_pair(ws_client)

    first, _ = await subscribe(ws_url, alice, tid)
    second, _ = await subscribe(ws_url, alice, tid)
    async with first, second:
        http_b.post(
            f"/api/v1/threads/{tid}/messages", json={"body": "to both tabs"}, headers=bob["csrf"]
        )
        assert (await recvn(first))["data"]["body"] == "to both tabs"
        assert (await recvn(second))["data"]["body"] == "to both tabs"
