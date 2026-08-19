"""Tests for UniqueLinePicker.

Pick is np.random.default_rng(stream_seed).integers(0, n). stream_seed is
SHA-256 of "{seed}:node:{id}" (or "{seed}:default" if unique_id is missing)
so two copies of the node with the same seed can still pick different lines.
"""

import hashlib
import random
import unittest

import numpy as np

from dynamic_prompt_engine.prompt_engine_nodes import SeededTextPool, UniqueLinePicker


class _LinePickerTestBase(unittest.TestCase):
    """Override picker_factory in subclasses to test another pick_line implementation."""

    @staticmethod
    def picker_factory():
        return UniqueLinePicker()

    def setUp(self):
        self.node = self.picker_factory()


class SeededTextPoolAsLinePicker:
    """Adapter so Seeded Text Pool runs Unique Line Picker behavioral tests."""

    def pick_line(self, input, bypass_chance=False, dpe_seed=0, unique_id=None):
        return SeededTextPool().select_from_pool(
            input, bypass_chance=bypass_chance, dpe_seed=dpe_seed, unique_id=unique_id
        )


def _candidates(pool_text):
    return [
        line.strip()
        for line in str(pool_text or "").splitlines()
        if line.strip()
    ]


def spec_stream_seed(master_seed, unique_id, suffix=""):
    """Copy of derive_stream_seed + stream_key_from_unique_id; not the node helper."""
    if isinstance(unique_id, (list, tuple)):
        unique_id = unique_id[0] if unique_id else None
    if unique_id is None:
        stream_key = "default"
    else:
        stream_key = f"node:{unique_id}"
    key = f"{int(master_seed)}:{stream_key}"
    if suffix:
        key = f"{key}:{suffix}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:16], 16)


def spec_bypass_gated(seed, unique_id=None):
    """Independent PCG64 50% gate; same integers(0, 2) as the line pick."""
    gate_seed = spec_stream_seed(seed, unique_id, "gate")
    return int(np.random.default_rng(gate_seed).integers(0, 2)) == 0


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
    def test_required_keys_are_input_and_bypass(self):
        required = UniqueLinePicker.INPUT_TYPES()["required"]
        self.assertEqual(set(required.keys()), {"input", "bypass_chance"})

    def test_bypass_chance_widget_matches_seeded_text_pool(self):
        widget = UniqueLinePicker.INPUT_TYPES()["required"]["bypass_chance"]
        self.assertEqual(widget[0], "BOOLEAN")
        self.assertEqual(widget[1].get("default"), False)
        self.assertEqual(widget[1].get("label_on"), "50%")
        self.assertEqual(widget[1].get("label_off"), "Off")

    def test_hidden_inputs(self):
        hidden = UniqueLinePicker.INPUT_TYPES().get("hidden", {})
        self.assertEqual(hidden.get("unique_id"), "UNIQUE_ID")
        self.assertIn("dpe_seed", hidden)

    def test_input_is_socket_only(self):
        socket = UniqueLinePicker.INPUT_TYPES()["required"]["input"]
        self.assertEqual(socket[0], "STRING")
        self.assertTrue(socket[1].get("forceInput"))
        self.assertNotIn("multiline", socket[1])

    def test_return_types_and_names(self):
        self.assertEqual(UniqueLinePicker.RETURN_TYPES, ("STRING",))
        self.assertEqual(UniqueLinePicker.RETURN_NAMES, ("text",))


class TestUniqueLinePickerEmptyPool(_LinePickerTestBase):

    def test_empty_string_returns_empty_text(self):
        self.assertEqual(self.node.pick_line("", dpe_seed=42), ("",))

    def test_none_pool_returns_empty_text(self):
        self.assertEqual(self.node.pick_line(None, dpe_seed=7), ("",))

    def test_whitespace_only_returns_empty_text(self):
        self.assertEqual(self.node.pick_line("   \n\t\n  ", dpe_seed=1), ("",))

    def test_only_blank_lines_returns_empty_text(self):
        self.assertEqual(self.node.pick_line("\n\n\n", dpe_seed=9), ("",))


