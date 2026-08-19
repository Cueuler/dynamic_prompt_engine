"""Tests for BranchRandomSwitcher, RoutingSwitch, SeededTextPool, and helpers."""

import hashlib
import unittest
from unittest.mock import patch
from dynamic_prompt_engine.prompt_engine_nodes import (
    BranchRandomSwitcher,
    BranchSelector,
    RoutingSwitch,
    SeededTextPool,
    TagJoin,
    chance_weight,
    connected_input_indices,
    MAX_BRANCHES,
    normalize_chance_value,
    numbered_input_indices,
    stream_key_from_unique_id,
)

# Spec copy of Routing Switch lottery (README): Default=2, 1.5x=3, 2x=4;
# r = sha256(f"{seed}:node:{id}")[:16] as int % total; walk cumulative weights
# in sorted input index order. Independent of prompt_engine_nodes.route.
_SPEC_WEIGHTS = {"Default": 2, "1.5x": 3, "2x": 4}


def _spec_weight(label):
    if label is None:
        label = "Default"
    if isinstance(label, (list, tuple)):
        label = label[0] if label else "Default"
    text = str(label).strip() or "Default"
    if text == "Off":
        return None
    return _SPEC_WEIGHTS.get(text, _SPEC_WEIGHTS["Default"])


def _spec_stream_seed(master_seed, unique_id):
    if isinstance(unique_id, (list, tuple)):
        unique_id = unique_id[0] if unique_id else None
    stream_key = f"node:{unique_id}" if unique_id is not None else "default"
    key = f"{int(master_seed)}:{stream_key}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16)


def spec_pick(seed, unique_id, slots):
    """slots: iterable of (index, text, chance). None=unconnected. Off skipped.
    Connected empty/whitespace is eligible and wins as "". Sorted by index."""
    eligible = []
    for _index, text, chance in sorted(slots, key=lambda item: item[0]):
        if text is None:
            continue
        stripped = str(text).strip()
        weight = _spec_weight(chance)
        if weight is None:
            continue
        eligible.append((weight, stripped))
    if not eligible:
        return ""
    remaining = _spec_stream_seed(seed, unique_id) % sum(w for w, _ in eligible)
    for weight, text in eligible:
        remaining -= weight
        if remaining < 0:
            return text
    return eligible[-1][1]


class TestBranchRandomSwitcher(unittest.TestCase):
    def setUp(self):
        self.node = BranchRandomSwitcher()

    def test_zero_connected_outputs_empty_text_and_branch_in_range(self):
        text, branch = self.node.select_branch(dpe_seed=42, unique_id="1")
        self.assertEqual(text, "")
        self.assertIn(branch, (0, 1))

    def test_zero_connected_is_deterministic(self):
        b1 = self.node.select_branch(dpe_seed=42, unique_id="1")[1]
        b2 = self.node.select_branch(dpe_seed=42, unique_id="1")[1]
        self.assertEqual(b1, b2)

    def test_single_connected_first_branch(self):
        text, branch = self.node.select_branch(dpe_seed=42, unique_id="1", branch_0="alice")
        self.assertEqual(branch, 0)
        self.assertEqual(text, "alice, ")

    def test_single_connected_middle_branch(self):
        text, branch = self.node.select_branch(dpe_seed=42, unique_id="1", branch_3="alice")
        self.assertEqual(branch, 3)
        self.assertEqual(text, "alice, ")

    def test_single_connected_last_branch_border(self):
        text, branch = self.node.select_branch(dpe_seed=42, unique_id="1", branch_14="bob")
        self.assertEqual(branch, 14)
        self.assertEqual(text, "bob, ")

    def test_multiple_connected_picks_among_connected(self):
        text, branch = self.node.select_branch(
            dpe_seed=42, unique_id="1", branch_0="a", branch_1="b", branch_2="c"
        )
        self.assertIn(branch, (0, 1, 2))
        self.assertEqual(text, {0: "a, ", 1: "b, ", 2: "c, "}[branch])

    def test_multiple_connected_is_deterministic(self):
        args = dict(dpe_seed=42, unique_id="1", branch_0="a", branch_1="b")
        self.assertEqual(self.node.select_branch(**args), self.node.select_branch(**args))

    def test_all_fifteen_branches_border(self):
        kwargs = {f"branch_{i}": f"v{i}" for i in range(MAX_BRANCHES)}
        text, branch = self.node.select_branch(dpe_seed=7, unique_id="1", **kwargs)
        self.assertGreaterEqual(branch, 0)
        self.assertLess(branch, MAX_BRANCHES)
        self.assertEqual(text, f"v{branch}, ")

    def test_invalid_dpe_seed_raises(self):
        with self.assertRaises(ValueError):
            self.node.select_branch(dpe_seed="not-an-int", unique_id="1")

    def test_different_unique_ids_can_differ(self):
        differing = 0
        for s in range(10):
            _, a = self.node.select_branch(dpe_seed=s, unique_id="1", branch_0="x", branch_1="y")
            _, b = self.node.select_branch(dpe_seed=s, unique_id="2", branch_0="x", branch_1="y")
            if a != b:
                differing += 1
        self.assertGreater(differing, 0)


