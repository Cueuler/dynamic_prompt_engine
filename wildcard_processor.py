"""Impact-style wildcard expansion as a Dynamic Prompt Engine node."""

from .global_seed import PICKER_HIDDEN, master_seed_from_dpe
from .prompt_engine_nodes import (
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
            },
            "hidden": PICKER_HIDDEN,
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("processed text",)
    FUNCTION = "doit"
    CATEGORY = "Dynamic Prompt Engine"

    def doit(self, populated_text, dpe_seed=None, unique_id=None):
        master_seed = master_seed_from_dpe(dpe_seed, self.__class__.__name__)
        stream_seed = derive_stream_seed(
            master_seed, stream_key_from_unique_id(unique_id)
        )
        return (process_impact_wildcards(populated_text, stream_seed),)
