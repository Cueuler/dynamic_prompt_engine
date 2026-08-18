"""Tests for WildcardProcessor.

Stolen cases come from ComfyUI-Impact-Pack:
  tests/wildcards/test_versatile_prompts.sh
  tests/test_dynamic_prompts_full.sh
  tests/test_error_handling.sh
  tests/test_encoding.sh
  tests/wildcards/test_wildcard_final.py
"""

import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

IMPACT_MODULES = (
    Path(__file__).resolve().parent / "ComfyUI-Impact-Pack" / "modules"
)


def _install_impact_stubs():
    """Load Impact wildcards.process without ComfyUI (folder_paths, nodes, utils)."""
    if not IMPACT_MODULES.is_dir():
        raise ImportError("ComfyUI-Impact-Pack/modules not found")
    if str(IMPACT_MODULES) not in sys.path:
        sys.path.insert(0, str(IMPACT_MODULES))
    if "folder_paths" not in sys.modules:
        folder_paths = ModuleType("folder_paths")
        folder_paths.get_filename_list = lambda name: []
        folder_paths.get_full_path = lambda *a, **k: None
        folder_paths.supported_pt_extensions = set()
        folder_paths.models_dir = "/tmp"
        sys.modules["folder_paths"] = folder_paths
    if "nodes" not in sys.modules:
        nodes = ModuleType("nodes")
        nodes.NODE_CLASS_MAPPINGS = {}
        sys.modules["nodes"] = nodes
    if "impact.utils" not in sys.modules:
        sys.modules["impact.utils"] = ModuleType("impact.utils")
    import numpy  # noqa: F401
    import yaml  # noqa: F401
    from impact.wildcards import process  # noqa: F401

    return process


try:
    _install_impact_stubs()
    IMPACT_PROCESS_AVAILABLE = True
except Exception:
    IMPACT_PROCESS_AVAILABLE = False

from dynamic_prompt_engine.wildcard_processor import WildcardProcessor


def expand(text, seed):
    (result,) = WildcardProcessor().doit(populated_text=text, seed=seed)
    return result


class TestWildcardProcessorInputTypes(unittest.TestCase):
    def test_required_keys_are_only_populated_text_and_seed(self):
        required = WildcardProcessor.INPUT_TYPES()["required"]
        self.assertEqual(set(required.keys()), {"populated_text", "seed"})

    def test_removed_impact_fields_are_absent(self):
        required = WildcardProcessor.INPUT_TYPES()["required"]
        self.assertNotIn("wildcard_text", required)
        self.assertNotIn("mode", required)
        self.assertNotIn("Select to add Wildcard", required)


