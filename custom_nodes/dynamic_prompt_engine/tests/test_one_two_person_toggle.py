"""Tests for BranchToggle and BranchSelect2."""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prompt_engine_nodes import (
    BranchToggle,
    BranchSelect2,
    TagJoin,
    validate_text_input,
    derive_stream_seed,
    join_prompt_parts,
)


def _toggle(mode="1girl", seed=0, branch_1="Alice", branch_2="Bob"):
    return BranchToggle().select_section(
        mode=mode,
        seed=seed,
        branch_1=branch_1,
        branch_2=branch_2,
    )


def test_random_mode_deterministic():
    result1 = _toggle(mode="Random", seed=42, branch_1="Alice", branch_2="Bob, Charlie")
    result2 = _toggle(mode="Random", seed=42, branch_1="Alice", branch_2="Bob, Charlie")
    assert result1[2] == result2[2]
    assert result1[0] == result2[0]


def test_different_seeds_can_produce_different_random_branches():
    branches = {_toggle(mode="Random", seed=s, branch_1="test", branch_2="test2")[2] for s in range(100)}
    if len(branches) == 1:
        branches = set()
        for s in range(10000):
            branches.add(_toggle(mode="Random", seed=s, branch_1="test", branch_2="test2")[2])
            if len(branches) == 2:
                break
    assert 0 in branches
    assert 1 in branches


def test_onegirl_always_returns_branch_0():
    for s in range(10):
        assert _toggle(mode="1girl", seed=s)[2] == 0


def test_twogirls_always_returns_branch_1():
    for s in range(10):
        assert _toggle(mode="2girls", seed=s)[2] == 1


def test_branch_output_exact():
    result = _toggle(mode="1girl", seed=0, branch_1="char", branch_2="chars")
    assert isinstance(result[2], int)
    assert result[2] in (0, 1)


def test_one_person_output_uses_only_branch_1():
    text = _toggle(mode="1girl", branch_1="Alice", branch_2="Bob")[0]
    assert text.startswith("1girl")
    assert "Alice" in text
    assert "Bob" not in text


def test_two_person_output_includes_both_branches():
    text = _toggle(mode="2girls", branch_1="Alice", branch_2="Bob")[0]
    assert text.startswith("2girls")
    assert "Alice" in text
    assert "Bob" in text


def test_missing_branch_1_raises():
    with pytest.raises(ValueError, match="branch_1"):
        _toggle(mode="1girl", branch_1="", branch_2="Bob")


def test_missing_branch_2_raises_even_when_onegirl():
    with pytest.raises(ValueError, match="branch_2"):
        _toggle(mode="1girl", branch_1="Alice", branch_2="")


def test_default_seed_succeeds():
    assert _toggle(mode="1girl", seed=0)[1] == 0


def test_branch_select2_picks_solo_or_duo():
    select = BranchSelect2()
    assert select.select(0, solo="solo path", duo="duo path")[0] == "solo path"
    assert select.select(1, solo="solo path", duo="duo path")[0] == "duo path"


def test_branch_select2_empty_solo_omits_char2():
    select = BranchSelect2()
    assert select.select(0, solo="", duo="jacket, boots")[0] == ""
    assert select.select(1, solo="", duo="jacket, boots")[0] == "jacket, boots"


def test_branch_select2_rejects_invalid_branch():
    with pytest.raises(ValueError, match="branch"):
        BranchSelect2().select(2, solo="a", duo="b")


def test_same_branch_routes_section_bundles_consistently():
    select = BranchSelect2()
    solo = TagJoin().join_tags(
        text="", tag_0="standing", tag_1="waving", tag_2="hands at sides"
    )["result"][0]
    duo = TagJoin().join_tags(
        text="", tag_0="sitting", tag_1="talking", tag_2="holding hands"
    )["result"][0]
    char1_clothes = TagJoin().join_tags(
        text="", tag_0="school uniform", tag_1="ribbon", tag_2="loafers"
    )["result"][0]
    char2_section = TagJoin().join_tags(
        text="", tag_0="tall", tag_1="jacket", tag_2="boots"
    )["result"][0]

    for mode, expected_branch in [("1girl", 0), ("2girls", 1)]:
        text, _seed, branch = _toggle(mode=mode, seed=0)
        assert branch == expected_branch
        interaction = select.select(branch, solo=solo, duo=duo)[0]
        char2 = select.select(branch, solo="", duo=char2_section)[0]
        final = TagJoin().join_tags(
            text="",
            tag_0="masterpiece",
            tag_1=text,
            tag_2=interaction,
            tag_3="slender",
            tag_4=char1_clothes,
            tag_5=char2,
            tag_6="park",
            tag_7="soft daylight",
        )["result"][0]
        assert "school uniform" in final
        if expected_branch == 0:
            assert "holding hands" not in final
            assert "Bob" not in final
            assert "jacket" not in final
        else:
            assert "holding hands" in final
            assert "Bob" in final
            assert "jacket" in final


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
    assert validate_text_input("  hello  ", "test", "TestNode") == "hello"


def test_derive_stream_seed_consistent():
    assert derive_stream_seed(42, "node:abc") == derive_stream_seed(42, "node:abc")


def test_join_prompt_parts_hygiene():
    assert join_prompt_parts(" a , b ", " , c ") == "a , b, c, "
    assert join_prompt_parts("  alice  ", "bob,") == "alice, bob, "
