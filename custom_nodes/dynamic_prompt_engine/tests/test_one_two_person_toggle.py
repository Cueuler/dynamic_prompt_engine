"""Tests for OneTwoPersonToggle and TextPoolRouter."""

import pytest
import sys
import os

# Add the parent directory so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prompt_engine_nodes import (
    OneTwoPersonToggle,
    TextPoolRouter,
    nonempty_text,
    validate_text_input,
    derive_stream_seed,
    join_prompt_parts,
)


# ---------------------------------------------------------------------------
# OneTwoPersonToggle
# ---------------------------------------------------------------------------

def test_random_mode_deterministic():
    toggle = OneTwoPersonToggle()
    # Same seed, same branch
    result1 = toggle.select_section(
        mode="Random",
        one_label="1girl",
        two_label="2girls",
        seed=42,
        one_character="Alice",
        two_or_more_characters="Bob, Charlie",
    )
    result2 = toggle.select_section(
        mode="Random",
        one_label="1girl",
        two_label="2girls",
        seed=42,
        one_character="Alice",
        two_or_more_characters="Bob, Charlie",
    )
    assert result1[2] == result2[2]  # branch
    assert result1[0] == result2[0]  # text


def test_different_seeds_can_produce_different_random_branches():
    toggle = OneTwoPersonToggle()
    branches = set()
    for s in range(100):
        result = toggle.select_section(
            mode="Random",
            one_label="1girl",
            two_label="2girls",
            seed=s,
            one_character="test",
            two_or_more_characters="test2",
        )
        branches.add(result[2])
    # It's *possible* that all 100 seeds give the same branch, but very unlikely.
    # We at least verify that both 0 and 1 are possible.
    if len(branches) == 1:
        # If only one branch appears, try a larger range
        branches = set()
        for s in range(10000):
            result = toggle.select_section(
                mode="Random",
                one_label="1girl",
                two_label="2girls",
                seed=s,
                one_character="test",
                two_or_more_characters="test2",
            )
            branches.add(result[2])
            if len(branches) == 2:
                break
    assert 0 in branches
    assert 1 in branches


def test_onegirl_always_returns_branch_0():
    toggle = OneTwoPersonToggle()
    for s in range(10):
        result = toggle.select_section(
            mode="1girl",
            one_label="1girl",
            two_label="2girls",
            seed=s,
            one_character="Alice",
            two_or_more_characters="Bob",
        )
        assert result[2] == 0


def test_twogirls_always_returns_branch_1():
    toggle = OneTwoPersonToggle()
    for s in range(10):
        result = toggle.select_section(
            mode="2girls",
            one_label="1girl",
            two_label="2girls",
            seed=s,
            one_character="Alice",
            two_or_more_characters="Bob",
        )
        assert result[2] == 1


def test_branch_output_exact():
    toggle = OneTwoPersonToggle()
    result = toggle.select_section(
        mode="1girl",
        one_label="1girl",
        two_label="2girls",
        seed=0,
        one_character="char",
        two_or_more_characters="chars",
    )
    assert isinstance(result[2], int)
    assert result[2] in (0, 1)


def test_one_person_output_uses_only_one_character():
    toggle = OneTwoPersonToggle()
    result = toggle.select_section(
        mode="1girl",
        one_label="1girl",
        two_label="2girls",
        seed=0,
        one_character="Alice",
        two_or_more_characters="Bob",
    )
    text = result[0]
    assert "Alice" in text
    assert "Bob" not in text


def test_two_person_output_includes_both():
    toggle = OneTwoPersonToggle()
    result = toggle.select_section(
        mode="2girls",
        one_label="1girl",
        two_label="2girls",
        seed=0,
        one_character="Alice",
        two_or_more_characters="Bob",
    )
    text = result[0]
    assert "Alice" in text
    assert "Bob" in text


def test_missing_one_label_raises():
    toggle = OneTwoPersonToggle()
    with pytest.raises(ValueError, match="one_label"):
        toggle.select_section(
            mode="1girl",
            one_label="",
            two_label="2girls",
            seed=0,
            one_character="Alice",
            two_or_more_characters="Bob",
        )


def test_missing_two_label_raises():
    toggle = OneTwoPersonToggle()
    with pytest.raises(ValueError, match="two_label"):
        toggle.select_section(
            mode="1girl",
            one_label="1girl",
            two_label="   ",
            seed=0,
            one_character="Alice",
            two_or_more_characters="Bob",
        )


def test_missing_one_character_raises():
    toggle = OneTwoPersonToggle()
    with pytest.raises(ValueError, match="one_character"):
        toggle.select_section(
            mode="1girl",
            one_label="1girl",
            two_label="2girls",
            seed=0,
            one_character="",
            two_or_more_characters="Bob",
        )


def test_missing_two_or_more_characters_raises_even_when_onegirl():
    toggle = OneTwoPersonToggle()
    with pytest.raises(ValueError, match="two_or_more_characters"):
        toggle.select_section(
            mode="1girl",
            one_label="1girl",
            two_label="2girls",
            seed=0,
            one_character="Alice",
            two_or_more_characters="",
        )


def test_default_seed_succeeds():
    toggle = OneTwoPersonToggle()
    # seed=0 is the default; unconnected seed is supplied as 0 by ComfyUI
    result = toggle.select_section(
        mode="1girl",
        one_label="1girl",
        two_label="2girls",
        seed=0,
        one_character="Alice",
        two_or_more_characters="Bob",
    )
    assert result[1] == 0


# ---------------------------------------------------------------------------
# TextPoolRouter strictness
# ---------------------------------------------------------------------------

def test_text_pool_router_missing_selected_input_raises():
    router = TextPoolRouter()
    # Only input_0 is connected, request input_1
    with pytest.raises(ValueError, match="input_1"):
        router.route_text(index=1, input_0="hello")


def test_text_pool_router_empty_selected_input_raises():
    router = TextPoolRouter()
    with pytest.raises(ValueError, match="input_0"):
        router.route_text(index=0, input_0="")


def test_text_pool_router_no_fallback():
    router = TextPoolRouter()
    # input_0 is empty, input_1 is non‑empty, but index=0 should fail
    with pytest.raises(ValueError):
        router.route_text(index=0, input_0="", input_1="fallback")
    # index=1 should succeed
    result = router.route_text(index=1, input_0="", input_1="fallback")
    assert result[0] == "fallback"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_validate_text_input_raises_for_none():
    with pytest.raises(ValueError):
        validate_text_input(None, "test", "TestNode")


def test_validate_text_input_raises_for_empty():
    with pytest.raises(ValueError):
        validate_text_input("", "test", "TestNode")


def test_validate_text_input_raises_for_whitespace():
    with pytest.raises(ValueError):
        validate_text_input("   ", "test", "TestNode")


def test_validate_text_input_returns_cleaned_text():
    result = validate_text_input("  hello  ", "test", "TestNode")
    assert result == "hello"


def test_derive_stream_seed_consistent():
    s1 = derive_stream_seed(42, "node:abc")
    s2 = derive_stream_seed(42, "node:abc")
    assert s1 == s2


def test_join_prompt_parts_hygiene():
    result = join_prompt_parts(" a , b ", " , c ")
    assert result == "a, b, c, "
