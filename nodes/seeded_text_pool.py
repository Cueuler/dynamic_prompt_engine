"""Seeded Text Pool: seeded multiline pool pick + wildcard expansion node."""

from ..core.seeding import PICKER_HIDDEN, master_seed_from_dpe
from ..core.rng import derive_stream_seed, pick_unique_line, stream_key_from_unique_id
from ..core.wildcards import process_impact_wildcards


class SeededTextPool:
    """Selects a deterministic text candidate from a multiline library based on seed + node id."""

    DESCRIPTION = (
        "Seeded Text Pool: picks one line from pool_text using the same PCG64 "
        "integers() as Unique Line Picker, then expands Impact Pack {a|b} / "
        "__wildcard__ on the chosen line using Unique Wildcard Processor's "
        "mixed seed. Master seed comes from DPE Global Seed.\n"
        "\n"
        "Unlike Unique Line Picker: this node has a multiline pool_text widget, "
        "and {a|b} / __wildcard__ run on the chosen line.\n"
        "\n"
        "Candidates: split on newlines, strip each line, drop blank/whitespace "
        "lines. Only remaining lines are in the pool.\n"
        "\n"
        "Bypass chance Off: never gates. 50%: "
        "default_rng(hash(seed:node:{id}:gate)).integers(0, 2) == 0 returns "
        "empty text (this check runs even if the pool is empty; Impact expand "
        "is skipped when gated).\n"
        "\n"
        "Examples: pool 'alice\\nbob\\ncharlie' → one of those three, stable for "
        "the same seed+node. 'alice\\n\\n  \\nbob' → only alice and bob. Chosen "
        "line '[empty]' → empty string. Empty pool → empty string.\n"
        "\n"
        "Edge cases: the literal line [empty] is a candidate that emits blank "
        "(not skipped). Impact Pack {a|b} / __wildcard__ runs only on the chosen "
        "line and requires ComfyUI-Impact-Pack (raises if missing)."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pool_text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": False,
                        "placeholder": "Enter candidates, one per line...",
                    },
                ),
                "bypass_chance": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "label_on": "50%",
                        "label_off": "Off",
                    },
                ),
            },
            "hidden": PICKER_HIDDEN,
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "select_from_pool"
    CATEGORY = "Dynamic Prompt Engine"

    def select_from_pool(
        self, pool_text, bypass_chance=False, dpe_seed=None, unique_id=None
    ):
        master_seed = master_seed_from_dpe(dpe_seed, self.__class__.__name__)
        text, _master_seed, gated = pick_unique_line(
            pool_text,
            bypass_chance=bypass_chance,
            dpe_seed=master_seed,
            unique_id=unique_id,
        )
        if gated:
            return ("",)
        stream_seed = derive_stream_seed(
            master_seed, stream_key_from_unique_id(unique_id)
        )
        return (process_impact_wildcards(text, stream_seed),)
