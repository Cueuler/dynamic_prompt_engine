from .prompt_engine_nodes import (
    SeededTextPool,
    BranchRandomSwitcher,
    BranchSelector,
    TagJoin,
)
from .resolution_node import ResolutionSwitch

NODE_CLASS_MAPPINGS = {
    "SeededTextPool": SeededTextPool,
    "BranchRandomSwitcher": BranchRandomSwitcher,
    "BranchSelector": BranchSelector,
    "TagJoin": TagJoin,
    "ResolutionSwitch": ResolutionSwitch,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeededTextPool": "Seeded Text Pool",
    "BranchRandomSwitcher": "Branch Random Switcher",
    "BranchSelector": "Branch Selector",
    "TagJoin": "Tag Join",
    "ResolutionSwitch": "Resolution Switch",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

# Makes web/extensions/dynamic_prompt_engine.js available to ComfyUI.
WEB_DIRECTORY = "./web"
