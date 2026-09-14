"""Dynamic ComfyUI socket/input schemas and kwargs index helpers."""


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


class RoutingSwitchOptionalInputs(dict):
    """STRING sockets for input_N and combo widgets for chance_N."""

    CHANCE_CHOICES = ["Default", "Off", "1.5x", "2x"]

    def __init__(self, data=None):
        super().__init__(data or {})
        self.data = data or {}

    def __getitem__(self, key):
        if key in self.data:
            return self.data[key]
        if key.startswith("chance_") and key[len("chance_"):].isdigit():
            return (
                list(self.CHANCE_CHOICES),
                {"default": "Default"},
            )
        if key.startswith("input_") and key[len("input_"):].isdigit():
            return ("STRING", {"default": "", "forceInput": True})
        return ("STRING", {"default": "", "forceInput": True})

    def __contains__(self, key):
        return True


def numbered_input_indices(kwargs, prefix):
    """Return sorted integer indices present in kwargs under prefix (uncapped)."""
    indices = []
    for key in kwargs:
        if not key.startswith(prefix):
            continue
        suffix = key[len(prefix):]
        if suffix.isdigit():
            indices.append(int(suffix))
    return sorted(indices)
