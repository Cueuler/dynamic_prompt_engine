"""DPE Global Seed node and onprompt seed injection for picker nodes."""

from ..core.seeding import (
    PICKER_NODE_CLASSES,
    GlobalSeedError,
    resolve_seed_from_prompt_value,
)

INSPIRE_GLOBAL_SEED_CLASS = "GlobalSeed //Inspire"
DPE_GLOBAL_SEED_CLASS = "DPEGlobalSeed"

GLOBAL_SEED_INPUT = (
    "INT",
    {
        "default": 0,
        "min": 0,
        "max": 0xFFFFFFFFFFFFFFFF,
        "step": 1,
        "display": "number",
        "control_after_generate": False,
    },
)


def _set_picker_seed_errors(prompt, message):
    for node in prompt.values():
        if isinstance(node, dict) and node.get("class_type") in PICKER_NODE_CLASSES:
            node.setdefault("inputs", {})["dpe_seed"] = message


def apply_global_seed_onprompt(json_data):
    """Resolve DPE Global Seed and inject master seed into every picker node.

    ComfyUI swallows exceptions from onprompt handlers, so this function never
    raises. Failures write an error string into each picker ``dpe_seed``; the
    picker raises that message at execute.
    """
    prompt = json_data.get("prompt")
    if not isinstance(prompt, dict):
        return json_data

    has_inspire = any(
        isinstance(node, dict) and node.get("class_type") == INSPIRE_GLOBAL_SEED_CLASS
        for node in prompt.values()
    )
    has_dpe_picker = any(
        isinstance(node, dict) and node.get("class_type") in PICKER_NODE_CLASSES
        for node in prompt.values()
    )
    has_dpe_global = any(
        isinstance(node, dict) and node.get("class_type") == DPE_GLOBAL_SEED_CLASS
        for node in prompt.values()
    )

    if has_inspire and (has_dpe_picker or has_dpe_global):
        _set_picker_seed_errors(
            prompt,
            "DPE Global Seed cannot be used with GlobalSeed //Inspire in the same "
            "prompt. Remove Inspire Global Seed or use only one seed controller.",
        )
        return json_data

    global_seed_nodes = [
        (node_id, node)
        for node_id, node in prompt.items()
        if isinstance(node, dict) and node.get("class_type") == DPE_GLOBAL_SEED_CLASS
    ]

    if has_dpe_picker:
        if len(global_seed_nodes) == 0:
            _set_picker_seed_errors(
                prompt,
                "Dynamic Prompt Engine picker nodes require exactly one "
                "DPE Global Seed controller.",
            )
            return json_data
        if len(global_seed_nodes) > 1:
            _set_picker_seed_errors(
                prompt,
                "Only one DPE Global Seed controller is allowed per prompt.",
            )
            return json_data

    if not global_seed_nodes:
        return json_data

    if len(global_seed_nodes) > 1:
        _set_picker_seed_errors(
            prompt,
            "Only one DPE Global Seed controller is allowed per prompt.",
        )
        return json_data

    _node_id, global_seed_node = global_seed_nodes[0]
    seed_input = global_seed_node.get("inputs", {}).get("seed")
    try:
        master_seed = resolve_seed_from_prompt_value(seed_input, prompt)
    except GlobalSeedError as exc:
        _set_picker_seed_errors(prompt, str(exc))
        return json_data

    for node in prompt.values():
        if isinstance(node, dict) and node.get("class_type") in PICKER_NODE_CLASSES:
            node.setdefault("inputs", {})["dpe_seed"] = master_seed

    return json_data


class DPEGlobalSeed:
    """Thin pass-through for the master seed (wire from rgthree Seed)."""

    DESCRIPTION = (
        "DPE Global Seed: required controller for seeded Dynamic Prompt Engine "
        "nodes. Wire rgthree Seed (or any INT) into the seed input. At queue "
        "time the resolved integer is injected into every picker (no seed wires "
        "on pickers). Optionally wire seed output to KSampler.\n"
        "\n"
        "Use rgthree Seed for Randomize / increment / last-queued on the "
        "frontend. DPE reads prompt.inputs after rgthree hijack, not the visible "
        "widget when it still shows -1."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": GLOBAL_SEED_INPUT,
            },
        }

    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("seed",)
    FUNCTION = "pass_seed"
    CATEGORY = "Dynamic Prompt Engine"
    OUTPUT_NODE = True

    def pass_seed(self, seed):
        return (int(seed),)


def register_global_seed_handler():
    """Register onprompt handler. Raises if ComfyUI's PromptServer exists but is unset."""
    try:
        from server import PromptServer
    except ImportError:
        return

    instance = PromptServer.instance
    if instance is None:
        raise RuntimeError(
            "DPE Global Seed: PromptServer.instance is None; "
            "cannot register the onprompt handler."
        )

    handlers = getattr(instance, "on_prompt_handlers", None)
    if handlers is not None and apply_global_seed_onprompt in handlers:
        return

    instance.add_on_prompt_handler(apply_global_seed_onprompt)