class TestBranchSelector(unittest.TestCase):
    def setUp(self):
        self.node = BranchSelector()

    def test_select_first(self):
        self.assertEqual(self.node.select(0, input_0="alice", input_1="bob"), ("alice",))

    def test_select_last_border(self):
        self.assertEqual(self.node.select(14, input_14="bob"), ("bob",))

    def test_select_missing_input_returns_skipped(self):
        self.assertEqual(self.node.select(2, input_0="a"), ("branch 2 skipped",))

    def test_select_empty_connected_input_returns_empty(self):
        self.assertEqual(self.node.select(1, input_1=""), ("",))

    def test_select_out_of_range_raises(self):
        with self.assertRaises(ValueError):
            self.node.select(15)

    def test_select_negative_raises(self):
        with self.assertRaises(ValueError):
            self.node.select(-1)


class TestStreamKeyFromUniqueId(unittest.TestCase):
    """stream_key_from_unique_id remains used by BranchRandomSwitcher."""

    def test_none_falls_back_to_default(self):
        self.assertEqual(stream_key_from_unique_id(None), "default")

    def test_list_input(self):
        self.assertEqual(stream_key_from_unique_id(["42"]), "node:42")

    def test_int_and_str_input(self):
        self.assertEqual(stream_key_from_unique_id(42), "node:42")
        self.assertEqual(stream_key_from_unique_id("42"), "node:42")