class TestWildcardProcessorProcess(unittest.TestCase):
    def setUp(self):
        self.node = WildcardProcessor()

    def test_plain_text_returns_unchanged(self):
        template = "a red fox"
        (result,) = self.node.doit(populated_text=template, seed=42)
        self.assertEqual(result, "a red fox")
        self.assertEqual(template, "a red fox")

    @patch("dynamic_prompt_engine.wildcard_processor.process_impact_wildcards")
    def test_wildcard_text_is_expanded_with_seed(self, process_wildcards):
        process_wildcards.return_value = "expanded prompt"
        template = "a {red|blue} fox"
        (result,) = self.node.doit(populated_text=template, seed=7)
        process_wildcards.assert_called_once_with(template, 7)
        self.assertEqual(result, "expanded prompt")
        self.assertEqual(template, "a {red|blue} fox")


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestStolenVersatileDynamicPrompts(unittest.TestCase):
    """From tests/wildcards/test_versatile_prompts.sh (dynamic-prompt cases)."""

    def test_04_simple_dynamic(self):
        result = expand("{red|green|blue} apple", 100)
        self.assertIn(result, {"red apple", "green apple", "blue apple"})

    def test_05_nested_dynamic(self):
        result = expand("{a|{d|e|f}|c}", 100)
        self.assertIn(result, {"a", "d", "e", "f", "c"})

    def test_06_complex_nested(self):
        result = expand("{blue apple|red {cherry|berry}|green melon}", 100)
        self.assertIn(
            result,
            {"blue apple", "red cherry", "red berry", "green melon"},
        )

    def test_07_weighted_selection(self):
        result = expand("{5::red|4::green|7::blue|black} car", 100)
        self.assertIn(result, {"red car", "green car", "blue car", "black car"})

    def test_08_weighted_complex(self):
        result = expand(
            "A {10::beautiful|5::stunning|amazing} {3::sunset|2::sunrise|dawn}",
            100,
        )
        first, second = result.removeprefix("A ").split(" ", 1)
        self.assertIn(first, {"beautiful", "stunning", "amazing"})
        self.assertIn(second, {"sunset", "sunrise", "dawn"})

    def test_15_multiselect_fixed(self):
        result = expand("{2$$, $$red|green|blue|yellow|purple}", 100)
        items = [part.strip() for part in result.split(",")]
        self.assertEqual(len(items), 2)
        self.assertEqual(len(set(items)), 2)
        allowed = {"red", "green", "blue", "yellow", "purple"}
        self.assertTrue(set(items).issubset(allowed))

    def test_16_multiselect_range(self):
        result = expand("{1-3$$, $$apple|banana|orange|grape|mango}", 100)
        items = [part.strip() for part in result.split(",") if part.strip()]
        self.assertGreaterEqual(len(items), 1)
        self.assertLessEqual(len(items), 3)
        allowed = {"apple", "banana", "orange", "grape", "mango"}
        self.assertTrue(set(items).issubset(allowed))

    def test_17_multiselect_custom_sep(self):
        result = expand("{2$$ and $$cat|dog|bird|fish}", 100)
        items = [part.strip() for part in result.split(" and ")]
        self.assertEqual(len(items), 2)
        self.assertEqual(len(set(items)), 2)
        self.assertTrue(set(items).issubset({"cat", "dog", "bird", "fish"}))

    def test_18_multiselect_or_sep(self):
        result = expand("{2-3$$ or $$happy|sad|excited|calm}", 100)
        items = [part.strip() for part in result.split(" or ")]
        self.assertGreaterEqual(len(items), 2)
        self.assertLessEqual(len(items), 3)
        self.assertTrue(set(items).issubset({"happy", "sad", "excited", "calm"}))

    def test_26_empty_dynamic_option(self):
        result = expand("{|something|nothing}", 100)
        self.assertIn(result, {"", "something", "nothing"})

    def test_27_single_option(self):
        self.assertEqual(expand("{only_one}", 100), "only_one")

    def test_28_deeply_nested(self):
        result = expand("{a|{b|{c|{d|e}}}}", 100)
        self.assertIn(result, {"a", "b", "c", "d", "e"})

    def test_29_extreme_weights(self):
        result = expand("{100::common|10::uncommon|1::rare|super_rare}", 100)
        self.assertIn(result, {"common", "uncommon", "rare", "super_rare"})

    def test_same_seed_is_deterministic(self):
        prompt = "{blue apple|red {cherry|berry}|green melon}"
        self.assertEqual(expand(prompt, 100), expand(prompt, 100))


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestStolenDynamicPromptsFull(unittest.TestCase):
    """From tests/test_dynamic_prompts_full.sh."""

    def _multiselect(self, prompt, expected_count, separator, options, iterations=20):
        for i in range(1, iterations + 1):
            seed = 1000 + i * 100
            result = expand(prompt, seed)
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
            result = expand(prompt, 1000 + i * 100)
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
class TestStolenErrorHandling(unittest.TestCase):
    """From tests/test_error_handling.sh (in-prompt cases, no sample files)."""

    def test_04_missing_wildcard_does_not_crash(self):
        result = expand("__this_file_does_not_exist__", 42)
        self.assertIsInstance(result, str)
        self.assertTrue(result)

    def test_06_empty_dynamic_option(self):
        result = expand("{|something|nothing}", 42)
        self.assertIn(result, {"", "something", "nothing"})

    def test_07_single_option_dynamic(self):
        self.assertEqual(expand("{only_one}", 42), "only_one")

    def test_08_unclosed_bracket_does_not_crash(self):
        result = expand("{option1|option2", 42)
        self.assertIsInstance(result, str)
        self.assertTrue(result)

    def test_09_very_deep_nesting(self):
        result = expand("{a|{b|{c|{d|{e|{f|{g|{h|i}}}}}}}}", 42)
        self.assertIn(result, list("abcdefghi"))
        self.assertEqual(result, expand("{a|{b|{c|{d|{e|{f|{g|{h|i}}}}}}}}", 42))


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestStolenEncoding(unittest.TestCase):
    """From tests/test_encoding.sh (cases that do not need sample files)."""

    def test_05_multiple_emojis_passthrough(self):
        text = "🌸 beautiful 🌺 garden 🌼"
        self.assertEqual(expand(text, 500), text)

    def test_06_emoji_in_dynamic_prompt(self):
        result = expand("{🌸|🌺|🌼|🌻|🌷}", 600)
        self.assertIn(result, {"🌸", "🌺", "🌼", "🌻", "🌷"})

    def test_08_currency_symbols(self):
        result = expand("Price: {$|€|£|¥|₩} 100", 800)
        self.assertRegex(result, r"^Price: [\$€£¥₩] 100$")

    def test_11_arabic_passthrough(self):
        self.assertEqual(expand("زهرة جميلة", 1100), "زهرة جميلة")

    def test_14_mixed_utf8_weighted(self):
        result = expand("{5::🌸|3::장미|2::花}", 1400)
        self.assertIn(result, {"🌸", "장미", "花"})


@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, "numpy/PyYAML + Impact Pack modules required")
class TestStolenWildcardFinal(unittest.TestCase):
    """From tests/wildcards/test_wildcard_final.py."""

    def test_3_dynamic_prompt(self):
        result = expand("{red|blue|green} flower", 456)
        self.assertIn(result, {"red flower", "blue flower", "green flower"})

    def test_5_multiselect_without_file_wildcards(self):
        result = expand("{2$$, $$rose|tulip|daisy}", 111)
        items = [part.strip() for part in result.split(",")]
        self.assertEqual(len(items), 2)
        self.assertTrue(set(items).issubset({"rose", "tulip", "daisy"}))


if __name__ == "__main__":
    unittest.main()
