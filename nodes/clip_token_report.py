"""CLIP Token Report node: tokenizes and reports without encoding."""

from ..core.token_report import (
    CLIP_INVALID_MESSAGE,
    format_clip_token_report,
    tokenize_prompt_with_overflow,
)


class CLIPTokenReport:
    """Inspect CLIP token chunks without encoding."""

    DESCRIPTION = (
        "CLIP Token Report: tokenizes the prompt with the connected CLIP model and reports how "
        "ComfyUI splits it into 77-token CLIP windows (75 content tokens each "
        "for SDXL CLIP-L/G). Inspect-only: does not output conditioning.\n"
        "\n"
        "Wire prompt text from upstream nodes (socket input). Chunk text lines use "
        "tokenizer.decode() on each chunk's content token ids.\n"
        "\n"
        "A1111 BREAK (word-boundary BREAK) starts a new CLIP window: each segment is "
        "tokenized separately so BREAK is not counted as a content token.\n"
        "\n"
        "overflow output: True when any single BREAK segment fills or exceeds one "
        "window's content capacity (75 for CLIP-L/G) — 75/75 counts, since it "
        "leaves no headroom. Segments are judged on their own, so short segments "
        "joined by BREAK do not trigger it. Windowless encoders (e.g. T5-XXL) never "
        "overflow. Commas are content tokens; only whitespace around BREAK is dropped."
    )

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP",),
                "text": (
                    "STRING",
                    {
                        "default": "",
                        "forceInput": True,
                    },
                ),
                "report": (
                    "STRING",
                    {
                        "default": "",
                        "multiline": True,
                        "dynamicPrompts": False,
                        "placeholder": "Token report preview (empty until run)…",
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING", "BOOLEAN")
    RETURN_NAMES = ("report", "overflow")
    FUNCTION = "inspect"
    CATEGORY = "Dynamic Prompt Engine"
    OUTPUT_NODE = True

    def inspect(self, clip, text, report=""):
        del report  # preview widget only; filled from execution result
        if clip is None:
            raise RuntimeError(CLIP_INVALID_MESSAGE)

        tokens, overflow_by_encoder = tokenize_prompt_with_overflow(clip, text)
        report_text = format_clip_token_report(
            tokens, clip.tokenizer, overflow_by_encoder
        )

        return {
            "ui": {"report": [report_text]},
            "result": (report_text, any(overflow_by_encoder.values())),
        }
