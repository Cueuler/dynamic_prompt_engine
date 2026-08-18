from .prompt_engine_nodes import (
    SeededTextPool,
    UniqueLinePicker,
    RoutingSwitch,
    BranchRandomSwitcher,
    BranchSelector,
    TagJoin,
)
from .clip_token_report import CLIPTokenReport
from .wildcard_processor import UniqueWildcardProcessor

try:
    from .resolution_node import ResolutionSwitch
except ImportError:
    ResolutionSwitch = None

NODE_CLASS_MAPPINGS = {
    "SeededTextPool": SeededTextPool,
    "UniqueLinePicker": UniqueLinePicker,
    "RoutingSwitch": RoutingSwitch,
    "BranchRandomSwitcher": BranchRandomSwitcher,
    "BranchSelector": BranchSelector,
    "TagJoin": TagJoin,
    "CLIPTokenReport": CLIPTokenReport,
    "UniqueWildcardProcessor": UniqueWildcardProcessor,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeededTextPool": "Seeded Text Pool",
    "UniqueLinePicker": "Unique Line Picker",
    "RoutingSwitch": "Routing Switch",
    "BranchRandomSwitcher": "Branch Random Switcher",
    "BranchSelector": "Branch Selector",
    "TagJoin": "Tag Join",
    "CLIPTokenReport": "CLIP Token Report",
    "UniqueWildcardProcessor": "Unique Wildcard Processor",
}

if ResolutionSwitch is not None:
    NODE_CLASS_MAPPINGS["ResolutionSwitch"] = ResolutionSwitch
    NODE_DISPLAY_NAME_MAPPINGS["ResolutionSwitch"] = "Resolution Switch"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

# Makes web/dynamic_prompt_engine.js available to ComfyUI.
WEB_DIRECTORY = "./web"
