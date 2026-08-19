"""Tests for UniqueWildcardProcessor.

Stolen cases come from ComfyUI-Impact-Pack:
  tests/wildcards/test_versatile_prompts.sh
  tests/test_dynamic_prompts_full.sh
  tests/test_error_handling.sh
  tests/test_encoding.sh
  tests/wildcards/test_wildcard_final.py
"""

import hashlib
import unittest
from unittest.mock import patch

from dynamic_prompt_engine.impact_loader import ensure_impact_wildcards
from dynamic_prompt_engine.prompt_engine_nodes import SeededTextPool
from dynamic_prompt_engine.wildcard_processor import UniqueWildcardProcessor


try:
    impact_process = ensure_impact_wildcards(mode="dev")
    IMPACT_PROCESS_AVAILABLE = True
except Exception:
    impact_process = None
    IMPACT_PROCESS_AVAILABLE = False


class SeededTextPoolAsWildcard:
    """Adapter: single-line pool_text pick is identity, then Impact expand."""

    def doit(self, populated_text, seed=0, unique_id=None):
        text, _ = SeededTextPool().select_from_pool(
            populated_text, bypass_chance=False, seed=seed, unique_id=unique_id
        )
        return (text,)


class _WildcardTestBase(unittest.TestCase):
    PROCESS_PATCH = (
        "dynamic_prompt_engine.wildcard_processor.process_impact_wildcards"
    )

    @staticmethod
    def node_factory():
        return UniqueWildcardProcessor()

    def setUp(self):
        self.node = self.node_factory()

    def expand(self, text, seed, unique_id="1"):
        (result,) = self.node.doit(
            populated_text=text, seed=seed, unique_id=unique_id
        )
        return result


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


class TestUniqueWildcardProcessorInputTypes(unittest.TestCase):
    def test_required_keys_are_only_populated_text_and_seed(self):
        required = UniqueWildcardProcessor.INPUT_TYPES()["required"]
        self.assertEqual(set(required.keys()), {"populated_text", "seed"})

    def test_removed_impact_fields_are_absent(self):
        required = UniqueWildcardProcessor.INPUT_TYPES()["required"]
        self.assertNotIn("wildcard_text", required)
        self.assertNotIn("mode", required)
        self.assertNotIn("Select to add Wildcard", required)

    def test_unique_id_is_hidden(self):
        hidden = UniqueWildcardProcessor.INPUT_TYPES().get("hidden", {})
        self.assertEqual(hidden.get("unique_id"), "UNIQUE_ID")


