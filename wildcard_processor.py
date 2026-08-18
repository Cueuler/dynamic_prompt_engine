"""Impact-style wildcard expansion as a Dynamic Prompt Engine node."""

from .prompt_engine_nodes import SEED_INPUT, process_impact_wildcards


class WildcardProcessor:
    """Expand {a|b} / __wildcard__ in populated_text using Impact Pack."""

    DESCRIPTION = (
        "Expands Impact Pack wildcard syntax in populated_text and outputs the "
        "processed prompt. Type in the multiline widget or convert/wire another "
        "STRING into it. Always expands at execute (populate behavior); the "
        "input is not overwritten.\n"
        "\n"
        "Syntax: {a|b}, weighted {a::2|b}, __wildcard__, quantifiers. Requires "
        "ComfyUI-Impact-Pack for { and __ syntax (raises if missing). Plain "
        "text is returned unchanged. Seed is passed to Impact's process() as-is."
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
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("processed text",)
    FUNCTION = "doit"
    CATEGORY = "Dynamic Prompt Engine"

    def doit(self, populated_text, seed=0):
        return (process_impact_wildcards(populated_text, seed),)
