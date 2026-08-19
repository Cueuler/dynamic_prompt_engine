"""DPE Global Seed controller and onprompt seed injection for picker nodes."""

from __future__ import annotations

INSPIRE_GLOBAL_SEED_CLASS = "GlobalSeed //Inspire"
DPE_GLOBAL_SEED_CLASS = "DPEGlobalSeed"

PICKER_NODE_CLASSES = frozenset(
    {
        "SeededTextPool",
        "UniqueLinePicker",
        "RoutingSwitch",
        "BranchRandomSwitcher",
        "UniqueWildcardProcessor",
    }
)

SPECIAL_SEEDS = frozenset({-1, -2, -3})

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

# No default: missing inject must not become seed 0.
PICKER_HIDDEN = {
    "unique_id": "UNIQUE_ID",
    "dpe_seed": ("INT", {"min": 0, "max": 0xFFFFFFFFFFFFFFFF}),
}


class GlobalSeedError(ValueError):
    """Raised when global seed resolution fails or a picker has no master seed."""


def master_seed_from_dpe(dpe_seed, node_name):
    """Return injected master seed, or raise if onprompt did not inject a valid INT."""
    if isinstance(dpe_seed, str):
        raise GlobalSeedError(dpe_seed)
    if dpe_seed is None:
        raise GlobalSeedError(
            f"{node_name}: missing DPE Global Seed. "
            "Add exactly one DPE Global Seed controller."
        )
    if isinstance(dpe_seed, bool):
        raise GlobalSeedError(
            f"{node_name}: invalid injected master seed {dpe_seed!r}."
        )
    try:
        seed = int(dpe_seed)
    except (TypeError, ValueError) as exc:
        raise GlobalSeedError(
            f"{node_name}: invalid injected master seed {dpe_seed!r}. "
            "Wire rgthree Seed into DPE Global Seed."
        ) from exc
    if seed in SPECIAL_SEEDS:
        raise GlobalSeedError(
            f"{node_name}: resolved seed is still a special placeholder ({seed}). "
            "Wire rgthree Seed into DPE Global Seed, or set a concrete integer "
            "before queueing."
        )
    if seed < 0:
        raise GlobalSeedError(
            f"{node_name}: resolved seed must be non-negative, got {seed}."
        )
    return seed


def resolve_seed_from_prompt_value(value, prompt, visited=None):
    """Resolve a concrete INT from prompt.inputs (direct int or one link hop)."""
    if visited is None:
        visited = set()

    if isinstance(value, bool):
        raise GlobalSeedError(
            "DPE Global Seed: seed input must resolve to an integer, "
            f"got boolean {value!r}."
        )

    if isinstance(value, int):
        if value in SPECIAL_SEEDS:
            raise GlobalSeedError(
                "DPE Global Seed: resolved seed is still a special placeholder "
                f"({value}). Wire rgthree Seed into DPE Global Seed, or set a "
                "concrete integer before queueing."
            )
        if value < 0:
            raise GlobalSeedError(
                f"DPE Global Seed: resolved seed must be non-negative, got {value}."
            )
        return value

    if isinstance(value, (list, tuple)) and len(value) == 2:
        src_id, _slot = value
        src_id = str(src_id)
        if src_id in visited:
            raise GlobalSeedError(
                "DPE Global Seed: cyclic seed link cannot be resolved."
            )
        visited.add(src_id)
        src_node = prompt.get(src_id)
        if not src_node or not isinstance(src_node.get("inputs"), dict):
            raise GlobalSeedError(
                "DPE Global Seed: seed link points to a missing node."
            )
        inputs = src_node["inputs"]
        for key in ("seed", "value"):
            if key in inputs:
                return resolve_seed_from_prompt_value(inputs[key], prompt, visited)
        raise GlobalSeedError(
            "DPE Global Seed: linked node has no resolvable seed or value input."
        )

    raise GlobalSeedError(
        "DPE Global Seed: seed input is not a concrete integer or resolvable link."
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