class TestUniqueLinePickerCandidates(_LinePickerTestBase):

    def test_blank_lines_are_dropped_and_lines_are_stripped(self):
        pool = "  alice  \n\n  \nbob\n"
        text, = self.node.pick_line(pool, dpe_seed=0, unique_id="1")
        self.assertIn(text, ("alice", "bob"))

    def test_crlf_and_lf_produce_the_same_candidates(self):
        lf = "alice\nbob\ncharlie"
        crlf = "alice\r\nbob\r\ncharlie"
        for seed in range(20):
            lf_text, = self.node.pick_line(lf, dpe_seed=seed, unique_id="1")
            crlf_text, = self.node.pick_line(crlf, dpe_seed=seed, unique_id="1")
            self.assertEqual(lf_text, crlf_text)

    def test_single_candidate_always_wins(self):
        for seed in (0, 1, 42, 999):
            text, = self.node.pick_line(
                "only", dpe_seed=seed, unique_id="1"
            )
            self.assertEqual(text, "only")

    def test_duplicate_lines_are_distinct_candidates(self):
        pool = "alice\nalice\nbob"
        lines = _candidates(pool)
        self.assertEqual(len(lines), 3)
        uid = "9"
        seen_indexes = set()
        for seed in range(200):
            text, = self.node.pick_line(pool, dpe_seed=seed, unique_id=uid)
            index = int(
                np.random.default_rng(spec_stream_seed(seed, uid)).integers(
                    0, 3
                )
            )
            self.assertEqual(text, lines[index])
            seen_indexes.add(index)
        self.assertEqual(seen_indexes, {0, 1, 2})


class TestUniqueLinePickerEmptyLiteral(_LinePickerTestBase):

    def test_only_empty_literal_emits_blank(self):
        text, = self.node.pick_line("[empty]", dpe_seed=5, unique_id="1")
        self.assertEqual(text, "")

    def test_padded_empty_literal_is_a_candidate(self):
        text, = self.node.pick_line("  [empty]  ", dpe_seed=0, unique_id="1")
        self.assertEqual(text, "")

    def test_empty_literal_is_case_sensitive(self):
        text, = self.node.pick_line("[Empty]", dpe_seed=0, unique_id="1")
        self.assertEqual(text, "[Empty]")

    def test_mixed_pool_can_select_empty_literal(self):
        pool = "alice\n[empty]\nbob"
        found_empty = False
        found_other = False
        for seed in range(300):
            text, = self.node.pick_line(pool, dpe_seed=seed, unique_id="1")
            if text == "":
                found_empty = True
            else:
                self.assertIn(text, ("alice", "bob"))
                found_other = True
            if found_empty and found_other:
                break
        self.assertTrue(found_empty, "expected some seed to pick [empty]")
        self.assertTrue(found_other, "expected some seed to pick a real line")