class TestRoutingSwitch(unittest.TestCase):
    def setUp(self):
        self.node = RoutingSwitch()

    def test_three_default_picks_exact_winner_and_is_deterministic(self):
        args = dict(
            dpe_seed=42,
            unique_id="1",
            input_0="alice",
            chance_0="Default",
            input_1="bob",
            chance_1="Default",
            input_2="carol",
            chance_2="Default",
        )
        expected = spec_pick(
            42,
            "1",
            ((0, "alice", "Default"), (1, "bob", "Default"), (2, "carol", "Default")),
        )
        text, = self.node.route(**args)
        self.assertEqual(text, expected)
        self.assertEqual(self.node.route(**args), (expected,))
        self.assertEqual(self.node.route(**args), self.node.route(**args))

    def test_strips_text_without_trailing_comma(self):
        text, = self.node.route(
            dpe_seed=0, unique_id="1", input_0="  hello  ", chance_0="Default"
        )
        self.assertEqual(text, "hello")

    def test_unconnected_kwargs_omitted_are_excluded(self):
        text, = self.node.route(
            dpe_seed=42, unique_id="1", input_2="only", chance_2="Default"
        )
        self.assertEqual(text, "only")

    def test_connected_empty_and_whitespace_can_win(self):
        slots = (
            (0, "keep", "Default"),
            (1, "", "Default"),
            (2, "   ", "2x"),
        )
        kwargs = dict(
            unique_id="1",
            input_0="keep",
            chance_0="Default",
            input_1="",
            chance_1="Default",
            input_2="   ",
            chance_2="2x",
        )
        for s in range(50):
            text, = self.node.route(dpe_seed=s, **kwargs)
            self.assertEqual(text, spec_pick(s, "1", slots))

    def test_off_empty_cannot_win_or_change_weights(self):
        keep_only = ((1, "keep", "Default"),)
        with_off_empty = ((0, "", "Off"), (1, "keep", "Default"))
        for s in range(30):
            without, = self.node.route(
                dpe_seed=s, unique_id="1", input_1="keep", chance_1="Default"
            )
            with_off, = self.node.route(
                dpe_seed=s,
                unique_id="1",
                input_0="",
                chance_0="Off",
                input_1="keep",
                chance_1="Default",
            )
            self.assertEqual(without, spec_pick(s, "1", keep_only))
            self.assertEqual(with_off, without)
            self.assertEqual(with_off, spec_pick(s, "1", with_off_empty))

    def test_off_is_excluded_even_with_text(self):
        text, = self.node.route(
            dpe_seed=42,
            unique_id="1",
            input_0="skip-me",
            chance_0="Off",
            input_1="keep",
            chance_1="Default",
        )
        self.assertEqual(text, "keep")

    def test_missing_chance_counts_as_default(self):
        args = dict(dpe_seed=42, unique_id="1", input_0="a", input_1="b")
        expected = spec_pick(42, "1", ((0, "a", "Default"), (1, "b", "Default")))
        text, = self.node.route(**args)
        self.assertEqual(text, expected)
        self.assertEqual(self.node.route(**args), (expected,))

    def test_zero_eligible_returns_empty_text(self):
        self.assertEqual(self.node.route(dpe_seed=99, unique_id="1"), ("",))
        self.assertEqual(
            self.node.route(
                dpe_seed=99,
                unique_id="1",
                input_0="nope",
                chance_0="Off",
                input_1="also-off",
                chance_1="Off",
            ),
            ("",),
        )

    def test_invalid_dpe_seed_raises(self):
        with self.assertRaises(ValueError):
            self.node.route(dpe_seed="not-an-int", unique_id="1", input_0="a")

    def test_unique_id_matches_spec_stream_for_every_seed(self):
        slots = ((0, "x", "Default"), (1, "y", "Default"))
        for s in range(50):
            a, = self.node.route(
                dpe_seed=s, unique_id="1", input_0="x", input_1="y"
            )
            b, = self.node.route(
                dpe_seed=s, unique_id="2", input_0="x", input_1="y"
            )
            self.assertEqual(a, spec_pick(s, "1", slots))
            self.assertEqual(b, spec_pick(s, "2", slots))

    def test_double_weight_matches_spec_lottery(self):
        slots = ((0, "a", "Default"), (1, "b", "2x"))
        for s in range(300):
            text, = self.node.route(
                dpe_seed=s,
                unique_id="1",
                input_0="a",
                chance_0="Default",
                input_1="b",
                chance_1="2x",
            )
            self.assertEqual(text, spec_pick(s, "1", slots))

    def test_two_x_wins_twice_as_often_as_default(self):
        """Uniform residues 0..5: Default weight 2, 2x weight 4 → 2 vs 4 wins."""
        wins = {"a": 0, "b": 0}
        with patch(
            "dynamic_prompt_engine.prompt_engine_nodes.derive_stream_seed",
            side_effect=range(6),
        ):
            for _ in range(6):
                text, = self.node.route(
                    dpe_seed=0,
                    unique_id="1",
                    input_0="a",
                    chance_0="Default",
                    input_1="b",
                    chance_1="2x",
                )
                wins[text] += 1
        self.assertEqual(wins["a"], 2)
        self.assertEqual(wins["b"], 4)

    def test_one_point_five_wins_one_and_a_half_times_default(self):
        """Uniform residues 0..4: Default weight 2, 1.5x weight 3 → 2 vs 3 wins."""
        wins = {"a": 0, "b": 0}
        with patch(
            "dynamic_prompt_engine.prompt_engine_nodes.derive_stream_seed",
            side_effect=range(5),
        ):
            for _ in range(5):
                text, = self.node.route(
                    dpe_seed=0,
                    unique_id="1",
                    input_0="a",
                    chance_0="Default",
                    input_1="b",
                    chance_1="1.5x",
                )
                wins[text] += 1
        self.assertEqual(wins["a"], 2)
        self.assertEqual(wins["b"], 3)

    def test_off_never_wins_across_all_residues(self):
        with patch(
            "dynamic_prompt_engine.prompt_engine_nodes.derive_stream_seed",
            side_effect=range(6),
        ):
            for _ in range(6):
                text, = self.node.route(
                    dpe_seed=0,
                    unique_id="1",
                    input_0="a",
                    chance_0="Default",
                    input_1="b",
                    chance_1="Off",
                )
                self.assertEqual(text, "a")
        only_a, = self.node.route(
            dpe_seed=0, unique_id="1", input_0="a", chance_0="Default"
        )
        self.assertEqual(only_a, "a")

    def test_optional_chance_schema(self):
        optional = RoutingSwitch.INPUT_TYPES()["optional"]
        schema = optional["chance_3"]
        self.assertEqual(schema[0], ["Default", "Off", "1.5x", "2x"])
        self.assertEqual(schema[1].get("default"), "Default")
        input_schema = optional["input_7"]
        self.assertEqual(input_schema[0], "STRING")

    def test_one_point_five_weight_matches_spec_lottery(self):
        slots = ((0, "a", "Default"), (1, "b", "1.5x"))
        for s in range(300):
            text, = self.node.route(
                dpe_seed=s,
                unique_id="1",
                input_0="a",
                chance_0="Default",
                input_1="b",
                chance_1="1.5x",
            )
            self.assertEqual(text, spec_pick(s, "1", slots))

    def test_all_three_weights_never_pick_off(self):
        slots = (
            (0, "default", "Default"),
            (1, "boost", "1.5x"),
            (2, "double", "2x"),
            (3, "off-text", "Off"),
        )
        for s in range(50):
            text, = self.node.route(
                dpe_seed=s,
                unique_id="1",
                input_0="default",
                chance_0="Default",
                input_1="boost",
                chance_1="1.5x",
                input_2="double",
                chance_2="2x",
                input_3="off-text",
                chance_3="Off",
            )
            self.assertEqual(text, spec_pick(s, "1", slots))
            self.assertNotEqual(text, "off-text")

    def test_single_survivor_after_filters_always_wins(self):
        for s in range(20):
            text, = self.node.route(
                dpe_seed=s,
                unique_id="1",
                input_0="skip",
                chance_0="Off",
                input_1="  ",
                chance_1="Off",
                input_3="only",
                chance_3="2x",
            )
            self.assertEqual(text, "only")

    def test_only_connected_empty_wins_empty_string(self):
        for s in range(10):
            text, = self.node.route(
                dpe_seed=s, unique_id="1", input_0="", chance_0="Default"
            )
            self.assertEqual(text, "")

    def test_combo_list_value_matches_string_label(self):
        kwargs = dict(
            unique_id="1",
            input_0="plain",
            input_1="boosted",
        )
        for s in range(20):
            as_string, = self.node.route(
                dpe_seed=s, chance_0="Default", chance_1="1.5x", **kwargs
            )
            as_list, = self.node.route(
                dpe_seed=s, chance_0=["Default"], chance_1=["1.5x"], **kwargs
            )
            self.assertEqual(as_string, as_list)

    def test_unknown_and_blank_chance_count_as_default(self):
        kwargs = dict(unique_id="1", input_0="a", input_1="b")
        for s in range(15):
            default, = self.node.route(
                dpe_seed=s, chance_0="Default", chance_1="Default", **kwargs
            )
            blank, = self.node.route(
                dpe_seed=s, chance_0="", chance_1="nope", **kwargs
            )
            lowercase_off, = self.node.route(
                dpe_seed=s, chance_0="off", chance_1="Default", **kwargs
            )
            self.assertEqual(blank, default)
            self.assertEqual(lowercase_off, default)

    def test_stray_chance_without_input_does_not_invent_a_slot(self):
        self.assertEqual(
            self.node.route(dpe_seed=7, unique_id="1", chance_5="2x"),
            ("",),
        )
        text, = self.node.route(
            dpe_seed=7,
            unique_id="1",
            input_0="keep",
            chance_0="Default",
            chance_5="2x",
        )
        self.assertEqual(text, "keep")

    def test_uncapped_index_beyond_branch_limit(self):
        text, = self.node.route(
            dpe_seed=3, unique_id="1", input_20="far", chance_20="Default"
        )
        self.assertEqual(text, "far")

    def test_none_input_is_excluded(self):
        text, = self.node.route(
            dpe_seed=4,
            unique_id="1",
            input_0=None,
            chance_0="2x",
            input_1="keep",
            chance_1="Default",
        )
        self.assertEqual(text, "keep")

    def test_comma_text_is_not_tag_join_hygiened(self):
        text, = self.node.route(
            dpe_seed=0, unique_id="1", input_0="red, blue", chance_0="Default"
        )
        self.assertEqual(text, "red, blue")

    def test_wildcard_syntax_is_not_expanded(self):
        template = "{red|blue} __samples/flower__"
        text, = self.node.route(
            dpe_seed=7, unique_id="1", input_0=template, chance_0="Default"
        )
        self.assertEqual(text, template)

    def test_lottery_walks_sorted_index_order_not_kwargs_order(self):
        kwargs = dict(
            dpe_seed=11,
            unique_id="1",
            input_5="late",
            chance_5="Default",
            input_1="early",
            chance_1="Default",
        )
        expected = spec_pick(
            11, "1", ((1, "early", "Default"), (5, "late", "Default"))
        )
        text, = self.node.route(**kwargs)
        self.assertEqual(text, expected)

    def test_unique_id_list_matches_scalar(self):
        slots = ((0, "a", "Default"), (1, "b", "Default"))
        for s in range(20):
            as_str, = self.node.route(
                dpe_seed=s, unique_id="9", input_0="a", input_1="b"
            )
            as_list, = self.node.route(
                dpe_seed=s, unique_id=["9"], input_0="a", input_1="b"
            )
            self.assertEqual(as_str, spec_pick(s, "9", slots))
            self.assertEqual(as_list, as_str)

    def test_combo_list_matches_spec_pick(self):
        slots = ((0, "plain", "Default"), (1, "boosted", "1.5x"))
        for s in range(20):
            text, = self.node.route(
                dpe_seed=s,
                unique_id="1",
                input_0="plain",
                chance_0=["Default"],
                input_1="boosted",
                chance_1=["1.5x"],
            )
            self.assertEqual(text, spec_pick(s, "1", slots))


