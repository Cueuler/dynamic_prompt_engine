from .nodes import (
    SeededTextPool,
    UniqueLinePicker,
    RoutingSwitch,
    TagJoin,
    CLIPTokenReport,
    UniqueWildcardProcessor,
    DPEGlobalSeed,
)

try:
    from .nodes.resolution import ResolutionSwitch
except ImportError:
    ResolutionSwitch = None

NODE_CLASS_MAPPINGS = {
    "SeededTextPool": SeededTextPool,
    "UniqueLinePicker": UniqueLinePicker,
    "RoutingSwitch": RoutingSwitch,
    "TagJoin": TagJoin,
    "CLIPTokenReport": CLIPTokenReport,
    "UniqueWildcardProcessor": UniqueWildcardProcessor,
    "DPEGlobalSeed": DPEGlobalSeed,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeededTextPool": "Seeded Text Pool",
    "UniqueLinePicker": "Unique Line Picker",
    "RoutingSwitch": "Routing Switch",
    "TagJoin": "Tag Join",
    "CLIPTokenReport": "CLIP Token Report",
    "UniqueWildcardProcessor": "Unique Wildcard Processor",
    "DPEGlobalSeed": "DPE Global Seed",
}

if ResolutionSwitch is not None:
    NODE_CLASS_MAPPINGS["ResolutionSwitch"] = ResolutionSwitch
    NODE_DISPLAY_NAME_MAPPINGS["ResolutionSwitch"] = "Resolution Switch"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

from .nodes.global_seed import register_global_seed_handler

register_global_seed_handler()

# Makes web/dynamic_prompt_engine.js available to ComfyUI.
WEB_DIRECTORY = "./web"
