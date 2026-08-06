from .prompt_engine_nodes import (
    SeededTextPool,
    FirstOrMerge,
    FirstOrSecond,
    BranchToggle,
    TagJoin,
)

NODE_CLASS_MAPPINGS = {
    "SeededTextPool": SeededTextPool,
    "FirstOrMerge": FirstOrMerge,
    "FirstOrSecond": FirstOrSecond,
    "BranchToggle": BranchToggle,
    "TagJoin": TagJoin,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeededTextPool": "Seeded Text Pool",
    "FirstOrMerge": "First OR Merge",
    "FirstOrSecond": "First OR Second",
    "BranchToggle": "Branch Toggle",
    "TagJoin": "Tag Join",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

# Makes web/extensions/dynamic_prompt_engine.js available to ComfyUI.
WEB_DIRECTORY = "./web"
