"""Tests for OOLONG benchmark scoring functions.

These are fast unit tests for the scoring logic in oolong/run_oolong_and_pairs.py.
They do NOT run the benchmark or call any LLMs.
"""

import pytest

from oolong.run_oolong_and_pairs import score_oolong

# ---------------------------------------------------------------------------
# Existing behaviour that must be preserved
# ---------------------------------------------------------------------------


class TestScoreOolongExactMatch:
    def test_exact_label_match(self):
        assert score_oolong("Label: human being", "['human being']") == 1.0

    def test_wrong_label(self):
        assert score_oolong("Label: description and abstract concept", "['human being']") == 0.0

    def test_exact_comparison_match(self):
        """When pred is bare comparison phrase, exact match should work."""
        assert score_oolong("Answer: less common than", "['less common than']") == 1.0


# ---------------------------------------------------------------------------
# Bug 1: Numerical scoring — 0.75^|y - ŷ| per the OOLONG paper
# ---------------------------------------------------------------------------


class TestScoreOolongNumerical:
    def test_exact_numerical_match(self):
        assert score_oolong("Answer: 28", "[28]") == 1.0

    def test_off_by_one(self):
        assert score_oolong("Answer: 0", "[1]") == pytest.approx(0.75)

    def test_off_by_two(self):
        assert score_oolong("Answer: 3", "[1]") == pytest.approx(0.75**2)

    def test_wildly_wrong_numerical(self):
        """586 vs 28 — should be near zero but not exactly 0.0."""
        score = score_oolong("Answer: 586", "[28]")
        assert score > 0.0
        assert score < 0.01

    def test_numerical_gold_non_numerical_pred(self):
        """Non-numeric prediction against numeric gold should score 0."""
        assert score_oolong("Answer: many", "[28]") == 0.0


# ---------------------------------------------------------------------------
# Bug 2: Comparison phrase extraction from full-sentence answers
# ---------------------------------------------------------------------------


class TestScoreOolongComparisonExtraction:
    """The OOLONG questions ask for 'Answer: X is [relation] Y' format.
    Gold is just the relation (e.g. 'less common than').
    The scorer must extract the relation from the full sentence.
    """

    def test_less_common_in_sentence(self):
        pred = "Answer: numeric value is less common than abbreviation"
        gold = "['less common than']"
        assert score_oolong(pred, gold) == 1.0

    def test_more_common_in_sentence(self):
        pred = "Answer: numeric value is more common than description and abstract concept"
        gold = "['more common than']"
        assert score_oolong(pred, gold) == 1.0

    def test_same_frequency_in_sentence(self):
        pred = "Answer: human being is same frequency as location"
        gold = "['same frequency as']"
        assert score_oolong(pred, gold) == 1.0

    def test_wrong_comparison_in_sentence(self):
        """Pred says 'same frequency as' but gold is 'less common than'."""
        pred = "Answer: numeric value is same frequency as entity"
        gold = "['less common than']"
        assert score_oolong(pred, gold) == 0.0


# ---------------------------------------------------------------------------
# Bug 3: "User:" prefix not stripped
# ---------------------------------------------------------------------------


class TestScoreOolongUserPrefix:
    def test_user_prefix_stripped(self):
        assert score_oolong("User: 94706", "[94706]") == 1.0

    def test_user_prefix_wrong_value(self):
        assert score_oolong("User: 12345", "[94706]") == 0.0
