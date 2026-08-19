"""Tests for DPE Global Seed resolve/inject and picker schema changes."""

import unittest
from unittest.mock import MagicMock, patch

from dynamic_prompt_engine.global_seed import (
    DPEGlobalSeed,
    GlobalSeedError,
    PICKER_NODE_CLASSES,
    apply_global_seed_onprompt,
    master_seed_from_dpe,
    register_global_seed_handler,
    resolve_seed_from_prompt_value,
)
from dynamic_prompt_engine.prompt_engine_nodes import (
    BranchRandomSwitcher,
    RoutingSwitch,
    SeededTextPool,
    UniqueLinePicker,
)
from dynamic_prompt_engine.wildcard_processor import UniqueWildcardProcessor


def _prompt(**nodes):
    return {
        "prompt": {
            node_id: {"class_type": class_type, "inputs": inputs}
            for node_id, (class_type, inputs) in nodes.items()
        }
    }


def _picker_execute(dpe_seed):
    return UniqueLinePicker().pick_line("a\nb", dpe_seed=dpe_seed, unique_id="1")


class TestResolveSeedFromPromptValue(unittest.TestCase):
    def test_direct_int(self):
        self.assertEqual(resolve_seed_from_prompt_value(42, {}), 42)

    def test_linked_rgthree_style_seed(self):
        prompt = {
            "1": {"class_type": "Seed (rgthree)", "inputs": {"seed": 12345}},
            "2": {
                "class_type": "DPEGlobalSeed",
                "inputs": {"seed": ["1", 0]},
            },
        }
        self.assertEqual(
            resolve_seed_from_prompt_value(["1", 0], prompt),
            12345,
        )

    def test_widget_minus_one_not_error_when_prompt_has_int(self):
        """rgthree keeps -1 on canvas but prompt.inputs has the real INT."""
        prompt = {
            "1": {"class_type": "Seed (rgthree)", "inputs": {"seed": 99999}},
        }
        self.assertEqual(resolve_seed_from_prompt_value(99999, prompt), 99999)

    def test_special_seeds_error(self):
        for special in (-1, -2, -3):
            with self.subTest(special=special):
                with self.assertRaises(GlobalSeedError):
                    resolve_seed_from_prompt_value(special, {})

    def test_unresolvable_link_errors(self):
        with self.assertRaises(GlobalSeedError):
            resolve_seed_from_prompt_value(["missing", 0], {})

    def test_linked_node_without_seed_errors(self):
        prompt = {"1": {"class_type": "SomeNode", "inputs": {"text": "x"}}}
        with self.assertRaises(GlobalSeedError):
            resolve_seed_from_prompt_value(["1", 0], prompt)


class TestMasterSeedFromDpe(unittest.TestCase):
    def test_missing_raises(self):
        with self.assertRaises(GlobalSeedError) as ctx:
            master_seed_from_dpe(None, "UniqueLinePicker")
        self.assertIn("missing DPE Global Seed", str(ctx.exception))

    def test_error_string_raises_that_message(self):
        with self.assertRaises(GlobalSeedError) as ctx:
            master_seed_from_dpe("only one controller", "UniqueLinePicker")
        self.assertEqual(str(ctx.exception), "only one controller")

    def test_zero_is_valid(self):
        self.assertEqual(master_seed_from_dpe(0, "UniqueLinePicker"), 0)