class TestChanceHelpers(unittest.TestCase):
    def test_chance_weight_labels(self):
        self.assertEqual(chance_weight("Default"), 2)
        self.assertEqual(chance_weight("1.5x"), 3)
        self.assertEqual(chance_weight("2x"), 4)
        self.assertIsNone(chance_weight("Off"))
        self.assertEqual(chance_weight(None), 2)
        self.assertEqual(chance_weight(""), 2)
        self.assertEqual(chance_weight("nope"), 2)
        self.assertEqual(chance_weight("off"), 2)
        self.assertEqual(chance_weight(["1.5x"]), 3)
        self.assertEqual(chance_weight([]), 2)

    def test_normalize_chance_value(self):
        self.assertEqual(normalize_chance_value(None), "Default")
        self.assertEqual(normalize_chance_value(["Off"]), "Off")
        self.assertEqual(normalize_chance_value("  2x  "), "2x")

    def test_numbered_input_indices_sorted_uncapped(self):
        self.assertEqual(
            numbered_input_indices(
                {"input_10": "a", "input_2": "b", "chance_2": "Default"},
                "input_",
            ),
            [2, 10],
        )
        self.assertEqual(numbered_input_indices({"chance_3": "2x"}, "input_"), [])


class TestSeededTextPoolUniqueId(unittest.TestCase):
    """SeededTextPool remains registered for backward-compatible workflows."""

    def setUp(self):
        self.node = SeededTextPool()

    def test_different_nodes_pick_different_lines(self):
        pool = "alice\nbob\ncharlie"
        uid_a, uid_b = "10", "20"

        differing = 0
        for s in [0, 1, 42, 100, 999]:
            a, = self.node.select_from_pool(pool, dpe_seed=s, unique_id=uid_a)
            b, = self.node.select_from_pool(pool, dpe_seed=s, unique_id=uid_b)
            if a != b:
                differing += 1

        self.assertGreater(
            differing, 0,
            "Expected at least one seed where different unique_ids produce "
            "different pool selections."
        )

    def test_same_node_is_deterministic(self):
        pool = "alice\nbob\ncharlie"
        text_1, = self.node.select_from_pool(pool, dpe_seed=42, unique_id="55")
        text_2, = self.node.select_from_pool(pool, dpe_seed=42, unique_id="55")
        self.assertEqual(text_1, text_2)


