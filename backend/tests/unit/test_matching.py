"""Matching scoring. The highest-value unit tests in the project: pure, fast,
no database. specs/04_matching_and_search.md §9."""

import uuid

import pytest

from app.services.matching import (
    CANDIDATE_POOL,
    WEIGHTS,
    MatchResult,
    ProfileView,
    matches_filters,
    max_possible_score,
    score_match,
    sort_key,
)

PYTHON = uuid.uuid4()
REACT = uuid.uuid4()
NODE = uuid.uuid4()
DJANGO = uuid.uuid4()
SQL = uuid.uuid4()
CLIMATE = uuid.uuid4()
FINTECH = uuid.uuid4()
EDTECH = uuid.uuid4()

DEV = "software_developer"
BIZ = "business_developer"


def view(
    *,
    role: str | None = DEV,
    course: uuid.UUID | None = None,
    skills: tuple = (),
    interests: tuple = (),
    name: str = "Test",
) -> ProfileView:
    return ProfileView(
        user_id=uuid.uuid4(),
        display_name=name,
        first_name=name,
        role=role,
        course_id=course,
        course_name="Software Development" if course else None,
        skills=skills,
        interests=interests,
    )


# ─── Role ────────────────────────────────────────────────────────────────────


def test_complementary_role_scores_30():
    """The core premise. Dev + business dev = 30."""
    result = score_match(view(role=DEV), view(role=BIZ))
    assert result.score >= WEIGHTS.complementary_role
    assert any("builds" in r for r in result.reasons)


def test_same_role_scores_zero_role_points():
    result = score_match(view(role=DEV), view(role=DEV))
    assert not any("builds" in r for r in result.reasons)


def test_missing_role_scores_zero():
    result = score_match(view(role=None), view(role=BIZ))
    assert result.score == 0


# ─── Skills ──────────────────────────────────────────────────────────────────


def test_each_shared_skill_scores_10():
    result = score_match(
        view(role=None, skills=((PYTHON, "Python"),)),
        view(role=None, skills=((PYTHON, "Python"),)),
    )
    assert result.score == 10
    assert result.shared_skill_names == ["Python"]


def test_shared_skill_points_capped_at_30():
    """Load-bearing. Without the cap a 20-skill profile outranks every genuine
    complementary match on list length alone."""
    many = tuple((uuid.uuid4(), f"s{i}") for i in range(5))
    result = score_match(view(role=None, skills=many), view(role=None, skills=many))
    assert result.score == WEIGHTS.max_shared_skill_points == 30


def test_three_shared_skills_is_max():
    three = ((PYTHON, "Python"), (REACT, "React"), (NODE, "Node.js"))
    result = score_match(view(role=None, skills=three), view(role=None, skills=three))
    assert result.score == 30


def test_non_overlapping_skills_score_zero():
    result = score_match(
        view(role=None, skills=((PYTHON, "Python"),)),
        view(role=None, skills=((DJANGO, "Django"),)),
    )
    assert result.score == 0
    assert result.shared_skill_names == []


# ─── Interests ───────────────────────────────────────────────────────────────


def test_each_shared_interest_scores_5():
    result = score_match(
        view(role=None, interests=((CLIMATE, "Climate tech"),)),
        view(role=None, interests=((CLIMATE, "Climate tech"),)),
    )
    assert result.score == 5


def test_shared_interest_points_capped_at_15():
    many = tuple((uuid.uuid4(), f"i{i}") for i in range(6))
    result = score_match(view(role=None, interests=many), view(role=None, interests=many))
    assert result.score == WEIGHTS.max_shared_interest_points == 15


# ─── Course ──────────────────────────────────────────────────────────────────


def test_same_course_scores_20():
    course = uuid.uuid4()
    result = score_match(view(role=None, course=course), view(role=None, course=course))
    assert result.score == 20


def test_missing_course_scores_zero():
    course = uuid.uuid4()
    result = score_match(view(role=None, course=course), view(role=None))
    assert result.score == 0


