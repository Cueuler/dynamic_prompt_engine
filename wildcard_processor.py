"""Impact-style wildcard expansion as a Dynamic Prompt Engine node."""

from .prompt_engine_nodes import (
    SEED_INPUT,
    derive_stream_seed,
    process_impact_wildcards,
    stream_key_from_unique_id,
)


class UniqueWildcardProcessor:
    """Expand {a|b} / __wildcard__ in populated_text using Impact Pack."""

    DESCRIPTION = (
        "Unique Wildcard Processor: expands Impact Pack wildcard syntax in "
        "populated_text and outputs the processed prompt. Type in the "
        "multiline widget or convert/wire another STRING into it. Always "
        "expands at execute (populate behavior); the input is not overwritten.\n"
        "\n"
        "Unlike Unique Line Picker, this node does expand {a|b} / __wildcard__. "
        "Syntax: {a|b}, weighted {a::2|b}, __wildcard__, quantifiers. Requires "
        "ComfyUI-Impact-Pack for { and __ syntax (raises if missing). Plain "
        "text is returned unchanged.\n"
        "\n"
        "Seed is mixed with this node's id before Impact's process(), so two "
        "copies of this node with the same seed can still expand differently. "
        "Same seed + same node stays deterministic."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "populated_text": (
                    "STRING",
                    {
                        "multiline": True,
                        "dynamicPrompts": False,
                        "tooltip": (
                            "Prompt using wildcard syntax. Type here or wire a "
                            "multiline STRING. The processed output is expanded; "
                            "this field is not overwritten."
                        ),
                    },
                ),
                "seed": SEED_INPUT,
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("processed text",)
    FUNCTION = "doit"
    CATEGORY = "Dynamic Prompt Engine"

    def doit(self, populated_text, seed=0, unique_id=None):
        stream_seed = derive_stream_seed(
            int(seed), stream_key_from_unique_id(unique_id)
        )
        return (process_impact_wildcards(populated_text, stream_seed),)
