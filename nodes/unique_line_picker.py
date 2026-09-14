"""Unique Line Picker: seeded pick from a wired STRING pool."""

from ..core.seeding import PICKER_HIDDEN, master_seed_from_dpe
from ..core.rng import pick_unique_line


class UniqueLinePicker:
    """Picks one line from a STRING pool using NumPy PCG64 mixed with node id."""

    DESCRIPTION = (
        "Unique Line Picker: picks one line from a wired STRING socket "
        "(input). Seed is mixed with "
        "this node's id, then np.random.default_rng(stream_seed).integers(0, n) "
        "chooses the line (same PCG64 generator Impact uses). Two copies of "
        "this node with the same master seed can still pick different lines. "
        "Master seed comes from DPE Global Seed.\n"
        "\n"
        "Unlike Seeded Text Pool: there is no multiline widget, and "
        "{a|b} / __wildcard__ are not expanded.\n"
        "\n"
        "Candidates: split on newlines, strip each line, drop blank/whitespace "
        "lines. Only remaining lines are in the pool.\n"
        "\n"
        "Bypass chance Off: never gates. 50%: "
        "default_rng(hash(seed:node:{id}:gate)).integers(0, 2) == 0 returns "
        "empty text (this check runs even if the pool is empty).\n"
        "\n"
        "Examples: pool 'alice\\nbob\\ncharlie' → one of those three, stable "
        "for the same seed+node. Two copies, same seed, different node ids → "
        "independent winners. 'alice\\n\\n  \\nbob' → only alice and bob. "
        "Chosen line '[empty]' → empty string. Empty pool → empty string.\n"
        "\n"
        "Edge cases: the literal line [empty] is a candidate that emits blank "
        "(not skipped)."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input": (
                    "STRING",
                    {
                        "default": "",
                        "forceInput": True,
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
    FUNCTION = "pick_line"
    CATEGORY = "Dynamic Prompt Engine"

    def pick_line(self, input, bypass_chance=False, dpe_seed=None, unique_id=None):
        master_seed = master_seed_from_dpe(dpe_seed, self.__class__.__name__)
        text, _master_seed, _gated = pick_unique_line(
            input,
            bypass_chance=bypass_chance,
            dpe_seed=master_seed,
            unique_id=unique_id,
        )
        return (text,)