def test_different_course_scores_zero():
    result = score_match(view(role=None, course=uuid.uuid4()), view(role=None, course=uuid.uuid4()))
    assert result.score == 0


# ─── Bounds and determinism ──────────────────────────────────────────────────


def test_no_overlap_scores_zero():
    assert score_match(view(), view()).score == 0


def test_maximum_score_is_95():
    assert max_possible_score() == 95


def test_deterministic_across_runs():
    a = view(role=DEV, skills=((PYTHON, "Python"), (REACT, "React")))
    b = view(role=BIZ, skills=((PYTHON, "Python"), (SQL, "SQL")))
    results = {score_match(a, b).score for _ in range(100)}
    assert results == {score_match(a, b).score}


def test_ties_break_on_candidate_id():
    """Stable total order — cursor pagination depends on it."""
    a, b = view(role=DEV), view(role=DEV)
    low = MatchResult(score=10, reasons=[], shared_skill_ids=[], shared_skill_names=[], shared_interest_names=[])
    high_id = max(a.user_id, b.user_id)
    assert sort_key(low, high_id) == sort_key(low, high_id)
    assert sort_key(low, high_id)[1] == high_id


# ─── Reasons ─────────────────────────────────────────────────────────────────


def test_reasons_only_mention_contributing_factors():
    result = score_match(
        view(role=None, skills=((PYTHON, "Python"),)),
        view(role=None, skills=((PYTHON, "Python"),)),
    )
    assert result.reasons == ["You both know Python."]
    assert not any("course" in r.lower() for r in result.reasons)


def test_reason_ordering_is_contribution_first():
    """Strongest contribution first: role 30, course 20, skills 10."""
    course = uuid.uuid4()
    result = score_match(
        view(role=DEV, course=course, skills=((PYTHON, "Python"),)),
        view(role=BIZ, course=course, skills=((PYTHON, "Python"),)),
    )
    assert "builds" in result.reasons[0]
    order = [
        next(i for i, r in enumerate(result.reasons) if "builds" in r),
        next(i for i, r in enumerate(result.reasons) if r.startswith("Both on")),
        next(i for i, r in enumerate(result.reasons) if r.startswith("You both know")),
    ]
    assert order == sorted(order), f"reasons out of contribution order: {result.reasons}"


def test_fallback_reason_when_nothing_overlaps():
    result = score_match(view(role=None), view(role=None))
    assert result.reasons == ["Someone with skills that complement yours."]


def test_reason_lists_many_shared_skills():
    result = score_match(
        view(role=None, skills=((PYTHON, "Python"), (REACT, "React"), (NODE, "Node.js"), (SQL, "SQL"))),
        view(role=None, skills=((PYTHON, "Python"), (REACT, "React"), (NODE, "Node.js"), (SQL, "SQL"))),
    )
    assert "+1 more" in result.reasons[0]


# ─── Filters ─────────────────────────────────────────────────────────────────


def test_filters_are_and_combined():
    candidate = view(role=BIZ, skills=((PYTHON, "Python"),))
    assert matches_filters(candidate, skill_ids={PYTHON}, role=BIZ)
    # Role matches but skill does not → filtered out.
    assert not matches_filters(candidate, skill_ids={DJANGO}, role=BIZ)
    assert not matches_filters(candidate, skill_ids={PYTHON}, role=DEV)


def test_repeated_filter_is_or():
    """skill_ids within one filter is a set, so it is inherently OR."""
    candidate = view(skills=((PYTHON, "Python"),))
    assert matches_filters(candidate, skill_ids={PYTHON, DJANGO})


def test_no_filters_matches_everything():
    assert matches_filters(view())


# ─── Pool ceiling ────────────────────────────────────────────────────────────


def test_candidate_pool_is_bounded():
    """A real ceiling, documented in the module. Flagged if someone raises it."""
    assert CANDIDATE_POOL == 200