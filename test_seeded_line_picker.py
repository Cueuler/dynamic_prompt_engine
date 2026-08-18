"""Tests for UniqueLinePicker.

Pick is np.random.default_rng(stream_seed).integers(0, n). stream_seed is
SHA-256 of "{seed}:node:{id}" (or "{seed}:default" if unique_id is missing)
so two copies of the node with the same seed can still pick different lines.
"""

import hashlib
import random
import unittest

import numpy as np

from dynamic_prompt_engine.prompt_engine_nodes import UniqueLinePicker


def _candidates(pool_text):
    return [
        line.strip()
        for line in str(pool_text or "").splitlines()
        if line.strip()
    ]


def spec_stream_seed(master_seed, unique_id):
    """Copy of derive_stream_seed + stream_key_from_unique_id; not the node helper."""
    if isinstance(unique_id, (list, tuple)):
        unique_id = unique_id[0] if unique_id else None
    if unique_id is None:
        stream_key = "default"
    else:
        stream_key = f"node:{unique_id}"
    key = f"{int(master_seed)}:{stream_key}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16)


def spec_pick(pool_text, seed, unique_id=None):
    """Independent PCG64 pick; must not use UniqueLinePicker internals."""
    lines = _candidates(pool_text)
    if not lines:
        return ""
    stream_seed = spec_stream_seed(seed, unique_id)
    index = int(np.random.default_rng(stream_seed).integers(0, len(lines)))
    chosen = lines[index]
    return "" if chosen == "[empty]" else chosen


class TestUniqueLinePickerInputTypes(unittest.TestCase):
    def test_required_keys_are_only_pool_text_and_seed(self):
        required = UniqueLinePicker.INPUT_TYPES()["required"]
        self.assertEqual(set(required.keys()), {"pool_text", "seed"})

    def test_bypass_chance_is_absent(self):
        schema = UniqueLinePicker.INPUT_TYPES()
        required = schema["required"]
        self.assertNotIn("bypass_chance", required)
        self.assertNotIn("bypass_chance", schema.get("optional", {}))

    def test_unique_id_is_hidden(self):
        hidden = UniqueLinePicker.INPUT_TYPES().get("hidden", {})
        self.assertEqual(hidden.get("unique_id"), "UNIQUE_ID")

    def test_pool_text_is_single_line_string(self):
        pool = UniqueLinePicker.INPUT_TYPES()["required"]["pool_text"]
        self.assertEqual(pool[0], "STRING")
        self.assertFalse(pool[1].get("multiline"))
        self.assertFalse(pool[1].get("dynamicPrompts"))

    def test_return_types_and_names(self):
        self.assertEqual(UniqueLinePicker.RETURN_TYPES, ("STRING", "INT"))
        self.assertEqual(UniqueLinePicker.RETURN_NAMES, ("text", "seed"))


class TestUniqueLinePickerEmptyPool(unittest.TestCase):
    def setUp(self):
        self.node = UniqueLinePicker()

    def test_empty_string_returns_empty_text_and_passthrough_seed(self):
        self.assertEqual(self.node.pick_line("", seed=42), ("", 42))

    def test_none_pool_returns_empty_text_and_passthrough_seed(self):
        self.assertEqual(self.node.pick_line(None, seed=7), ("", 7))

    def test_whitespace_only_returns_empty_text(self):
        self.assertEqual(self.node.pick_line("   \n\t\n  ", seed=1), ("", 1))

    def test_only_blank_lines_returns_empty_text(self):
        self.assertEqual(self.node.pick_line("\n\n\n", seed=9), ("", 9))


