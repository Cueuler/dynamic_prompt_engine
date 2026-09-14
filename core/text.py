"""Prompt text hygiene and Routing Switch chance weights."""

CHANCE_WEIGHTS = {
    "Default": 2,
    "1.5x": 3,
    "2x": 4,
}


def nonempty_text(value):
    """Return stripped text, or None if absent/empty/whitespace-only."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def normalize_chance_value(value):
    """Coerce a chance widget/kwargs value to a label; missing/blank is Default."""
    if value is None:
        return "Default"
    if isinstance(value, (list, tuple)):
        value = value[0] if value else "Default"
    text = str(value).strip()
    return text if text else "Default"


def chance_weight(value):
    """Return integer lottery weight, or None when the slot is Off."""
    label = normalize_chance_value(value)
    if label == "Off":
        return None
    return CHANCE_WEIGHTS.get(label, CHANCE_WEIGHTS["Default"])