class TestUniqueLinePickerDeterminism(_LinePickerTestBase):
    def setUp(self):
        super().setUp()
        self.pool = "alice\nbob\ncharlie"

    def test_same_seed_and_unique_id_is_deterministic(self):
        text_1, = self.node.pick_line(self.pool, dpe_seed=42, unique_id="55")
        text_2, = self.node.pick_line(self.pool, dpe_seed=42, unique_id="55")
        self.assertEqual(text_1, text_2)

    def test_same_seed_matches_independent_pcg64(self):
        for seed in (0, 1, 42, 100, 999, 2**32):
            text, = self.node.pick_line(
                self.pool, dpe_seed=seed, unique_id="55"
            )
            self.assertEqual(text, spec_pick(self.pool, seed, "55"))

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
            text, = self.node.pick_line(self.pool, dpe_seed=seed, unique_id=uid)
            expected_text = (
                "" if lines[expected_index] == "[empty]" else lines[expected_index]
            )
            self.assertEqual(text, expected_text)

    def test_empty_pool_returns_empty_text(self):
        for pool in ("", None, "   \n  ", "\n\n"):
            for seed in (0, 42, 999):
                text, = self.node.pick_line(pool, dpe_seed=seed, unique_id="1")
                self.assertEqual(text, "")

    def test_unique_id_list_matches_string(self):
        a, = self.node.pick_line(self.pool, dpe_seed=7, unique_id="55")
        b, = self.node.pick_line(self.pool, dpe_seed=7, unique_id=["55"])
        self.assertEqual(a, b)

    def test_missing_unique_id_uses_default_stream(self):
        text, = self.node.pick_line(self.pool, dpe_seed=7)
        self.assertEqual(text, spec_pick(self.pool, 7, unique_id=None))

    def test_different_nodes_can_pick_different_lines(self):
        differing = 0
        for seed in range(40):
            a, = self.node.pick_line(self.pool, dpe_seed=seed, unique_id="10")
            b, = self.node.pick_line(self.pool, dpe_seed=seed, unique_id="20")
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
        text, = self.node.pick_line(self.pool, dpe_seed=seed, unique_id=uid)
        self.assertEqual(text, _candidates(self.pool)[mixed_index])
        self.assertNotEqual(text, _candidates(self.pool)[plain_index])

    def test_different_seeds_can_pick_different_lines(self):
        seen = {
            self.node.pick_line(self.pool, dpe_seed=s, unique_id="1")[0]
            for s in range(50)
        }
        self.assertGreater(len(seen), 1)

    def test_does_not_mutate_stdlib_random(self):
        random.seed(123)
        before = random.random()
        random.seed(123)
        self.node.pick_line(self.pool, dpe_seed=99, unique_id="1")
        after = random.random()
        self.assertEqual(before, after)


class TestUniqueLinePickerNoWildcardExpansion(unittest.TestCase):
    def setUp(self):
        self.node = UniqueLinePicker()

    def test_brace_syntax_is_returned_literally(self):
        text, = self.node.pick_line("{red|blue}", dpe_seed=0, unique_id="1")
        self.assertEqual(text, "{red|blue}")

    def test_underscore_wildcard_is_returned_literally(self):
        text, = self.node.pick_line("__colors__", dpe_seed=0, unique_id="1")
        self.assertEqual(text, "__colors__")

    def test_chosen_line_with_wildcard_syntax_is_not_expanded(self):
        pool = "{a|b}\nplain"
        for seed in range(40):
            text, = self.node.pick_line(pool, dpe_seed=seed, unique_id="1")
            self.assertEqual(text, spec_pick(pool, seed, "1"))
            self.assertIn(text, ("{a|b}", "plain"))


