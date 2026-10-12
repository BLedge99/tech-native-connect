from uuid import UUID

import pytest

from app.services.connections import transition_status
from app.services.matching import ProfileView, decode_match_cursor, encode_match_cursor, score_match
from app.services.profiles import detect_photo_type, profile_is_complete
from app.web import ApiError


def view(user_id: int, role: str, skills: dict[UUID, str], interests: dict[UUID, str], course_id: UUID) -> ProfileView:
    return ProfileView(
        user_id=UUID(int=user_id),
        display_name=f"User {user_id}",
        role=role,
        course_id=course_id,
        course_name="Software Development",
        skill_ids=frozenset(skills),
        skill_names=skills,
        interest_ids=frozenset(interests),
        interest_names=interests,
    )


def test_complementary_role_and_shared_factors_have_deterministic_explanation():
    python = UUID(int=100)
    react = UUID(int=101)
    climate = UUID(int=200)
    course = UUID(int=300)
    viewer = view(1, "software_developer", {python: "Python", react: "React"}, {climate: "Climate tech"}, course)
    candidate = view(2, "business_developer", {python: "Python", react: "React"}, {climate: "Climate tech"}, course)

    result = score_match(viewer, candidate)

    assert result.score == 75
    assert result.reasons == [
        "User 2 is a business developer, complementing your software developer role.",
        "You both know Python, React.",
        "Both on Software Development.",
        "Both interested in Climate tech.",
    ]
    assert result.shared_skill_ids == [python, react]


def test_matching_caps_skill_and_interest_contributions_and_same_role_is_not_excluded():
    skills = {UUID(int=index): f"Skill {index}" for index in range(1, 7)}
    interests = {UUID(int=index + 100): f"Interest {index}" for index in range(1, 6)}
    course = UUID(int=400)
    result = score_match(
        view(1, "software_developer", skills, interests, course),
        view(2, "software_developer", skills, interests, course),
    )

    assert result.score == 65
    assert result.shared_skill_ids == sorted(skills, key=str)
    assert result.shared_interest_ids == sorted(interests, key=str)
    assert "complementing" not in " ".join(result.reasons)


@pytest.mark.parametrize(
    ("role", "skill_count", "complete"),
    [
        ("software_developer", 1, True),
        ("business_developer", 1, True),
        ("software_developer", 0, False),
        (None, 1, False),
        (None, 0, False),
    ],
)
def test_profile_completion_requires_both_role_and_skill(role, skill_count, complete):
    assert profile_is_complete(role, skill_count) is complete


def test_photo_mime_is_detected_from_file_signature():
    assert detect_photo_type(b"\xff\xd8\xffpayload") == "image/jpeg"
    assert detect_photo_type(b"\x89PNG\r\n\x1a\npayload") == "image/png"
    assert detect_photo_type(b"RIFF0000WEBPpayload") == "image/webp"
    assert detect_photo_type(b"not-an-image") is None


def test_match_cursor_round_trip_and_invalid_input():
    user_id = UUID(int=789)
    assert decode_match_cursor(encode_match_cursor(45, user_id)) == (45, user_id)
    with pytest.raises(ApiError) as error:
        decode_match_cursor("not-a-cursor")
    assert error.value.code == "validation_error"


@pytest.mark.parametrize(
    ("status", "action", "actor", "expected_status", "expected_code"),
    [
        ("pending", "accept", "receiver", "accepted", None),
        ("pending", "decline", "receiver", "declined", None),
        ("pending", "accept", "sender", None, "not_receiver"),
        ("accepted", "accept", "receiver", None, "already_responded"),
        ("accepted", "decline", "receiver", None, "already_responded"),
        ("declined", "accept", "receiver", None, "already_responded"),
        ("declined", "decline", "receiver", None, "already_responded"),
        ("pending", "withdraw", "receiver", None, "validation_error"),
        ("pending", "accept", "outsider", None, "not_found"),
    ],
)
def test_connection_transition_table(status, action, actor, expected_status, expected_code):
    sender = UUID(int=1)
    receiver = UUID(int=2)
    actor_id = {"sender": sender, "receiver": receiver, "outsider": UUID(int=3)}[actor]

    if expected_code:
        with pytest.raises(ApiError) as error:
            transition_status(status, action, actor_id, sender, receiver)
        assert error.value.code == expected_code
    else:
        assert transition_status(status, action, actor_id, sender, receiver) == expected_status