class TestApplyGlobalSeedOnprompt(unittest.TestCase):
    def test_widget_int_injects_into_pickers(self):
        data = _prompt(
            gs=("DPEGlobalSeed", {"seed": 777}),
            p1=("UniqueLinePicker", {"input": "a\nb", "bypass_chance": False}),
            p2=("RoutingSwitch", {"input_0": "x", "chance_0": "Default"}),
        )
        result = apply_global_seed_onprompt(data)
        self.assertEqual(result["prompt"]["p1"]["inputs"]["dpe_seed"], 777)
        self.assertEqual(result["prompt"]["p2"]["inputs"]["dpe_seed"], 777)

    def test_linked_rgthree_injects_concrete_int(self):
        data = _prompt(
            rg=("Seed (rgthree)", {"seed": 54321}),
            gs=("DPEGlobalSeed", {"seed": ["rg", 0]}),
            p1=("SeededTextPool", {"pool_text": "a\nb", "bypass_chance": False}),
        )
        apply_global_seed_onprompt(data)
        self.assertEqual(data["prompt"]["p1"]["inputs"]["dpe_seed"], 54321)

    def test_prompt_still_special_seed_does_not_raise_picker_execute_fails(self):
        data = _prompt(
            gs=("DPEGlobalSeed", {"seed": -1}),
            p1=("UniqueLinePicker", {"input": "a", "bypass_chance": False}),
        )
        apply_global_seed_onprompt(data)
        injected = data["prompt"]["p1"]["inputs"]["dpe_seed"]
        self.assertIsInstance(injected, str)
        with self.assertRaises(GlobalSeedError):
            _picker_execute(injected)

    def test_linked_special_seed_picker_execute_fails(self):
        data = _prompt(
            rg=("Seed (rgthree)", {"seed": -1}),
            gs=("DPEGlobalSeed", {"seed": ["rg", 0]}),
            p1=("UniqueLinePicker", {"input": "a", "bypass_chance": False}),
        )
        apply_global_seed_onprompt(data)
        with self.assertRaises(GlobalSeedError):
            _picker_execute(data["prompt"]["p1"]["inputs"]["dpe_seed"])

    def test_inspire_with_picker_picker_execute_fails(self):
        data = _prompt(
            inspire=("GlobalSeed //Inspire", {"seed": 1}),
            p1=("UniqueLinePicker", {"input": "a", "bypass_chance": False}),
        )
        apply_global_seed_onprompt(data)
        with self.assertRaises(GlobalSeedError):
            _picker_execute(data["prompt"]["p1"]["inputs"]["dpe_seed"])

    def test_inspire_with_dpe_global_marks_pickers(self):
        data = _prompt(
            inspire=("GlobalSeed //Inspire", {"seed": 1}),
            gs=("DPEGlobalSeed", {"seed": 2}),
            p1=("UniqueLinePicker", {"input": "a", "bypass_chance": False}),
        )
        apply_global_seed_onprompt(data)
        self.assertIsInstance(data["prompt"]["p1"]["inputs"]["dpe_seed"], str)

    def test_missing_controller_picker_execute_fails(self):
        data = _prompt(
            p1=("UniqueLinePicker", {"input": "a", "bypass_chance": False}),
        )
        apply_global_seed_onprompt(data)
        with self.assertRaises(GlobalSeedError):
            _picker_execute(data["prompt"]["p1"]["inputs"]["dpe_seed"])

    def test_duplicate_controller_picker_execute_fails(self):
        data = _prompt(
            g1=("DPEGlobalSeed", {"seed": 1}),
            g2=("DPEGlobalSeed", {"seed": 2}),
            p1=("UniqueLinePicker", {"input": "a", "bypass_chance": False}),
        )
        apply_global_seed_onprompt(data)
        with self.assertRaises(GlobalSeedError):
            _picker_execute(data["prompt"]["p1"]["inputs"]["dpe_seed"])

    def test_ksampler_seed_unchanged(self):
        data = _prompt(
            gs=("DPEGlobalSeed", {"seed": 888}),
            ks=("KSampler", {"seed": 42, "steps": 20}),
            p1=("UniqueLinePicker", {"input": "a", "bypass_chance": False}),
        )
        apply_global_seed_onprompt(data)
        self.assertEqual(data["prompt"]["ks"]["inputs"]["seed"], 42)

    def test_global_seed_only_no_pickers_ok(self):
        data = _prompt(gs=("DPEGlobalSeed", {"seed": 100}))
        result = apply_global_seed_onprompt(data)
        self.assertIs(result, data)

    def test_no_pickers_no_controller_ok(self):
        data = _prompt(other=("SomeNode", {"x": 1}))
        result = apply_global_seed_onprompt(data)
        self.assertIs(result, data)


class TestPickerExecuteMissingSeed(unittest.TestCase):
    def test_unique_line_picker_missing_dpe_seed_raises(self):
        with self.assertRaises(GlobalSeedError):
            UniqueLinePicker().pick_line("a\nb", unique_id="1")

    def test_routing_switch_missing_dpe_seed_raises(self):
        with self.assertRaises(GlobalSeedError):
            RoutingSwitch().route(unique_id="1", input_0="a")

    def test_seeded_text_pool_missing_dpe_seed_raises(self):
        with self.assertRaises(GlobalSeedError):
            SeededTextPool().select_from_pool("a\nb", unique_id="1")

    def test_branch_switcher_missing_dpe_seed_raises(self):
        with self.assertRaises(GlobalSeedError):
            BranchRandomSwitcher().select_branch(unique_id="1", branch_0="a")

    def test_wildcard_missing_dpe_seed_raises(self):
        with self.assertRaises(GlobalSeedError):
            UniqueWildcardProcessor().doit("plain", unique_id="1")


class TestRegisterHandler(unittest.TestCase):
    def test_none_instance_raises(self):
        class FakePromptServer:
            instance = None

        fake_module = MagicMock()
        fake_module.PromptServer = FakePromptServer
        with patch.dict("sys.modules", {"server": fake_module}):
            with self.assertRaises(RuntimeError):
                register_global_seed_handler()


class TestDPEGlobalSeedNode(unittest.TestCase):
    def setUp(self):
        self.node = DPEGlobalSeed()

    def test_passes_seed_through(self):
        self.assertEqual(self.node.pass_seed(12345), (12345,))

    def test_output_node_flag(self):
        self.assertTrue(DPEGlobalSeed.OUTPUT_NODE)

    def test_seed_input_disables_control_after_generate(self):
        seed_spec = DPEGlobalSeed.INPUT_TYPES()["required"]["seed"]
        self.assertFalse(seed_spec[1].get("control_after_generate"))


class TestPickerSchemaNoSeedIO(unittest.TestCase):
    PICKERS = (
        (SeededTextPool, "select_from_pool"),
        (UniqueLinePicker, "pick_line"),
        (RoutingSwitch, "route"),
        (BranchRandomSwitcher, "select_branch"),
        (UniqueWildcardProcessor, "doit"),
    )

    def test_picker_classes_registered(self):
        self.assertEqual(len(PICKER_NODE_CLASSES), 5)

    def test_no_seed_in_required_inputs(self):
        for cls, _fn in self.PICKERS:
            with self.subTest(cls=cls.__name__):
                required = cls.INPUT_TYPES().get("required", {})
                self.assertNotIn("seed", required)

    def test_no_seed_in_return_names(self):
        for cls, _fn in self.PICKERS:
            with self.subTest(cls=cls.__name__):
                names = getattr(cls, "RETURN_NAMES", ())
                self.assertNotIn("seed", names)

    def test_dpe_seed_in_hidden(self):
        for cls, _fn in self.PICKERS:
            with self.subTest(cls=cls.__name__):
                hidden = cls.INPUT_TYPES().get("hidden", {})
                self.assertIn("dpe_seed", hidden)
                self.assertNotIn("default", hidden["dpe_seed"][1])


if __name__ == "__main__":
    unittest.main()
