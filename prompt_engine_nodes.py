import hashlib
import sys
from pathlib import Path


class FlexibleOptionalInputType(dict):
    """Accept dynamically named optional inputs (e.g. TagJoin tag_N sockets)."""

    def __init__(self, input_type, data=None):
        super().__init__(data or {})
        self.input_type = input_type
        self.data = data or {}

    def __getitem__(self, key):
        return self.data.get(key, (self.input_type,))

    def __contains__(self, key):
        return True


def resolve_unique_id(unique_id):
    """Normalize ComfyUI UNIQUE_ID (str/int or single-element list/tuple) to a string."""
    if unique_id is None:
        return None
    if isinstance(unique_id, (list, tuple)):
        if not unique_id:
            return None
        unique_id = unique_id[0]
    return str(unique_id)


def stream_key_from_unique_id(unique_id):
    """Derive a stable per-node stream key from UNIQUE_ID (fallback for unit tests)."""
    uid = resolve_unique_id(unique_id)
    return f"node:{uid}" if uid else "default"


def nonempty_text(value):
    """Return stripped text, or None if absent/empty/whitespace-only."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def validate_text_input(value, input_name, node_name):
    """Validate that a text input is non‑empty; raise ValueError with a clear message."""
    text = nonempty_text(value)
    if text is None:
        raise ValueError(
            f"{node_name}: '{input_name}' is required and must be non‑empty."
        )
    return text


def process_impact_wildcards(text, seed):
    """Process a selected line with Impact Pack's exact wildcard implementation."""
    if "{" not in text and "__" not in text:
        return text

    try:
        from impact import wildcards
    except ImportError:
        impact_modules = (
            Path(__file__).resolve().parents[1]
            / "comfyui-impact-pack"
            / "modules"
        )
        if impact_modules.is_dir():
            sys.path.insert(0, str(impact_modules))
            from impact import wildcards
        else:
            raise RuntimeError(
                "SeededTextPool wildcard syntax requires ComfyUI-Impact-Pack."
            )

    return wildcards.process(text, seed)


def derive_stream_seed(master_seed, stream_key, suffix=""):
    """Deterministic 64-bit seed from master seed + stream key (+ optional suffix)."""
    key_str = f"{master_seed}:{stream_key}"
    if suffix:
        key_str = f"{key_str}:{suffix}"
    return int(hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:16], 16)


def join_prompt_parts(*parts):
    """Join non-empty prompt fragments with TagJoin comma hygiene."""
    clean = []
    for part in parts:
        text = nonempty_text(part)
        if not text:
            continue
        text = text.strip(", ")
        if text:
            clean.append(text)
    joined = ", ".join(clean)
    if joined:
        joined += ", "
    return joined


SEED_INPUT = (
    "INT",
    {
        "default": 0,
        "min": 0,
        "max": 0xFFFFFFFFFFFFFFFF,
        "step": 1,
        "display": "number",
    },
)


class SeededTextPool:
    """Selects a deterministic text candidate from a multiline library based on seed + node id."""

    DESCRIPTION = (
        "Picks one line from pool_text using hash(seed:node:{id}) % n "
        "(independent stream per node). Blank/whitespace-only lines are skipped "
        "and never chosen; only non-empty lines count as candidates. Supports "
        "Impact Pack {a|b} / __wildcard__ on the chosen line; [empty] emits blank. "
        "Bypass chance 50% can emit empty via a separate …:gate hash; Off never "
        "gates. Outputs text and passthrough seed."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "pool_text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": False,
                        "placeholder": "Enter candidates, one per line...",
                    },
                ),
                "bypass_chance": (
                    "BOOLEAN",
                    {
                        "default": False,
                        "label_on": "50%",
                        "label_off": "Off",
                    },
                ),
                "seed": SEED_INPUT,
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("text", "seed")
    FUNCTION = "select_from_pool"
    CATEGORY = "Dynamic Prompt Engine"

    def select_from_pool(
        self, pool_text, seed, bypass_chance=False, unique_id=None
    ):
        master_seed = int(seed)
        stream_key = stream_key_from_unique_id(unique_id)
        lines = [
            line.strip()
            for line in str(pool_text or "").splitlines()
            if line.strip()
        ]

        if bypass_chance:
            gate_seed = derive_stream_seed(master_seed, stream_key, "gate")
            if gate_seed % 2 == 0:
                return ("", master_seed)

        if not lines:
            return ("", master_seed)

        derived_seed = derive_stream_seed(master_seed, stream_key)
        choice_index = derived_seed % len(lines)
        chosen_text = "" if lines[choice_index] == "[empty]" else lines[choice_index]
        chosen_text = process_impact_wildcards(chosen_text, derived_seed)
        return (chosen_text, master_seed)


class FirstOrMerge:
    """Branch 0 → first input only; branch 1 → merge both inputs."""

    DESCRIPTION = (
        "Routes from BranchToggle.branch: 0 → solo only; 1 → join_prompt_parts(solo, duo). "
        "Solo and duo are optional inputs; empty parts are skipped on merge — "
        "e.g. leave solo blank and wire Char2 into duo to omit Char2 in 1girl mode "
        "and include it when branch is 1. No seed."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "branch": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 1,
                        "step": 1,
                        "forceInput": True,
                    },
                ),
            },
            "optional": {
                "solo": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": False,
                    },
                ),
                "duo": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": False,
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "select"
    CATEGORY = "Dynamic Prompt Engine"

    def select(self, branch, solo="", duo=""):
        try:
            choice = int(branch)
        except (TypeError, ValueError):
            raise ValueError(
                f"{self.__class__.__name__}: 'branch' must be 0 or 1, got {branch!r}."
            )
        if choice == 0:
            return (nonempty_text(solo) or "",)
        if choice == 1:
            return (join_prompt_parts(solo, duo),)
        raise ValueError(
            f"{self.__class__.__name__}: 'branch' must be 0 or 1, got {choice}."
        )