class TestUniqueLinePickerCandidates(unittest.TestCase):
    def setUp(self):
        self.node = UniqueLinePicker()

    def test_blank_lines_are_dropped_and_lines_are_stripped(self):
        pool = "  alice  \n\n  \nbob\n"
        text, _ = self.node.pick_line(pool, seed=0, unique_id="1")
        self.assertIn(text, ("alice", "bob"))

    def test_crlf_and_lf_produce_the_same_candidates(self):
        lf = "alice\nbob\ncharlie"
        crlf = "alice\r\nbob\r\ncharlie"
        for seed in range(20):
            lf_text, _ = self.node.pick_line(lf, seed=seed, unique_id="1")
            crlf_text, _ = self.node.pick_line(crlf, seed=seed, unique_id="1")
            self.assertEqual(lf_text, crlf_text)

    def test_single_candidate_always_wins(self):
        for seed in (0, 1, 42, 999):
            text, out_seed = self.node.pick_line(
                "only", seed=seed, unique_id="1"
            )
            self.assertEqual(text, "only")
            self.assertEqual(out_seed, seed)

    def test_duplicate_lines_are_distinct_candidates(self):
        pool = "alice\nalice\nbob"
        lines = _candidates(pool)
        self.assertEqual(len(lines), 3)
        uid = "9"
        seen_indexes = set()
        for seed in range(200):
            text, _ = self.node.pick_line(pool, seed=seed, unique_id=uid)
            index = int(
                np.random.default_rng(spec_stream_seed(seed, uid)).integers(
                    0, 3
                )
            )
            self.assertEqual(text, lines[index])
            seen_indexes.add(index)
        self.assertEqual(seen_indexes, {0, 1, 2})


class TestUniqueLinePickerEmptyLiteral(unittest.TestCase):
    def setUp(self):
        self.node = UniqueLinePicker()

    def test_only_empty_literal_emits_blank(self):
        text, seed = self.node.pick_line("[empty]", seed=5, unique_id="1")
        self.assertEqual(text, "")
        self.assertEqual(seed, 5)

    def test_padded_empty_literal_is_a_candidate(self):
        text, _ = self.node.pick_line("  [empty]  ", seed=0, unique_id="1")
        self.assertEqual(text, "")

    def test_empty_literal_is_case_sensitive(self):
        text, _ = self.node.pick_line("[Empty]", seed=0, unique_id="1")
        self.assertEqual(text, "[Empty]")

    def test_mixed_pool_can_select_empty_literal(self):
        pool = "alice\n[empty]\nbob"
        found_empty = False
        found_other = False
        for seed in range(300):
            text, _ = self.node.pick_line(pool, seed=seed, unique_id="1")
            if text == "":
                found_empty = True
            else:
                self.assertIn(text, ("alice", "bob"))
                found_other = True
            if found_empty and found_other:
                break
        self.assertTrue(found_empty, "expected some seed to pick [empty]")
        self.assertTrue(found_other, "expected some seed to pick a real line")


