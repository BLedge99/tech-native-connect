"""Matching. Pure functions, no I/O. specs/04_matching_and_search.md §3.

Because score_match never touches a database, its unit tests are the fastest and
highest-value tests in the project. Keep it that way.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

# (id, name) pairs, kept in sync order. Deriving names from ids this way means
# the caller supplies one ordered list rather than a set plus a parallel tuple.
SkillRef = tuple[uuid.UUID, str]


@dataclass(frozen=True)
class MatchingWeights:
    """One number, one place. See specs/04 §2 for the rationale."""

    complementary_role: int = 30
    shared_skill: int = 10
    max_shared_skill_points: int = 30
    shared_interest: int = 5
    max_shared_interest_points: int = 15
    same_course: int = 20


WEIGHTS = MatchingWeights()

# Scoring cannot happen in SQL (the caps and reason building are Python), so the
# candidate pool must be bounded.
# ponytail: pool capped at 200 rows. Fine for a bootcamp cohort. Upgrade path if
# a cohort exceeds ~500: a precomputed score column refreshed on profile update,
# then paginate in SQL.
CANDIDATE_POOL = 200


@dataclass(frozen=True)
class ProfileView:
    """Flattened projection. Deliberately not an ORM model — taking one would
    couple this function to the schema and force a database into its tests."""

    user_id: uuid.UUID
    display_name: str
    first_name: str
    role: str | None
    course_id: uuid.UUID | None
    course_name: str | None = None
    bio: str | None = None
    looking_for: str | None = None
    has_photo: bool = False
    skills: tuple[SkillRef, ...] = ()
    interests: tuple[SkillRef, ...] = ()

    @property
    def skill_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(s for s, _ in self.skills)

    @property
    def interest_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(i for i, _ in self.interests)


@dataclass(frozen=True)
class MatchResult:
    score: int
    reasons: list[str]
    shared_skill_ids: list[uuid.UUID]
    shared_skill_names: list[str]
    shared_interest_names: list[str]


def _join(names: list[str], limit: int = 3) -> str:
    if len(names) <= limit:
        return ", ".join(names)
    return ", ".join(names[:limit]) + f" +{len(names) - limit} more"


def _names_for(refs: tuple[SkillRef, ...], ids: list[uuid.UUID]) -> list[str]:
    wanted = set(ids)
    return [name for ref_id, name in refs if ref_id in wanted]


def score_match(viewer: ProfileView, candidate: ProfileView) -> MatchResult:
    """Deterministic. Same inputs, same output, always. Pure."""
    reasons: list[tuple[int, str]] = []
    total = 0

    # 1. Complementary role — the core premise, highest weight.
    if viewer.role and candidate.role and viewer.role != candidate.role:
        total += WEIGHTS.complementary_role
        reasons.append(
            (
                WEIGHTS.complementary_role,
                f"You're both developers — {candidate.first_name} builds, you find the customers.",
            )
        )

    # 2. Shared skills, capped. Without the cap a 20-skill profile outranks every
    #    genuine complementary match on list length alone.
    shared_skill_ids = sorted(viewer.skill_ids & candidate.skill_ids)
    shared_skill_names = _names_for(candidate.skills, shared_skill_ids)
    skill_points = min(
        len(shared_skill_ids) * WEIGHTS.shared_skill, WEIGHTS.max_shared_skill_points
    )
    total += skill_points
    if shared_skill_ids:
        reasons.append((skill_points, f"You both know {_join(shared_skill_names)}."))

    # 3. Shared interests, capped.
    shared_interest_ids = sorted(viewer.interest_ids & candidate.interest_ids)
    shared_interest_names = _names_for(candidate.interests, shared_interest_ids)
    interest_points = min(
        len(shared_interest_ids) * WEIGHTS.shared_interest,
        WEIGHTS.max_shared_interest_points,
    )
    total += interest_points
    if shared_interest_ids:
        reasons.append(
            (interest_points, f"Both interested in {_join(shared_interest_names)}.")
        )

    # 4. Same course.
    if viewer.course_id and candidate.course_id and viewer.course_id == candidate.course_id:
        total += WEIGHTS.same_course
        reasons.append((WEIGHTS.same_course, f"Both on {candidate.course_name or 'the same course'}."))

    if not reasons:
        reasons.append((0, "Someone with skills that complement yours."))

    # Strongest contribution first, then alphabetical, so ties are stable.
    reasons.sort(key=lambda pair: (-pair[0], pair[1]))

    return MatchResult(
        score=total,
        reasons=[text for _, text in reasons],
        shared_skill_ids=shared_skill_ids,
        shared_skill_names=shared_skill_names,
        shared_interest_names=shared_interest_names,
    )


def sort_key(result: MatchResult, candidate_id: uuid.UUID) -> tuple[int, uuid.UUID]:
    """Stable total order. A fuzzy tiebreak would let page 2 repeat rows from
    page 1 — cursor pagination depends on this."""
    return (-result.score, candidate_id)


def max_possible_score() -> int:
    return (
        WEIGHTS.complementary_role
        + WEIGHTS.max_shared_skill_points
        + WEIGHTS.max_shared_interest_points
        + WEIGHTS.same_course
    )


def matches_filters(
    candidate: ProfileView,
    *,
    skill_ids: set[uuid.UUID] | None = None,
    role: str | None = None,
    course_id: uuid.UUID | None = None,
    interest_ids: set[uuid.UUID] | None = None,
) -> bool:
    """AND across filters, OR within one filter. Specs/04 §6."""
    if skill_ids and not (skill_ids & candidate.skill_ids):
        return False
    if interest_ids and not (interest_ids & candidate.interest_ids):
        return False
    if role and candidate.role != role:
        return False
    if course_id and candidate.course_id != course_id:
        return False
    return True


__all__ = [
    "MatchingWeights",
    "WEIGHTS",
    "CANDIDATE_POOL",
    "SkillRef",
    "ProfileView",
    "MatchResult",
    "score_match",
    "sort_key",
    "matches_filters",
    "max_possible_score",
]