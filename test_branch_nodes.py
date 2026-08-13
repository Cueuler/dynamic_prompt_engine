"""Tests for BranchRandomSwitcher, SeededTextPool, and branch input helpers."""

import unittest
from dynamic_prompt_engine.prompt_engine_nodes import (
    BranchRandomSwitcher,
    BranchSelector,
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


class TestSeededTextPoolUniqueId(unittest.TestCase):
    """SeededTextPool already uses per-node unique_id; confirm no regression."""

    def setUp(self):
        self.node = SeededTextPool()

    def test_different_nodes_pick_different_lines(self):
        """Two SeededTextPool nodes with the same seed/pool but different
        unique_id can pick different lines."""
        pool = "alice\nbob\ncharlie"
        uid_a, uid_b = "10", "20"
        seed = 42

        text_a, _ = self.node.select_from_pool(pool, seed=seed, unique_id=uid_a)
        text_b, _ = self.node.select_from_pool(pool, seed=seed, unique_id=uid_b)

        # With 3 lines and different unique_ids, they should differ sometimes.
        # Run a few seed values to check.
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
        """Same seed + same unique_id always picks the same line."""
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