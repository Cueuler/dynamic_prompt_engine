"""Impact Pack wildcard expansion entry point."""


def process_impact_wildcards(text, seed):
    """Process a selected line with Impact Pack's exact wildcard implementation."""
    if "{" not in text and "__" not in text:
        return text

    try:
        from .impact_loader import ensure_impact_wildcards

        process = ensure_impact_wildcards()
    except ImportError:
        raise RuntimeError(
            "Wildcard syntax requires ComfyUI-Impact-Pack. "
            "In ComfyUI, install it as a sibling custom node. "
            "For local tests: pip install -r dev-requirements.txt && "
            "PYTHONPATH=. python -m dynamic_prompt_engine.setup_dev"
        ) from None

    return process(text, seed)