class TestUniqueLinePickerBypassChance(_LinePickerTestBase):
    def setUp(self):
        super().setUp()
        self.pool = "alice\nbob\ncharlie"

    def test_off_never_gates(self):
        for seed in range(80):
            text, = self.node.pick_line(
                self.pool, bypass_chance=False, dpe_seed=seed, unique_id="1"
            )
            self.assertEqual(text, spec_pick(self.pool, seed, "1"))
            self.assertIn(text, ("alice", "bob", "charlie"))

    def test_fifty_percent_matches_independent_pcg64_gate(self):
        uid = "55"
        gated = 0
        picked = 0
        for seed in range(200):
            text, = self.node.pick_line(
                self.pool, bypass_chance=True, dpe_seed=seed, unique_id=uid
            )
            if spec_bypass_gated(seed, uid):
                self.assertEqual(text, "")
                gated += 1
            else:
                self.assertEqual(text, spec_pick(self.pool, seed, uid))
                picked += 1
        self.assertGreater(gated, 0)
        self.assertGreater(picked, 0)

    def test_gate_does_not_use_hash_mod_two(self):
        uid = "7"
        mismatch = 0
        for seed in range(80):
            hash_even = spec_stream_seed(seed, uid, "gate") % 2 == 0
            pcg_even = spec_bypass_gated(seed, uid)
            if hash_even != pcg_even:
                mismatch += 1
                text, = self.node.pick_line(
                    self.pool, bypass_chance=True, dpe_seed=seed, unique_id=uid
                )
                self.assertEqual(text == "", pcg_even)
        self.assertGreater(mismatch, 0)

    def test_gate_runs_on_empty_pool(self):
        text, = self.node.pick_line(
            "", bypass_chance=True, dpe_seed=3, unique_id="1"
        )
        self.assertEqual(text, "")

    def test_gate_is_independent_of_pick_stream(self):
        uid = "1"
        pick_seed = spec_stream_seed(42, uid)
        gate_seed = spec_stream_seed(42, uid, "gate")
        self.assertNotEqual(pick_seed, gate_seed)

    def test_does_not_mutate_stdlib_random_when_gating(self):
        random.seed(123)
        before = random.random()
        random.seed(123)
        self.node.pick_line(
            self.pool, bypass_chance=True, dpe_seed=99, unique_id="1"
        )
        after = random.random()
        self.assertEqual(before, after)


class TestUniqueLinePickerSpread(_LinePickerTestBase):
    def test_three_thousand_seeds_hit_every_line_hundreds_of_times(self):
        node = self.picker_factory()
        pool = "alice\nbob\ncharlie"
        counts = {"alice": 0, "bob": 0, "charlie": 0}
        for seed in range(3000):
            text, = node.pick_line(pool, dpe_seed=seed, unique_id="1")
            counts[text] += 1
        for name, count in counts.items():
            self.assertGreaterEqual(
                count,
                300,
                f"{name} only picked {count} times in 3000 seeds",
            )


class TestSeededTextPoolInputTypes(unittest.TestCase):
    def test_required_keys_are_pool_and_bypass(self):
        required = SeededTextPool.INPUT_TYPES()["required"]
        self.assertEqual(set(required.keys()), {"pool_text", "bypass_chance"})

    def test_pool_text_is_multiline(self):
        widget = SeededTextPool.INPUT_TYPES()["required"]["pool_text"]
        self.assertEqual(widget[0], "STRING")
        self.assertTrue(widget[1].get("multiline"))

    def test_bypass_chance_widget_matches_unique_line_picker(self):
        pool = SeededTextPool.INPUT_TYPES()["required"]["bypass_chance"]
        picker = UniqueLinePicker.INPUT_TYPES()["required"]["bypass_chance"]
        self.assertEqual(pool, picker)

    def test_return_types_and_names(self):
        self.assertEqual(SeededTextPool.RETURN_TYPES, ("STRING",))
        self.assertEqual(SeededTextPool.RETURN_NAMES, ("text",))


class TestSeededTextPoolInheritsLinePicker:
    @staticmethod
    def picker_factory():
        return SeededTextPoolAsLinePicker()


class TestSeededTextPoolEmptyPool(TestSeededTextPoolInheritsLinePicker, TestUniqueLinePickerEmptyPool):
    pass


class TestSeededTextPoolCandidates(TestSeededTextPoolInheritsLinePicker, TestUniqueLinePickerCandidates):
    pass


class TestSeededTextPoolEmptyLiteral(TestSeededTextPoolInheritsLinePicker, TestUniqueLinePickerEmptyLiteral):
    pass


class TestSeededTextPoolDeterminism(TestSeededTextPoolInheritsLinePicker, TestUniqueLinePickerDeterminism):
    pass


class TestSeededTextPoolBypassChance(TestSeededTextPoolInheritsLinePicker, TestUniqueLinePickerBypassChance):
    pass


class TestSeededTextPoolSpread(TestSeededTextPoolInheritsLinePicker, TestUniqueLinePickerSpread):
    pass


if __name__ == "__main__":
    unittest.main()