class FirstOrSecond:
    """Branch 0 → first input only; branch 1 → second input only."""

    DESCRIPTION = (
        "Routes from BranchToggle.branch: 0 → solo only; 1 → duo only. "
        "Solo and duo are optional inputs; empty selected paths return empty so TagJoin can "
        "skip them — e.g. leave solo blank and wire Char2 into duo to omit Char2 in 1girl "
        "mode. No seed."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "branch": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 1,
                        "step": 1,
                        "forceInput": True,
                    },
                ),
            },
            "optional": {
                "solo": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": False,
                    },
                ),
                "duo": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": False,
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "select"
    CATEGORY = "Dynamic Prompt Engine"

    def select(self, branch, solo="", duo=""):
        try:
            choice = int(branch)
        except (TypeError, ValueError):
            raise ValueError(
                f"{self.__class__.__name__}: 'branch' must be 0 or 1, got {branch!r}."
            )
        if choice == 0:
            return (nonempty_text(solo) or "",)
        if choice == 1:
            return (nonempty_text(duo) or "",)
        raise ValueError(
            f"{self.__class__.__name__}: 'branch' must be 0 or 1, got {choice}."
        )


class BranchToggle:
    """Mode-controlled switch that selects branch_1 or branch_2 text."""

    STREAM_KEY = "one_two_person_toggle"
    MODE_CHOICES = ("Random", "1girl", "2girls")

    DESCRIPTION = (
        "Branch Toggle: picks branch 0 or 1, then outputs exactly one of the two "
        "linked strings. mode: Random → hash(seed:one_two_person_toggle) % 2; "
        "1girl → 0; 2girls → 1. "
        "Branch 0 → branch_1 only; branch 1 → branch_2 only "
        "(does not prepend 1girl/2girls or merge both inputs). "
        "Put the full solo text in branch_1 and full duo text in branch_2 "
        "(e.g. '1girl, alice' / '2girls, alice, bob'). "
        "Both inputs are optional; an absent or empty input produces empty output. "
        "Wire branch into FirstOrMerge / FirstOrSecond.branch for other sections. "
        "Outputs text and branch (0 or 1)."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (list(cls.MODE_CHOICES), {"default": "Random"}),
                "seed": SEED_INPUT,
            },
            "optional": {
                "branch_1": ("STRING", {"default": "", "forceInput": True}),
                "branch_2": ("STRING", {"default": "", "forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("text", "branch")
    FUNCTION = "select_section"
    CATEGORY = "Dynamic Prompt Engine"

    def select_section(self, mode, seed=0, branch_1="", branch_2=""):
        node_name = self.__class__.__name__

        if mode not in self.MODE_CHOICES:
            raise ValueError(
                f"{node_name}: 'mode' must be one of {set(self.MODE_CHOICES)}, "
                f"got '{mode}'."
            )

        try:
            master_seed = int(seed)
        except (TypeError, ValueError):
            raise ValueError(
                f"{node_name}: 'seed' must be a valid integer, got {seed!r}."
            )

        if mode == "Random":
            branch = derive_stream_seed(master_seed, self.STREAM_KEY) % 2
        elif mode == "1girl":
            branch = 0
        else:  # "2girls"
            branch = 1

        chosen = branch_1 if branch == 0 else branch_2
        text = join_prompt_parts(chosen)

        return (text, branch)


class TagJoin:
    """Joins connected tag strings in input order and displays the resulting text."""

    DESCRIPTION = (
        "Concatenates connected tag_N strings in numeric order. Skips empty/"
        "whitespace tags and strips leading/trailing commas/spaces from each part; "
        "joins with ', ' and ends with ', ' when non-empty. Always shows a multiline "
        "text preview (placeholder until run; filled after execution — not a tag "
        "input). Dynamic sockets: connected tags + one spare. No seed. Outputs prompt."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": False,
                        "placeholder": "Joined prompt preview (empty until run)…",
                    },
                ),
            },
            "optional": FlexibleOptionalInputType(
                "STRING",
                {
                    "tag_0": ("STRING", {"default": "", "forceInput": True}),
                },
            ),
            "hidden": {
                "unique_id": "UNIQUE_ID",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("prompt",)
    FUNCTION = "join_tags"
    CATEGORY = "Dynamic Prompt Engine"
    OUTPUT_NODE = True

    def join_tags(self, text="", unique_id=None, extra_pnginfo=None, **kwargs):
        tag_keys = sorted(
            (key for key in kwargs if key.startswith("tag_")),
            key=lambda key: int(key.rsplit("_", 1)[1]),
        )
        clean_tags = []

        for k in tag_keys:
            value = nonempty_text(kwargs.get(k))
            if value is None:
                continue
            value = value.strip(", ")
            if value:
                clean_tags.append(value)

        final_prompt = ", ".join(clean_tags)
        if final_prompt:
            final_prompt += ", "

        node_uid = resolve_unique_id(unique_id)
        if node_uid is not None and extra_pnginfo is not None:
            if isinstance(extra_pnginfo, list) and extra_pnginfo:
                workflow = extra_pnginfo[0].get("workflow")
            elif isinstance(extra_pnginfo, dict):
                workflow = extra_pnginfo.get("workflow")
            else:
                workflow = None
            if workflow:
                node = next(
                    (
                        item
                        for item in workflow["nodes"]
                        if str(item["id"]) == node_uid
                    ),
                    None,
                )
                if node:
                    node["widgets_values"] = [final_prompt]

        return {
            "ui": {"text": [final_prompt]},
            "result": (final_prompt,),
        }