class TestUniqueWildcardProcessorProcess(_WildcardTestBase):
    def test_plain_text_returns_unchanged(self):
        template = "a red fox"
        (result,) = self.node.doit(populated_text=template, seed=42)
        self.assertEqual(result, "a red fox")
        self.assertEqual(template, "a red fox")

    def test_wildcard_text_is_expanded_with_mixed_seed(self):
        with patch(self.PROCESS_PATCH) as process_wildcards:
            process_wildcards.return_value = "expanded prompt"
            template = "a {red|blue} fox"
            (result,) = self.node.doit(
                populated_text=template, seed=7, unique_id="55"
            )
            process_wildcards.assert_called_once_with(
                template, spec_stream_seed(7, "55")
            )
            self.assertEqual(result, "expanded prompt")
            self.assertEqual(template, "a {red|blue} fox")

    def test_plain_text_ignores_unique_id(self):
        a, = self.node.doit(populated_text="plain", seed=1, unique_id="10")
        b, = self.node.doit(populated_text="plain", seed=1, unique_id="20")
        self.assertEqual(a, "plain")
        self.assertEqual(b, "plain")


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestUniqueWildcardProcessorUniqueId(_WildcardTestBase):
    def setUp(self):
        super().setUp()
        self.prompt = "{red|green|blue}"

    def test_same_seed_and_unique_id_is_deterministic(self):
        a = self.expand(self.prompt, 42, unique_id="55")
        b = self.expand(self.prompt, 42, unique_id="55")
        self.assertEqual(a, b)

    def test_unique_id_list_matches_string(self):
        a, = self.node.doit(
            populated_text=self.prompt, seed=7, unique_id="55"
        )
        b, = self.node.doit(
            populated_text=self.prompt, seed=7, unique_id=["55"]
        )
        self.assertEqual(a, b)

    def test_missing_unique_id_uses_default_stream(self):
        text, = self.node.doit(populated_text=self.prompt, seed=7)
        self.assertEqual(text, self.expand(self.prompt, 7, unique_id=None))

    def test_different_nodes_can_expand_differently(self):
        differing = 0
        for seed in range(80):
            a = self.expand(self.prompt, seed, unique_id="10")
            b = self.expand(self.prompt, seed, unique_id="20")
            if a != b:
                differing += 1
        self.assertGreater(
            differing,
            0,
            "Expected at least one seed where different unique_ids expand "
            "differently.",
        )

    def test_seed_zero_and_large_seed_expand(self):
        for seed in (0, 2**32):
            result = self.expand(self.prompt, seed, unique_id="1")
            self.assertIn(result, {"red", "green", "blue"})


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestUniqueWildcardProcessorOracle(_WildcardTestBase):
    def test_doit_equals_impact_process_with_mixed_seed(self):
        prompt = "{blue apple|red {cherry|berry}|green melon}"
        uid = "55"
        for seed in (0, 1, 42, 100, 999):
            ours, = self.node.doit(
                populated_text=prompt, seed=seed, unique_id=uid
            )
            vanilla = impact_process(prompt, spec_stream_seed(seed, uid))
            self.assertEqual(ours, vanilla)

    def test_raw_seed_is_not_the_impact_seed(self):
        prompt = "{red|green|blue}"
        seed = 2
        uid = "55"
        mixed = spec_stream_seed(seed, uid)
        vanilla_raw = impact_process(prompt, seed)
        vanilla_mixed = impact_process(prompt, mixed)
        if vanilla_raw == vanilla_mixed:
            self.skipTest("this seed collides between raw and mixed streams")
        ours, = self.node.doit(
            populated_text=prompt, seed=seed, unique_id=uid
        )
        self.assertEqual(ours, vanilla_mixed)
        self.assertNotEqual(ours, vanilla_raw)


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestUniqueWildcardProcessorSpread(_WildcardTestBase):
    def test_three_thousand_seeds_hit_every_color_hundreds_of_times(self):
        prompt = "{red|green|blue}"
        counts = {"red": 0, "green": 0, "blue": 0}
        for seed in range(3000):
            counts[self.expand(prompt, seed, unique_id="1")] += 1
        for name, count in counts.items():
            self.assertGreaterEqual(
                count,
                300,
                f"{name} only picked {count} times in 3000 seeds",
            )


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestStolenVersatileDynamicPrompts(_WildcardTestBase):
    """From tests/wildcards/test_versatile_prompts.sh (dynamic-prompt cases)."""

    def test_04_simple_dynamic(self):
        result = self.expand("{red|green|blue} apple", 100)
        self.assertIn(result, {"red apple", "green apple", "blue apple"})

    def test_05_nested_dynamic(self):
        result = self.expand("{a|{d|e|f}|c}", 100)
        self.assertIn(result, {"a", "d", "e", "f", "c"})

    def test_06_complex_nested(self):
        result = self.expand("{blue apple|red {cherry|berry}|green melon}", 100)
        self.assertIn(
            result,
            {"blue apple", "red cherry", "red berry", "green melon"},
        )

    def test_07_weighted_selection(self):
        result = self.expand("{5::red|4::green|7::blue|black} car", 100)
        self.assertIn(result, {"red car", "green car", "blue car", "black car"})

    def test_08_weighted_complex(self):
        result = self.expand(
            "A {10::beautiful|5::stunning|amazing} {3::sunset|2::sunrise|dawn}",
            100,
        )
        first, second = result.removeprefix("A ").split(" ", 1)
        self.assertIn(first, {"beautiful", "stunning", "amazing"})
        self.assertIn(second, {"sunset", "sunrise", "dawn"})

    def test_15_multiselect_fixed(self):
        result = self.expand("{2$$, $$red|green|blue|yellow|purple}", 100)
        items = [part.strip() for part in result.split(",")]
        self.assertEqual(len(items), 2)
        self.assertEqual(len(set(items)), 2)
        allowed = {"red", "green", "blue", "yellow", "purple"}
        self.assertTrue(set(items).issubset(allowed))

    def test_16_multiselect_range(self):
        result = self.expand("{1-3$$, $$apple|banana|orange|grape|mango}", 100)
        items = [part.strip() for part in result.split(",") if part.strip()]
        self.assertGreaterEqual(len(items), 1)
        self.assertLessEqual(len(items), 3)
        allowed = {"apple", "banana", "orange", "grape", "mango"}
        self.assertTrue(set(items).issubset(allowed))

    def test_17_multiselect_custom_sep(self):
        result = self.expand("{2$$ and $$cat|dog|bird|fish}", 100)
        items = [part.strip() for part in result.split(" and ")]
        self.assertEqual(len(items), 2)
        self.assertEqual(len(set(items)), 2)
        self.assertTrue(set(items).issubset({"cat", "dog", "bird", "fish"}))

    def test_18_multiselect_or_sep(self):
        result = self.expand("{2-3$$ or $$happy|sad|excited|calm}", 100)
        items = [part.strip() for part in result.split(" or ")]
        self.assertGreaterEqual(len(items), 2)
        self.assertLessEqual(len(items), 3)
        self.assertTrue(set(items).issubset({"happy", "sad", "excited", "calm"}))

    def test_26_empty_dynamic_option(self):
        result = self.expand("{|something|nothing}", 100)
        self.assertIn(result, {"", "something", "nothing"})

    def test_27_single_option(self):
        self.assertEqual(self.expand("{only_one}", 100), "only_one")

    def test_28_deeply_nested(self):
        result = self.expand("{a|{b|{c|{d|e}}}}", 100)
        self.assertIn(result, {"a", "b", "c", "d", "e"})

    def test_29_extreme_weights(self):
        result = self.expand("{100::common|10::uncommon|1::rare|super_rare}", 100)
        self.assertIn(result, {"common", "uncommon", "rare", "super_rare"})

    def test_same_seed_is_deterministic(self):
        prompt = "{blue apple|red {cherry|berry}|green melon}"
        self.assertEqual(self.expand(prompt, 100), self.expand(prompt, 100))


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestStolenDynamicPromptsFull(_WildcardTestBase):
    """From tests/test_dynamic_prompts_full.sh."""

    def _multiselect(self, prompt, expected_count, separator, options, iterations=20):
        for i in range(1, iterations + 1):
            seed = 1000 + i * 100
            result = self.expand(prompt, seed)
            if separator:
                items = result.split(separator)
            else:
                items = [result]
            self.assertEqual(len(items), expected_count, result)
            self.assertEqual(len(set(items)), expected_count, result)
            for item in items:
                self.assertIn(item.strip(), options, result)

    def test_1_two_item_multiselect(self):
        self._multiselect(
            "{2$$, $$red|blue|green|yellow}",
            2,
            ", ",
            ["red", "blue", "green", "yellow"],
        )

    def test_2_three_item_multiselect(self):
        self._multiselect(
            "{3$$ and $$alpha|beta|gamma|delta|epsilon}",
            3,
            " and ",
            ["alpha", "beta", "gamma", "delta", "epsilon"],
        )

    def test_3_single_item_multiselect(self):
        self._multiselect("{1$$ $$one|two|three}", 1, None, ["one", "two", "three"])

    def test_4_max_item_multiselect(self):
        self._multiselect(
            "{4$$-$$cat|dog|bird|fish}",
            4,
            "-",
            ["cat", "dog", "bird", "fish"],
        )

    def _weighted_always_valid(self, prompt, options, iterations):
        seen = {opt: 0 for opt in options}
        for i in range(1, iterations + 1):
            result = self.expand(prompt, 1000 + i * 100)
            self.assertIn(result, options, result)
            seen[result] += 1
        return seen

    def test_5_heavy_bias_10_to_1(self):
        seen = self._weighted_always_valid("{10::common|1::rare}", ["common", "rare"], 100)
        self.assertGreater(seen["common"], seen["rare"])

    def test_6_equal_weights(self):
        seen = self._weighted_always_valid(
            "{1::alpha|1::beta|1::gamma}", ["alpha", "beta", "gamma"], 60
        )
        self.assertTrue(all(count > 0 for count in seen.values()), seen)

    def test_7_extreme_bias_100_to_1(self):
        seen = self._weighted_always_valid(
            "{100::very_common|1::very_rare}", ["very_common", "very_rare"], 100
        )
        self.assertGreater(seen["very_common"], seen["very_rare"])

    def test_8_multilevel_weights(self):
        self._weighted_always_valid(
            "{5::high|3::medium|2::low}", ["high", "medium", "low"], 100
        )

    def test_9_default_weight_mixing(self):
        self._weighted_always_valid(
            "{10::weighted|unweighted}", ["weighted", "unweighted"], 100
        )

    def test_10_simple_random_selection(self):
        seen = self._weighted_always_valid(
            "{option_a|option_b|option_c}",
            ["option_a", "option_b", "option_c"],
            50,
        )
        self.assertTrue(all(count > 0 for count in seen.values()), seen)

    def test_11_nested_selection(self):
        self._weighted_always_valid(
            "{outer_{inner1|inner2}|simple}",
            ["outer_inner1", "outer_inner2", "simple"],
            50,
        )


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestStolenErrorHandling(_WildcardTestBase):
    """From tests/test_error_handling.sh (in-prompt cases, no sample files)."""

    def test_04_missing_wildcard_does_not_crash(self):
        result = self.expand("__this_file_does_not_exist__", 42)
        self.assertIsInstance(result, str)
        self.assertTrue(result)

    def test_06_empty_dynamic_option(self):
        result = self.expand("{|something|nothing}", 42)
        self.assertIn(result, {"", "something", "nothing"})

    def test_07_single_option_dynamic(self):
        self.assertEqual(self.expand("{only_one}", 42), "only_one")

    def test_08_unclosed_bracket_does_not_crash(self):
        result = self.expand("{option1|option2", 42)
        self.assertIsInstance(result, str)
        self.assertTrue(result)

    def test_09_very_deep_nesting(self):
        result = self.expand("{a|{b|{c|{d|{e|{f|{g|{h|i}}}}}}}}", 42)
        self.assertIn(result, list("abcdefghi"))
        self.assertEqual(
            result, self.expand("{a|{b|{c|{d|{e|{f|{g|{h|i}}}}}}}}", 42)
        )


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestStolenEncoding(_WildcardTestBase):
    """From tests/test_encoding.sh (cases that do not need sample files)."""

    def test_05_multiple_emojis_passthrough(self):
        text = "🌸 beautiful 🌺 garden 🌼"
        self.assertEqual(self.expand(text, 500), text)

    def test_06_emoji_in_dynamic_prompt(self):
        result = self.expand("{🌸|🌺|🌼|🌻|🌷}", 600)
        self.assertIn(result, {"🌸", "🌺", "🌼", "🌻", "🌷"})

    def test_08_currency_symbols(self):
        result = self.expand("Price: {$|€|£|¥|₩} 100", 800)
        self.assertRegex(result, r"^Price: [\$€£¥₩] 100$")

    def test_11_arabic_passthrough(self):
        self.assertEqual(self.expand("زهرة جميلة", 1100), "زهرة جميلة")

    def test_14_mixed_utf8_weighted(self):
        result = self.expand("{5::🌸|3::장미|2::花}", 1400)
        self.assertIn(result, {"🌸", "장미", "花"})


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestStolenWildcardFinal(_WildcardTestBase):
    """From tests/wildcards/test_wildcard_final.py."""

    def test_3_dynamic_prompt(self):
        result = self.expand("{red|blue|green} flower", 456)
        self.assertIn(result, {"red flower", "blue flower", "green flower"})

    def test_5_multiselect_without_file_wildcards(self):
        result = self.expand("{2$$, $$rose|tulip|daisy}", 111)
        items = [part.strip() for part in result.split(",")]
        self.assertEqual(len(items), 2)
        self.assertTrue(set(items).issubset({"rose", "tulip", "daisy"}))


