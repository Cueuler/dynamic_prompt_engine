from .prompt_engine_nodes import (
    SeededTextPool,
    BranchRandomSwitcher,
    BranchSelector,
    TagJoin,
)

try:
    from .resolution_node import ResolutionSwitch
except ImportError:
    ResolutionSwitch = None

NODE_CLASS_MAPPINGS = {
    "SeededTextPool": SeededTextPool,
    "BranchRandomSwitcher": BranchRandomSwitcher,
    "BranchSelector": BranchSelector,
    "TagJoin": TagJoin,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeededTextPool": "Seeded Text Pool",
    "BranchRandomSwitcher": "Branch Random Switcher",
    "BranchSelector": "Branch Selector",
    "TagJoin": "Tag Join",
}

if ResolutionSwitch is not None:
    NODE_CLASS_MAPPINGS["ResolutionSwitch"] = ResolutionSwitch
    NODE_DISPLAY_NAME_MAPPINGS["ResolutionSwitch"] = "Resolution Switch"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

# Makes web/dynamic_prompt_engine.js available to ComfyUI.
WEB_DIRECTORY = "./web"
