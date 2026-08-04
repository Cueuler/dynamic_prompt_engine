from .prompt_engine_nodes import (
    SeededTextPool,
    BranchSelect2,
    BranchToggle,
    TagJoin,
)

NODE_CLASS_MAPPINGS = {
    "SeededTextPool": SeededTextPool,
    "BranchSelect2": BranchSelect2,
    "BranchToggle": BranchToggle,
    "TagJoin": TagJoin,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeededTextPool": "Seeded Text Pool",
    "BranchSelect2": "Branch Select 2",
    "BranchToggle": "Branch Toggle",
    "TagJoin": "Tag Join",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

# Makes web/extensions/dynamic_prompt_engine.js available to ComfyUI.
WEB_DIRECTORY = "./web"