class _SeededTextPoolWildcardOverrides:
    PROCESS_PATCH = (
        "dynamic_prompt_engine.prompt_engine_nodes.process_impact_wildcards"
    )

    @staticmethod
    def node_factory():
        return SeededTextPoolAsWildcard()


class TestSeededTextPoolWildcardProcess(
    _SeededTextPoolWildcardOverrides, TestUniqueWildcardProcessorProcess
):
    pass


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestSeededTextPoolWildcardUniqueId(
    _SeededTextPoolWildcardOverrides, TestUniqueWildcardProcessorUniqueId
):
    pass


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestSeededTextPoolWildcardOracle(
    _SeededTextPoolWildcardOverrides, TestUniqueWildcardProcessorOracle
):
    pass


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestSeededTextPoolWildcardSpread(
    _SeededTextPoolWildcardOverrides, TestUniqueWildcardProcessorSpread
):
    pass


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestSeededTextPoolStolenVersatile(
    _SeededTextPoolWildcardOverrides, TestStolenVersatileDynamicPrompts
):
    pass


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestSeededTextPoolStolenDynamicFull(
    _SeededTextPoolWildcardOverrides, TestStolenDynamicPromptsFull
):
    pass


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestSeededTextPoolStolenErrorHandling(
    _SeededTextPoolWildcardOverrides, TestStolenErrorHandling
):
    pass


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestSeededTextPoolStolenEncoding(
    _SeededTextPoolWildcardOverrides, TestStolenEncoding
):
    pass


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestSeededTextPoolStolenWildcardFinal(
    _SeededTextPoolWildcardOverrides, TestStolenWildcardFinal
):
    pass


if __name__ == "__main__":
    unittest.main()
