from .prompt_engine_nodes import (
    SeededTextPool,
    FirstOrMerge,
    FirstOrSecond,
    BranchRandomSwitcher,
    TagJoin,
)
from .resolution_node import ResolutionSwitch

NODE_CLASS_MAPPINGS = {
    "SeededTextPool": SeededTextPool,
    "FirstOrMerge": FirstOrMerge,
    "FirstOrSecond": FirstOrSecond,
    "BranchRandomSwitcher": BranchRandomSwitcher,
    "TagJoin": TagJoin,
    "ResolutionSwitch": ResolutionSwitch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeededTextPool": "Seeded Text Pool",
    "FirstOrMerge": "First OR Merge",
    "FirstOrSecond": "First OR Second",
    "BranchRandomSwitcher": "Branch Random Switcher",
    "TagJoin": "Tag Join",
    "ResolutionSwitch": "Resolution Switch",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

# Makes web/extensions/dynamic_prompt_engine.js available to ComfyUI.
WEB_DIRECTORY = "./web"
