import base64
import json
from dataclasses import dataclass
from uuid import UUID

from app.web import ApiError

CANDIDATE_POOL = 200


@dataclass(frozen=True)
class MatchingWeights:
    complementary_role: int = 30
    shared_skill: int = 10
    max_shared_skill_points: int = 30
    shared_interest: int = 5
    max_shared_interest_points: int = 15
    same_course: int = 20


WEIGHTS = MatchingWeights()


@dataclass(frozen=True)
class ProfileView:
    user_id: UUID
    display_name: str
    role: str | None
    course_id: UUID | None
    course_name: str | None
    skill_ids: frozenset[UUID]
    skill_names: dict[UUID, str]
    interest_ids: frozenset[UUID]
    interest_names: dict[UUID, str]


@dataclass(frozen=True)
class MatchResult:
    score: int
    reasons: list[str]
    shared_skill_ids: list[UUID]
    shared_interest_ids: list[UUID]


def score_match(viewer: ProfileView, candidate: ProfileView) -> MatchResult:
    shared_skills = sorted(viewer.skill_ids & candidate.skill_ids, key=str)
    shared_interests = sorted(viewer.interest_ids & candidate.interest_ids, key=str)
    score = 0
    factors: list[tuple[int, str]] = []

    if viewer.role and candidate.role and viewer.role != candidate.role:
        score += WEIGHTS.complementary_role
        viewer_role = "software developer" if viewer.role == "software_developer" else "business developer"
        candidate_role = "software developer" if candidate.role == "software_developer" else "business developer"
        factors.append(
            (WEIGHTS.complementary_role, f"{candidate.display_name} is a {candidate_role}, complementing your {viewer_role} role.")
        )

    skill_points = min(len(shared_skills) * WEIGHTS.shared_skill, WEIGHTS.max_shared_skill_points)
    if shared_skills:
        score += skill_points
        names = ", ".join(candidate.skill_names[item] for item in shared_skills[:5])
        factors.append((skill_points, f"You both know {names}."))

    interest_points = min(
        len(shared_interests) * WEIGHTS.shared_interest,
        WEIGHTS.max_shared_interest_points,
    )
    if shared_interests:
        score += interest_points
        names = ", ".join(candidate.interest_names[item] for item in shared_interests[:3])
        factors.append((interest_points, f"Both interested in {names}."))

    if viewer.course_id is not None and viewer.course_id == candidate.course_id:
        score += WEIGHTS.same_course
        factors.append((WEIGHTS.same_course, f"Both on {candidate.course_name}."))

    factors.sort(key=lambda item: -item[0])
    reasons = [reason for _, reason in factors]
    if not reasons:
        reasons = ["Someone with skills that complement yours."]
    return MatchResult(score, reasons, shared_skills, shared_interests)


def encode_match_cursor(score: int, user_id: UUID) -> str:
    content = json.dumps({"score": score, "id": str(user_id)}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(content).decode().rstrip("=")


def decode_match_cursor(cursor: str) -> tuple[int, UUID]:
    try:
        content = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        value = json.loads(content)
        return int(value["score"]), UUID(value["id"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ApiError(422, "validation_error", "The page cursor is invalid.", {"cursor": "Use a cursor from the previous page."}) from exc
