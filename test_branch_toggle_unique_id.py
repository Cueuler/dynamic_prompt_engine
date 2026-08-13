"""Tests for per-node unique_id randomization in BranchToggle and SeededTextPool."""

import unittest
from dynamic_prompt_engine.prompt_engine_nodes import (
    BranchToggle,
    SeededTextPool,
    connected_input_indices,
    MAX_BRANCHES,
    stream_key_from_unique_id,
)


class TestBranchToggleUniqueId(unittest.TestCase):
    """BranchToggle should produce independent branches per node with the same seed."""

    def setUp(self):
        self.node = BranchToggle()
        self.seed = 12345

    def test_different_nodes_can_produce_different_branches(self):
        """Two BranchToggle nodes with the same seed but different unique_id
        should be able to produce different branches (the core fix)."""
        _, branch_a = self.node.select_section("Random", seed=self.seed, unique_id="100")
        _, branch_b = self.node.select_section("Random", seed=self.seed, unique_id="200")

        # Probabilistic: with different unique_ids there's a 50% chance they differ.
        # If they're the same, run more trials to confirm determinism isn't the issue.
        differing = 0
        total = 0
        for uid_a, uid_b in [("100", "200"), ("50", "99"), ("1", "2"), ("10", "20")]:
            _, ba = self.node.select_section("Random", seed=self.seed, unique_id=uid_a)
            _, bb = self.node.select_section("Random", seed=self.seed, unique_id=uid_b)
            if ba != bb:
                differing += 1
            total += 1

        self.assertGreater(
            differing, 0,
            f"Expected at least one differing pair across {total} trials, "
            f"but all {total} pairs agreed. This suggests the unique_id is not "
            f"affecting the branch selection."
        )

    def test_same_node_id_is_deterministic(self):
        """Same seed + same unique_id always produces the same branch."""
        _, branch_1 = self.node.select_section("Random", seed=42, unique_id="77")
        _, branch_2 = self.node.select_section("Random", seed=42, unique_id="77")
        self.assertEqual(branch_1, branch_2)

    def test_1girl_always_zero(self):
        """mode='1girl' always returns branch 0, regardless of seed or unique_id."""
        for uid in [None, "1", "100", "abc"]:
            for seed in [0, 1, 999999]:
                _, branch = self.node.select_section("1girl", seed=seed, unique_id=uid)
                self.assertEqual(branch, 0)

    def test_2girls_always_one(self):
        """mode='2girls' always returns branch 1, regardless of seed or unique_id."""
        for uid in [None, "1", "100", "abc"]:
            for seed in [0, 1, 999999]:
                _, branch = self.node.select_section("2girls", seed=seed, unique_id=uid)
                self.assertEqual(branch, 1)

    def test_unique_id_none_falls_back_to_default(self):
        """When unique_id is None, use 'default' stream key (for unit tests)."""
        key = stream_key_from_unique_id(None)
        self.assertEqual(key, "default")

        _, branch = self.node.select_section("Random", seed=42, unique_id=None)
        self.assertIn(branch, (0, 1))

    def test_text_output_matches_branch(self):
        """branch 0 outputs branch_1 text; branch 1 outputs branch_2 text."""
        # Force branch 0
        text, b0 = self.node.select_section(
            "1girl", branch_1="alice", branch_2="bob", unique_id="99"
        )
        self.assertEqual(b0, 0)
        self.assertEqual(text, "alice, ")

        # Force branch 1
        text, b1 = self.node.select_section(
            "2girls", branch_1="alice", branch_2="bob", unique_id="99"
        )
        self.assertEqual(b1, 1)
        self.assertEqual(text, "bob, ")

    def test_resolve_unique_id_list(self):
        """stream_key_from_unique_id handles list/tuple input (ComfyUI format)."""
        key = stream_key_from_unique_id(["42"])
        self.assertEqual(key, "node:42")

    def test_resolve_unique_id_int(self):
        """stream_key_from_unique_id handles int input."""
        key = stream_key_from_unique_id(42)
        self.assertEqual(key, "node:42")

    def test_resolve_unique_id_str(self):
        """stream_key_from_unique_id handles str input."""
        key = stream_key_from_unique_id("42")
        self.assertEqual(key, "node:42")


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

        text_a, _ = self.node.select_from_pool(pool, seed, unique_id=uid_a)
        text_b, _ = self.node.select_from_pool(pool, seed, unique_id=uid_b)

        # With 3 lines and different unique_ids, they should differ sometimes.
        # Run a few seed values to check.
        differing = 0
        for s in [0, 1, 42, 100, 999]:
            a, _ = self.node.select_from_pool(pool, s, unique_id=uid_a)
            b, _ = self.node.select_from_pool(pool, s, unique_id=uid_b)
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
        text_1, _ = self.node.select_from_pool(pool, 42, unique_id="55")
        text_2, _ = self.node.select_from_pool(pool, 42, unique_id="55")
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


if __name__ == "__main__":
    unittest.main()