"""Routing Switch: seeded weighted pick among dynamic STRING inputs."""

from ..core.seeding import PICKER_HIDDEN, master_seed_from_dpe
from ..core.dynamic_inputs import RoutingSwitchOptionalInputs, numbered_input_indices
from ..core.rng import derive_stream_seed, stream_key_from_unique_id
from ..core.text import chance_weight


class RoutingSwitch:
    """Seeded weighted pick among dynamic STRING inputs with per-slot chance combos."""

    DESCRIPTION = (
        "Routing Switch: picks one wired input_N string. Unconnected sockets and chance Off "
        "are excluded from the lottery. A connected empty or whitespace string "
        "can win (output is stripped empty). Off cannot win and does not add "
        "weight. Remaining slots share the roll: Default is 1×, 1.5x is 50% "
        "more than Default, 2x is twice Default. Same seed+node id is "
        "deterministic.\n"
        "\n"
        "Outputs the winning text (stripped, no extra commas). Wire Unique "
        "Wildcard Processor on the text output; master seed comes from "
        "DPE Global Seed.\n"
        "\n"
        "Examples: three Default clothes groups → one of them, equal chance. "
        "input_0 Default and input_1 2x → input_1 wins about twice as often. "
        "Only Off or unconnected left → empty text."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": RoutingSwitchOptionalInputs(
                {"input_0": ("STRING", {"default": "", "forceInput": True})},
            ),
            "hidden": PICKER_HIDDEN,
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "route"
    CATEGORY = "Dynamic Prompt Engine"

    def route(self, dpe_seed=None, unique_id=None, **kwargs):
        node_name = self.__class__.__name__
        master_seed = master_seed_from_dpe(dpe_seed, node_name)

        eligible = []
        for index in numbered_input_indices(kwargs, "input_"):
            raw = kwargs.get(f"input_{index}")
            if raw is None:
                continue
            weight = chance_weight(kwargs.get(f"chance_{index}"))
            if weight is None:
                continue
            text = str(raw).strip()
            eligible.append((weight, text))

        if not eligible:
            return ("",)

        derived_seed = derive_stream_seed(
            master_seed, stream_key_from_unique_id(unique_id)
        )
        remaining = derived_seed % sum(weight for weight, _ in eligible)
        for weight, text in eligible:
            remaining -= weight
            if remaining < 0:
                return (text,)
        return (eligible[-1][1],)