class TestUniqueLinePickerDeterminism(unittest.TestCase):
    def setUp(self):
        self.node = UniqueLinePicker()
        self.pool = "alice\nbob\ncharlie"

    def test_same_seed_and_unique_id_is_deterministic(self):
        text_1, _ = self.node.pick_line(self.pool, seed=42, unique_id="55")
        text_2, _ = self.node.pick_line(self.pool, seed=42, unique_id="55")
        self.assertEqual(text_1, text_2)

    def test_same_seed_matches_independent_pcg64(self):
        for seed in (0, 1, 42, 100, 999, 2**32):
            text, out_seed = self.node.pick_line(
                self.pool, seed=seed, unique_id="55"
            )
            self.assertEqual(text, spec_pick(self.pool, seed, "55"))
            self.assertEqual(out_seed, seed)

    def test_pick_index_matches_independent_stream_seed_pcg64(self):
        """Index = default_rng(sha256(seed:node:id)).integers(0, n), not node code."""
        lines = _candidates(self.pool)
        uid = "55"
        for seed in (0, 7, 42, 1000):
            expected_index = int(
                np.random.default_rng(spec_stream_seed(seed, uid)).integers(
                    0, len(lines)
                )
            )
            text, _ = self.node.pick_line(self.pool, seed=seed, unique_id=uid)
            expected_text = (
                "" if lines[expected_index] == "[empty]" else lines[expected_index]
            )
            self.assertEqual(text, expected_text)

    def test_empty_pool_seed_passthrough(self):
        for pool in ("", None, "   \n  ", "\n\n"):
            for seed in (0, 42, 999):
                text, out_seed = self.node.pick_line(pool, seed=seed, unique_id="1")
                self.assertEqual(text, "")
                self.assertEqual(out_seed, seed)

    def test_unique_id_list_matches_string(self):
        a, _ = self.node.pick_line(self.pool, seed=7, unique_id="55")
        b, _ = self.node.pick_line(self.pool, seed=7, unique_id=["55"])
        self.assertEqual(a, b)

    def test_missing_unique_id_uses_default_stream(self):
        text, _ = self.node.pick_line(self.pool, seed=7)
        self.assertEqual(text, spec_pick(self.pool, 7, unique_id=None))

    def test_different_nodes_can_pick_different_lines(self):
        differing = 0
        for seed in range(40):
            a, _ = self.node.pick_line(self.pool, seed=seed, unique_id="10")
            b, _ = self.node.pick_line(self.pool, seed=seed, unique_id="20")
            if a != b:
                differing += 1
        self.assertGreater(
            differing,
            0,
            "Expected at least one seed where different unique_ids pick "
            "different lines.",
        )

    def test_plain_seed_rng_is_not_the_pick(self):
        seed = 0
        uid = "55"
        plain_index = int(np.random.default_rng(seed).integers(0, 3))
        mixed_index = int(
            np.random.default_rng(spec_stream_seed(seed, uid)).integers(0, 3)
        )
        self.assertNotEqual(plain_index, mixed_index)
        text, _ = self.node.pick_line(self.pool, seed=seed, unique_id=uid)
        self.assertEqual(text, _candidates(self.pool)[mixed_index])
        self.assertNotEqual(text, _candidates(self.pool)[plain_index])

    def test_different_seeds_can_pick_different_lines(self):
        seen = {
            self.node.pick_line(self.pool, seed=s, unique_id="1")[0]
            for s in range(50)
        }
        self.assertGreater(len(seen), 1)

    def test_does_not_mutate_stdlib_random(self):
        random.seed(123)
        before = random.random()
        random.seed(123)
        self.node.pick_line(self.pool, seed=99, unique_id="1")
        after = random.random()
        self.assertEqual(before, after)


class TestUniqueLinePickerNoWildcardExpansion(unittest.TestCase):
    def setUp(self):
        self.node = UniqueLinePicker()

    def test_brace_syntax_is_returned_literally(self):
        text, _ = self.node.pick_line("{red|blue}", seed=0, unique_id="1")
        self.assertEqual(text, "{red|blue}")

    def test_underscore_wildcard_is_returned_literally(self):
        text, _ = self.node.pick_line("__colors__", seed=0, unique_id="1")
        self.assertEqual(text, "__colors__")

    def test_chosen_line_with_wildcard_syntax_is_not_expanded(self):
        pool = "{a|b}\nplain"
        for seed in range(40):
            text, _ = self.node.pick_line(pool, seed=seed, unique_id="1")
            self.assertEqual(text, spec_pick(pool, seed, "1"))
            self.assertIn(text, ("{a|b}", "plain"))


class TestUniqueLinePickerSpread(unittest.TestCase):
    def test_three_thousand_seeds_hit_every_line_hundreds_of_times(self):
        node = UniqueLinePicker()
        pool = "alice\nbob\ncharlie"
        counts = {"alice": 0, "bob": 0, "charlie": 0}
        for seed in range(3000):
            text, _ = node.pick_line(pool, seed=seed, unique_id="1")
            counts[text] += 1
        for name, count in counts.items():
            self.assertGreaterEqual(
                count,
                300,
                f"{name} only picked {count} times in 3000 seeds",
            )


if __name__ == "__main__":
    unittest.main()
