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


MAX_BRANCHES = 15


def connected_input_indices(kwargs, prefix, max_count):
    """Return sorted in-range integer indices present in kwargs under prefix."""
    indices = []
    for key in kwargs:
        if not key.startswith(prefix):
            continue
        suffix = key[len(prefix):]
        if not suffix.isdigit():
            continue
        index = int(suffix)
        if 0 <= index < max_count:
            indices.append(index)
    return sorted(indices)


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
        "Picks one line from pool_text. Choice is hash(seed:node:{id}) % n, so "
        "two copies of this node with the same seed can still pick different "
        "lines. Outputs: text, and seed unchanged.\n"
        "\n"
        "Candidates: split on newlines, strip each line, drop blank/whitespace "
        "lines. Only remaining lines are in the pool.\n"
        "\n"
        "Bypass chance Off: never gates. 50%: hash(seed:node:{id}:gate) % 2 == 0 "
        "returns empty text (this check runs even if the pool is empty).\n"
        "\n"
        "Examples: pool 'alice\\nbob\\ncharlie' → one of those three, stable for "
        "the same seed+node. 'alice\\n\\n  \\nbob' → only alice and bob. Chosen "
        "line '[empty]' → empty string. Empty pool → empty string.\n"
        "\n"
        "Edge cases: the literal line [empty] is a candidate that emits blank "
        "(not skipped). Impact Pack {a|b} / __wildcard__ runs only on the chosen "
        "line and requires ComfyUI-Impact-Pack (raises if missing). Seed is "
        "passed through even when text is empty."
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
        self, pool_text, bypass_chance=False, seed=0, unique_id=None
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


class BranchSelector:
    """Selects the input at the given branch index (N-way)."""

    DESCRIPTION = (
        "Returns input_{branch} (sockets input_0…input_14). The branch integer "
        "is a socket index, not 'the Nth wired input'. No seed. Wire Branch "
        "Random Switcher's branch output here so the numbers match "
        "(branch_2 → input_2).\n"
        "\n"
        "Not connected (socket unwired): text is 'branch {n} skipped', e.g. "
        "'branch 2 skipped'.\n"
        "Connected with an empty or whitespace-only string: that empty string "
        "is passed through (not skipped). Tag Join will drop it.\n"
        "Connected with text: that string, whitespace-stripped.\n"
        "\n"
        "Examples: branch=1 and input_1='bob' → 'bob'. Switcher has 3 branches "
        "and this node only has input_0 and input_1 → pick 2 yields "
        "'branch 2 skipped'. input_2 wired to '' → ''.\n"
        "\n"
        "Edge cases: branch outside 0…14 raises. Whitespace-only connected "
        "values become ''. 'branch N skipped' is real text; Tag Join will "
        "include it if you wire this output into a join."
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
                        "max": MAX_BRANCHES - 1,
                        "step": 1,
                        "forceInput": True,
                    },
                ),
            },
            "optional": FlexibleOptionalInputType(
                "STRING",
                {"input_0": ("STRING", {"default": "", "forceInput": True})},
            ),
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "select"
    CATEGORY = "Dynamic Prompt Engine"

    def select(self, branch, **kwargs):
        node_name = self.__class__.__name__

        try:
            index = int(branch)
        except (TypeError, ValueError):
            raise ValueError(
                f"{node_name}: 'branch' must be a valid integer, got {branch!r}."
            )

        if not (0 <= index < MAX_BRANCHES):
            raise ValueError(
                f"{node_name}: 'branch' must be between 0 and {MAX_BRANCHES - 1}, "
                f"got {index}."
            )

        key = f"input_{index}"
        if key not in kwargs or kwargs.get(key) is None:
            return (f"branch {index} skipped",)
        return (nonempty_text(kwargs.get(key)) or "",)


