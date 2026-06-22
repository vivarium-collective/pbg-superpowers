"""Tests for the framework house plotting style (pbg_superpowers.plot_style)."""
import numpy as np
import pytest

from pbg_superpowers.plot_style import stitch_minutes, gen_boundaries, wrap


# --------------------------------------------------------------------------- #
# stitch_minutes: per-generation global_time RESETS -> cumulative minutes
# --------------------------------------------------------------------------- #
def test_stitch_minutes_lays_generations_sequentially():
    # Two generations, each emits seconds resetting to 0; gen 0 spans 0..120s,
    # gen 1 spans 0..60s. Stitched lineage time (minutes) must be monotonic.
    generation = [0, 0, 0, 1, 1]
    global_time = [0.0, 60.0, 120.0, 0.0, 60.0]
    t_min = stitch_minutes(generation, global_time)
    # gen 0: 0, 1, 2 min. gen 1 offset by gen-0 max (120s=2min): 2, 3 min.
    assert t_min == pytest.approx([0.0, 1.0, 2.0, 2.0, 3.0])
    assert np.all(np.diff(t_min) >= 0)  # monotonic non-decreasing


def test_stitch_minutes_single_generation_is_just_seconds_over_60():
    t_min = stitch_minutes([0, 0, 0], [0.0, 30.0, 90.0])
    assert t_min == pytest.approx([0.0, 0.5, 1.5])


def test_stitch_minutes_returns_ndarray_aligned_to_input():
    out = stitch_minutes([0, 1], [0.0, 0.0])
    assert isinstance(out, np.ndarray)
    assert out.shape == (2,)


# --------------------------------------------------------------------------- #
# gen_boundaries: detect where the generation index increments
# --------------------------------------------------------------------------- #
def test_gen_boundaries_detects_increment_points():
    generation = [0, 0, 0, 1, 1]
    t_min = [0.0, 1.0, 2.0, 2.0, 3.0]
    # New generation begins at the first gen-1 sample -> t_min == 2.0.
    assert gen_boundaries(generation, t_min) == pytest.approx([2.0])


def test_gen_boundaries_multiple_generations():
    generation = [0, 1, 1, 2]
    t_min = [0.0, 1.0, 2.0, 3.0]
    assert gen_boundaries(generation, t_min) == pytest.approx([1.0, 3.0])


def test_gen_boundaries_single_generation_is_empty():
    assert gen_boundaries([0, 0, 0], [0.0, 1.0, 2.0]) == []


# --------------------------------------------------------------------------- #
# wrap: word-boundary <br> wrapping
# --------------------------------------------------------------------------- #
def test_wrap_breaks_at_word_boundary():
    text = "alpha beta gamma delta"
    # width 11 -> "alpha beta" (10) fits; adding " gamma" exceeds -> new line.
    wrapped = wrap(text, width=11)
    lines = wrapped.split("<br>")
    assert lines == ["alpha beta", "gamma delta"]
    # Never splits inside a word.
    for line in lines:
        assert "alph" not in line or "alpha" in line


def test_wrap_short_text_is_unchanged():
    assert wrap("short subtitle", width=78) == "short subtitle"


def test_wrap_uses_br_separator_and_preserves_all_words():
    text = "one two three four five six seven eight nine ten"
    wrapped = wrap(text, width=15)
    assert "<br>" in wrapped
    # Round-trip: joining the lines back recovers the original word sequence.
    assert wrapped.replace("<br>", " ").split() == text.split()