class TestConnectedInputIndices(unittest.TestCase):
    def test_extracts_and_sorts_in_range_indices(self):
        kwargs = {"branch_2": "b", "branch_0": "a", "branch_10": "c", "other": "x"}
        self.assertEqual(
            connected_input_indices(kwargs, "branch_", MAX_BRANCHES), [0, 2, 10]
        )

    def test_ignores_non_numeric_and_out_of_range(self):
        kwargs = {"branch_abc": "x", "branch_15": "too high", "branch_-1": "neg"}
        self.assertEqual(connected_input_indices(kwargs, "branch_", MAX_BRANCHES), [])

    def test_ignores_other_prefixes(self):
        kwargs = {"input_0": "x", "tag_0": "y"}
        self.assertEqual(connected_input_indices(kwargs, "branch_", MAX_BRANCHES), [])


class TestTagJoin(unittest.TestCase):
    def setUp(self):
        self.node = TagJoin()

    def test_numeric_sort_order(self):
        result = self.node.join_tags(tag_10="b", tag_0="a", tag_2="c")
        self.assertEqual(result["result"], ("a, c, b, ",))

    def test_ignores_non_numeric_tag_keys(self):
        result = self.node.join_tags(tag_0="a", tag_foo="nope", tag_1="b")
        self.assertEqual(result["result"], ("a, b, ",))


if __name__ == "__main__":
    unittest.main()