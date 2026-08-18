"""Tests for BranchRandomSwitcher, RoutingSwitch, SeededTextPool, and helpers."""

import unittest
from dynamic_prompt_engine.prompt_engine_nodes import (
    BranchRandomSwitcher,
    BranchSelector,
    RoutingSwitch,
    SeededTextPool,
    TagJoin,
    connected_input_indices,
    MAX_BRANCHES,
    stream_key_from_unique_id,
)


class TestBranchRandomSwitcher(unittest.TestCase):
    def setUp(self):
        self.node = BranchRandomSwitcher()

    def test_zero_connected_outputs_empty_text_and_branch_in_range(self):
        text, branch = self.node.select_branch(seed=42, unique_id="1")
        self.assertEqual(text, "")
        self.assertIn(branch, (0, 1))

    def test_zero_connected_is_deterministic(self):
        b1 = self.node.select_branch(seed=42, unique_id="1")[1]
        b2 = self.node.select_branch(seed=42, unique_id="1")[1]
        self.assertEqual(b1, b2)

    def test_single_connected_first_branch(self):
        text, branch = self.node.select_branch(seed=42, unique_id="1", branch_0="alice")
        self.assertEqual(branch, 0)
        self.assertEqual(text, "alice, ")

    def test_single_connected_middle_branch(self):
        text, branch = self.node.select_branch(seed=42, unique_id="1", branch_3="alice")
        self.assertEqual(branch, 3)
        self.assertEqual(text, "alice, ")

    def test_single_connected_last_branch_border(self):
        text, branch = self.node.select_branch(seed=42, unique_id="1", branch_14="bob")
        self.assertEqual(branch, 14)
        self.assertEqual(text, "bob, ")

    def test_multiple_connected_picks_among_connected(self):
        text, branch = self.node.select_branch(
            seed=42, unique_id="1", branch_0="a", branch_1="b", branch_2="c"
        )
        self.assertIn(branch, (0, 1, 2))
        self.assertEqual(text, {0: "a, ", 1: "b, ", 2: "c, "}[branch])

    def test_multiple_connected_is_deterministic(self):
        args = dict(seed=42, unique_id="1", branch_0="a", branch_1="b")
        self.assertEqual(self.node.select_branch(**args), self.node.select_branch(**args))

    def test_all_fifteen_branches_border(self):
        kwargs = {f"branch_{i}": f"v{i}" for i in range(MAX_BRANCHES)}
        text, branch = self.node.select_branch(seed=7, unique_id="1", **kwargs)
        self.assertGreaterEqual(branch, 0)
        self.assertLess(branch, MAX_BRANCHES)
        self.assertEqual(text, f"v{branch}, ")

    def test_invalid_seed_raises(self):
        with self.assertRaises(ValueError):
            self.node.select_branch(seed="not-an-int", unique_id="1")

    def test_different_unique_ids_can_differ(self):
        differing = 0
        for s in range(10):
            _, a = self.node.select_branch(seed=s, unique_id="1", branch_0="x", branch_1="y")
            _, b = self.node.select_branch(seed=s, unique_id="2", branch_0="x", branch_1="y")
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

    def test_three_default_picks_one_and_is_deterministic(self):
        args = dict(
            seed=42,
            unique_id="1",
            input_0="alice",
            chance_0="Default",
            input_1="bob",
            chance_1="Default",
            input_2="carol",
            chance_2="Default",
        )
        text, seed = self.node.route(**args)
        self.assertIn(text, ("alice", "bob", "carol"))
        self.assertEqual(seed, 42)
        self.assertEqual(self.node.route(**args), self.node.route(**args))

    def test_strips_text_without_trailing_comma(self):
        text, seed = self.node.route(
            seed=0, unique_id="1", input_0="  hello  ", chance_0="Default"
        )
        self.assertEqual(text, "hello")
        self.assertEqual(seed, 0)

    def test_unconnected_kwargs_omitted_are_excluded(self):
        text, seed = self.node.route(
            seed=42, unique_id="1", input_2="only", chance_2="Default"
        )
        self.assertEqual(text, "only")
        self.assertEqual(seed, 42)

    def test_empty_and_whitespace_are_excluded(self):
        text, _ = self.node.route(
            seed=42,
            unique_id="1",
            input_0="keep",
            chance_0="Default",
            input_1="",
            chance_1="Default",
            input_2="   ",
            chance_2="2x",
        )
        self.assertEqual(text, "keep")

    def test_off_is_excluded_even_with_text(self):
        text, _ = self.node.route(
            seed=42,
            unique_id="1",
            input_0="skip-me",
            chance_0="Off",
            input_1="keep",
            chance_1="Default",
        )
        self.assertEqual(text, "keep")

    def test_missing_chance_counts_as_default(self):
        args = dict(seed=42, unique_id="1", input_0="a", input_1="b")
        text, _ = self.node.route(**args)
        self.assertIn(text, ("a", "b"))
        self.assertEqual(self.node.route(**args), self.node.route(**args))

    def test_zero_eligible_returns_empty_text_and_passthrough_seed(self):
        self.assertEqual(self.node.route(seed=99, unique_id="1"), ("", 99))
        self.assertEqual(
            self.node.route(
                seed=99,
                unique_id="1",
                input_0="nope",
                chance_0="Off",
                input_1="  ",
                chance_1="Default",
            ),
            ("", 99),
        )

    def test_invalid_seed_raises(self):
        with self.assertRaises(ValueError):
            self.node.route(seed="not-an-int", unique_id="1", input_0="a")

    def test_different_unique_ids_can_differ(self):
        differing = 0
        for s in range(10):
            a, _ = self.node.route(
                seed=s, unique_id="1", input_0="x", input_1="y"
            )
            b, _ = self.node.route(
                seed=s, unique_id="2", input_0="x", input_1="y"
            )
            if a != b:
                differing += 1
        self.assertGreater(differing, 0)

    def test_double_weight_wins_about_twice_as_often(self):
        wins = {"a": 0, "b": 0}
        for s in range(300):
            text, _ = self.node.route(
                seed=s,
                unique_id="1",
                input_0="a",
                chance_0="Default",
                input_1="b",
                chance_1="2x",
            )
            wins[text] += 1
        self.assertGreater(wins["b"], wins["a"])
        self.assertGreater(wins["b"], 150)
        self.assertGreater(wins["a"], 50)

    def test_optional_chance_schema(self):
        optional = RoutingSwitch.INPUT_TYPES()["optional"]
        schema = optional["chance_3"]
        self.assertEqual(schema[0], ["Default", "Off", "1.5x", "2x"])
        self.assertEqual(schema[1].get("default"), "Default")
        input_schema = optional["input_7"]
        self.assertEqual(input_schema[0], "STRING")

    def test_one_point_five_weight_wins_more_often_than_default(self):
        wins = {"a": 0, "b": 0}
        for s in range(300):
            text, _ = self.node.route(
                seed=s,
                unique_id="1",
                input_0="a",
                chance_0="Default",
                input_1="b",
                chance_1="1.5x",
            )
            wins[text] += 1
        self.assertGreater(wins["b"], wins["a"])
        self.assertGreater(wins["b"], 140)
        self.assertGreater(wins["a"], 50)

    def test_all_three_weights_never_pick_off(self):
        live = {"default", "boost", "double"}
        for s in range(50):
            text, seed = self.node.route(
                seed=s,
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
            self.assertIn(text, live)
            self.assertEqual(seed, s)

    def test_single_survivor_after_filters_always_wins(self):
        for s in range(20):
            text, seed = self.node.route(
                seed=s,
                unique_id="1",
                input_0="skip",
                chance_0="Off",
                input_1="  ",
                chance_1="Default",
                input_3="only",
                chance_3="2x",
            )
            self.assertEqual(text, "only")
            self.assertEqual(seed, s)

    def test_combo_list_value_matches_string_label(self):
        kwargs = dict(
            unique_id="1",
            input_0="plain",
            input_1="boosted",
        )
        for s in range(20):
            as_string, _ = self.node.route(
                seed=s, chance_0="Default", chance_1="1.5x", **kwargs
            )
            as_list, _ = self.node.route(
                seed=s, chance_0=["Default"], chance_1=["1.5x"], **kwargs
            )
            self.assertEqual(as_string, as_list)

    def test_unknown_and_blank_chance_count_as_default(self):
        kwargs = dict(unique_id="1", input_0="a", input_1="b")
        for s in range(15):
            default, _ = self.node.route(
                seed=s, chance_0="Default", chance_1="Default", **kwargs
            )
            blank, _ = self.node.route(
                seed=s, chance_0="", chance_1="nope", **kwargs
            )
            lowercase_off, _ = self.node.route(
                seed=s, chance_0="off", chance_1="Default", **kwargs
            )
            self.assertEqual(blank, default)
            self.assertEqual(lowercase_off, default)

    def test_stray_chance_without_input_does_not_invent_a_slot(self):
        self.assertEqual(
            self.node.route(seed=7, unique_id="1", chance_5="2x"),
            ("", 7),
        )
        text, seed = self.node.route(
            seed=7,
            unique_id="1",
            input_0="keep",
            chance_0="Default",
            chance_5="2x",
        )
        self.assertEqual(text, "keep")
        self.assertEqual(seed, 7)

    def test_uncapped_index_beyond_branch_limit(self):
        text, seed = self.node.route(
            seed=3, unique_id="1", input_20="far", chance_20="Default"
        )
        self.assertEqual(text, "far")
        self.assertEqual(seed, 3)

    def test_none_input_is_excluded(self):
        text, seed = self.node.route(
            seed=4,
            unique_id="1",
            input_0=None,
            chance_0="2x",
            input_1="keep",
            chance_1="Default",
        )
        self.assertEqual(text, "keep")
        self.assertEqual(seed, 4)

    def test_comma_text_is_not_tag_join_hygiened(self):
        text, seed = self.node.route(
            seed=0, unique_id="1", input_0="red, blue", chance_0="Default"
        )
        self.assertEqual(text, "red, blue")
        self.assertEqual(seed, 0)


class TestSeededTextPoolUniqueId(unittest.TestCase):
    """SeededTextPool remains registered for backward-compatible workflows."""

    def setUp(self):
        self.node = SeededTextPool()

    def test_different_nodes_pick_different_lines(self):
        pool = "alice\nbob\ncharlie"
        uid_a, uid_b = "10", "20"

        differing = 0
        for s in [0, 1, 42, 100, 999]:
            a, _ = self.node.select_from_pool(pool, seed=s, unique_id=uid_a)
            b, _ = self.node.select_from_pool(pool, seed=s, unique_id=uid_b)
            if a != b:
                differing += 1

        self.assertGreater(
            differing, 0,
            "Expected at least one seed where different unique_ids produce "
            "different pool selections."
        )

    def test_same_node_is_deterministic(self):
        pool = "alice\nbob\ncharlie"
        text_1, _ = self.node.select_from_pool(pool, seed=42, unique_id="55")
        text_2, _ = self.node.select_from_pool(pool, seed=42, unique_id="55")
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