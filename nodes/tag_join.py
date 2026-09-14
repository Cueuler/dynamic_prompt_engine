"""Tag Join: joins wired tag_N strings in numeric order with comma hygiene."""

from ..core.dynamic_inputs import FlexibleOptionalInputType
from ..core.rng import resolve_unique_id
from ..core.text import nonempty_text


class TagJoin:
    """Joins connected tag strings in input order and displays the resulting text."""

    DESCRIPTION = (
        "Tag Join: joins wired tag_N strings in numeric index order (tag_0, tag_1, …; "
        "tag_10 after tag_2). Dynamic sockets: connected tags + one spare. No "
        "seed. The multiline text widget is a preview only (filled after run), "
        "not a tag input. Output: prompt.\n"
        "\n"
        "Each tag: skip if empty/whitespace; strip leading/trailing commas and "
        "spaces; skip again if nothing remains. Join survivors with ', ' "
        "(no trailing comma after the last tag). All empty → ''.\n"
        "\n"
        "Examples: tag_0='red', tag_1='blue' → 'red, blue'. tag_0='', "
        "tag_1='blue' → 'blue'. tag_0='red,', tag_1=', blue' → 'red, blue'. "
        "tag_0 and tag_2 wired, tag_1 empty/unwired → join 0 then 2.\n"
        "\n"
        "Holes in tag indices are allowed; order is by number, not socket "
        "position."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": False,
                        "placeholder": "Joined prompt preview (empty until run)…",
                    },
                ),
            },
            "optional": FlexibleOptionalInputType(
                "STRING",
                {
                    "tag_0": ("STRING", {"default": "", "forceInput": True}),
                },
            ),
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "join_tags"
    CATEGORY = "Dynamic Prompt Engine"
    OUTPUT_NODE = True

    def join_tags(self, text="", unique_id=None, extra_pnginfo=None, **kwargs):
        tag_keys = sorted(
            (
                key
                for key in kwargs
                if key.startswith("tag_") and key[len("tag_"):].isdigit()
            ),
            key=lambda key: int(key[len("tag_"):]),
        )
        clean_tags = []

        for k in tag_keys:
            value = nonempty_text(kwargs.get(k))
            if value is None:
                continue
            value = value.strip(", ")
            if value:
                clean_tags.append(value)

        final_prompt = ", ".join(clean_tags)

        node_uid = resolve_unique_id(unique_id)
        if node_uid is not None and extra_pnginfo is not None:
            if isinstance(extra_pnginfo, list) and extra_pnginfo:
                workflow = extra_pnginfo[0].get("workflow")
            elif isinstance(extra_pnginfo, dict):
                workflow = extra_pnginfo.get("workflow")
            else:
                workflow = None
            if workflow:
                node = next(
                    (
                        item
                        for item in workflow["nodes"]
                        if str(item["id"]) == node_uid
                    ),
                    None,
                )
                if node:
                    node["widgets_values"] = [final_prompt]

        return {
            "ui": {"text": [final_prompt]},
            "result": (final_prompt,),
        }
