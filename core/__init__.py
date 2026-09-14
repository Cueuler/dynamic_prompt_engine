"""Pure prompt-engine logic: no ComfyUI imports, fully unit-testable."""

from .rng import (
    derive_stream_seed,
    pick_unique_line,
    resolve_unique_id,
    stream_key_from_unique_id,
)
from .text import (
    CHANCE_WEIGHTS,
    chance_weight,
    nonempty_text,
    normalize_chance_value,
)
from .dynamic_inputs import (
    FlexibleOptionalInputType,
    RoutingSwitchOptionalInputs,
    numbered_input_indices,
)
from .wildcards import process_impact_wildcards

__all__ = [
    "CHANCE_WEIGHTS",
    "FlexibleOptionalInputType",
    "RoutingSwitchOptionalInputs",
    "chance_weight",
    "derive_stream_seed",
    "nonempty_text",
    "normalize_chance_value",
    "numbered_input_indices",
    "pick_unique_line",
    "process_impact_wildcards",
    "resolve_unique_id",
    "stream_key_from_unique_id",
]
