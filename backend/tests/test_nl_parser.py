"""
Unit tests for the natural-language parser.

Two layers:

1. Pure-function tests — exercise `parse_duration_expression` and
   `infer_energy_level` directly. No LLM, no network, fast and deterministic.

2. Integration tests — hit the real LLM via `parse_task`. These are marked
   with `@pytest.mark.integration` and skipped automatically when GROQ_API_KEY
   is not configured. Run with `pytest -m integration` once a key is set.
"""

import os

import pytest

from app.models.models import EnergyLevel, Flexibility, Priority
from app.services.nl_parser import (
    infer_energy_level,
    parse_duration_expression,
    parse_task,
)


# ============================================================================
# parse_duration_expression — pure function
# ============================================================================


class TestParseDurationExpression:
    """Cover the duration grammar including the upper-bound rule."""

    def test_minutes_simple(self):
        minutes, needs = parse_duration_expression("45 minutes")
        assert minutes == 45
        assert needs is False

    def test_minutes_short_form(self):
        minutes, needs = parse_duration_expression("30 mins")
        assert minutes == 30
        assert needs is False

    def test_hours_simple(self):
        minutes, needs = parse_duration_expression("2 hrs")
        assert minutes == 120
        assert needs is False

    def test_hours_singular(self):
        minutes, needs = parse_duration_expression("1 hour")
        assert minutes == 60
        assert needs is False

    def test_range_uses_upper_bound(self):
        # Upper bound, not midpoint.
        minutes, needs = parse_duration_expression("1 to 2 hours")
        assert minutes == 120
        assert needs is False

    def test_range_with_dash(self):
        minutes, needs = parse_duration_expression("30-45 minutes")
        assert minutes == 45
        assert needs is False

    def test_an_hour(self):
        minutes, needs = parse_duration_expression("an hour")
        assert minutes == 60
        assert needs is False

    def test_half_an_hour(self):
        minutes, needs = parse_duration_expression("half an hour")
        assert minutes == 30
        assert needs is False

    def test_empty_string_flags_clarification(self):
        minutes, needs = parse_duration_expression("")
        assert minutes == 30
        assert needs is True

    def test_garbage_input_flags_clarification(self):
        minutes, needs = parse_duration_expression("schedule a meeting later")
        assert minutes == 30
        assert needs is True

    def test_embedded_in_sentence(self):
        minutes, needs = parse_duration_expression("I need 45 minutes for this")
        assert minutes == 45
        assert needs is False

    def test_decimal_hours(self):
        minutes, needs = parse_duration_expression("1.5 hours")
        assert minutes == 90
        assert needs is False


# ============================================================================
# infer_energy_level — pure function
# ============================================================================


class TestInferEnergyLevel:
    """Verify keyword routing for the energy-level fallback."""

    @pytest.mark.parametrize("title", ["gym", "morning run", "weight lifting", "yoga session"])
    def test_physical_keywords_map_to_high(self, title):
        assert infer_energy_level(title) == EnergyLevel.HIGH

    @pytest.mark.parametrize("title", ["study calculus", "code review", "write essay", "debug auth"])
    def test_focused_cognitive_maps_to_high(self, title):
        assert infer_energy_level(title) == EnergyLevel.HIGH

    @pytest.mark.parametrize("title", ["check email", "buy groceries", "do laundry", "reply to texts"])
    def test_admin_keywords_map_to_low(self, title):
        assert infer_energy_level(title) == EnergyLevel.LOW

    @pytest.mark.parametrize("title", ["catch up with mom", "weekly review", "team sync"])
    def test_unknown_maps_to_medium(self, title):
        assert infer_energy_level(title) == EnergyLevel.MEDIUM

    def test_high_keyword_wins_when_both_present(self):
        # Title contains a Low keyword but also a High keyword — High wins.
        assert infer_energy_level("send email then go to gym") == EnergyLevel.HIGH

    def test_case_insensitive(self):
        assert infer_energy_level("GYM") == EnergyLevel.HIGH

    def test_word_boundary(self):
        # "code" should not fire on "discord" — protects against substring matches.
        assert infer_energy_level("discord catchup") == EnergyLevel.MEDIUM

    def test_determinism(self):
        # Property 12: same input always returns the same value.
        for _ in range(5):
            assert infer_energy_level("study physics") == EnergyLevel.HIGH


# ============================================================================
# parse_task — integration tests (real LLM)
# ============================================================================


_NO_KEY = not os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY", "").startswith("your_")


@pytest.mark.integration
@pytest.mark.skipif(_NO_KEY, reason="GROQ_API_KEY not configured")
class TestParseTaskIntegration:
    """End-to-end checks against a real LLM provider."""

    async def test_extracts_simple_task(self):
        result = await parse_task("schedule gym tomorrow at 7am for 90 minutes")
        assert result.has_task_intent is True
        assert "gym" in result.title.lower()
        assert result.duration_minutes == 90

    async def test_greeting_has_no_task_intent(self):
        result = await parse_task("hello there")
        assert result.has_task_intent is False

    async def test_contradictory_message_is_ambiguous(self):
        result = await parse_task("urgent but whenever, study calculus 2 hours")
        assert result.is_ambiguous is True
        assert result.clarifying_question is not None
        assert len(result.clarifying_question) > 0

    async def test_defaults_applied_when_unspecified(self):
        result = await parse_task("add a quick task to call mom for 15 minutes")
        assert result.has_task_intent is True
        # priority and flexibility should fall back to defaults
        assert result.priority == Priority.MEDIUM
        assert result.flexibility == Flexibility.FLEXIBLE
