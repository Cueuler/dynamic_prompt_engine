"""Seed-resolution contract shared by pickers and the DPE Global Seed controller."""

from __future__ import annotations

PICKER_NODE_CLASSES = frozenset(
    {
        "SeededTextPool",
        "UniqueLinePicker",
        "RoutingSwitch",
        "UniqueWildcardProcessor",
    }
)

SPECIAL_SEEDS = frozenset({-1, -2, -3})

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
