from .prompt_engine_nodes import (
    SeededTextPool,
    TextPoolRouter,
    SeededInputPick,
    OneTwoPersonToggle,
    TagJoin,
)

NODE_CLASS_MAPPINGS = {
    "SeededTextPool": SeededTextPool,
    "TextPoolRouter": TextPoolRouter,
    "SeededInputPick": SeededInputPick,
    "OneTwoPersonToggle": OneTwoPersonToggle,
    "TagJoin": TagJoin,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SeededTextPool": "Seeded Text Pool",
    "TextPoolRouter": "Text Pool Router",
    "SeededInputPick": "Seeded Input Pick",
    "OneTwoPersonToggle": "One/Two Person Toggle",
    "TagJoin": "Tag Join",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]

# Makes web/extensions/dynamic_prompt_engine.js available to ComfyUI.
WEB_DIRECTORY = "./web"