class BranchRandomSwitcher:
    """Randomly selects one connected branch and outputs its text and index."""

    DESCRIPTION = (
        "Seeded pick among wired branch_0…branch_14 sockets (max 15). Outputs "
        "text and branch (the socket index 0…14, not 'Nth wire'). Same seed+"
        "node id is deterministic; different node ids can differ. Unplug a "
        "socket to drop it from the rotation.\n"
        "\n"
        "0 wired: text is empty; branch is hash(seed:node:{id}) % 2 (0 or 1).\n"
        "1 wired: branch is that socket's index (only branch_5 → always 5); "
        "text is that value after comma hygiene.\n"
        "2+ wired: seeded pick among those indices; text is the chosen value "
        "after comma hygiene (strip empty/whitespace, strip extra commas, "
        "join with ', ' and a trailing ', ' when non-empty).\n"
        "\n"
        "Examples: branch_0=red, branch_1=blue, branch_2=green → branch is 0, 1, "
        "or 2 and text is 'red, ' / 'blue, ' / 'green, '. Only branch_5 wired "
        "→ always branch=5.\n"
        "\n"
        "Edge cases: a wired empty string still counts as connected; if picked, "
        "text is '' and branch is that index (selector should pass '' through "
        "if the matching input is also wired). 0 wired still emits branch 0 or "
        "1, so a selector may return 'branch 1 skipped' if input_1 is unwired. "
        "Match selector input_N to switcher branch_N."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": SEED_INPUT,
            },
            "optional": FlexibleOptionalInputType(
                "STRING",
                {"branch_0": ("STRING", {"default": "", "forceInput": True})},
            ),
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("text", "branch")
    FUNCTION = "select_branch"
    CATEGORY = "Dynamic Prompt Engine"

    def select_branch(self, seed=0, unique_id=None, **kwargs):
        node_name = self.__class__.__name__

        try:
            master_seed = int(seed)
        except (TypeError, ValueError):
            raise ValueError(
                f"{node_name}: 'seed' must be a valid integer, got {seed!r}."
            )

        connected = connected_input_indices(kwargs, "branch_", MAX_BRANCHES)
        stream_key = stream_key_from_unique_id(unique_id)

        if not connected:
            branch = derive_stream_seed(master_seed, stream_key) % 2
            text = ""
        elif len(connected) == 1:
            branch = connected[0]
            text = join_prompt_parts(kwargs[f"branch_{branch}"])
        else:
            choice = derive_stream_seed(master_seed, stream_key) % len(connected)
            branch = connected[choice]
            text = join_prompt_parts(kwargs[f"branch_{branch}"])

        return (text, branch)


class TagJoin:
    """Joins connected tag strings in input order and displays the resulting text."""

    DESCRIPTION = (
        "Joins wired tag_N strings in numeric index order (tag_0, tag_1, …; "
        "tag_10 after tag_2). Dynamic sockets: connected tags + one spare. No "
        "seed. The multiline text widget is a preview only (filled after run), "
        "not a tag input. Output: prompt.\n"
        "\n"
        "Each tag: skip if empty/whitespace; strip leading/trailing commas and "
        "spaces; skip again if nothing remains. Join survivors with ', ' and "
        "add a trailing ', ' when the result is non-empty. All empty → ''.\n"
        "\n"
        "Examples: tag_0='red', tag_1='blue' → 'red, blue, '. tag_0='', "
        "tag_1='blue' → 'blue, '. tag_0='red,', tag_1=', blue' → 'red, blue, '. "
        "tag_0 and tag_2 wired, tag_1 empty/unwired → join 0 then 2.\n"
        "\n"
        "Edge cases: a selector marker like 'branch 2 skipped' is non-empty, so "
        "it is included in the prompt. Holes in tag indices are allowed; order "
        "is by number, not socket position."
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
            (
                key
                for key in kwargs
                if key.startswith("tag_") and key[len("tag_"):].isdigit()
            ),
            key=lambda key: int(key[len("tag_"):]),
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
