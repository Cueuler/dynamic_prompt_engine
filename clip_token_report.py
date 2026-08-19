"""CLIP token chunk inspection for ComfyUI SDXL / SD1.5 encoders."""

import re

CLIP_WINDOW_THRESHOLD = 256

# A1111 keyword: force a new 77-token CLIP window. Not implemented by stock
# clip.tokenize() or BlenderNeko ADV CLIP (those tokenize the whole string).
BREAK_SPLIT = re.compile(r"\s*\bBREAK\b\s*")

ENCODER_LABELS = {
    "l": "CLIP-L",
    "g": "CLIP-G",
    "l/g": "CLIP-L / CLIP-G",
    "t5xxl": "T5-XXL",
}

CLIP_INVALID_MESSAGE = (
    "ERROR: clip input is invalid: None\n\n"
    "If the clip is from a checkpoint loader node your checkpoint does not "
    "contain a valid clip or text encoder model."
)


def encoder_label(name):
    return ENCODER_LABELS.get(name, name)


def break_segments(text):
    """Split a prompt on A1111 BREAK into independently tokenized segments."""
    parts = BREAK_SPLIT.split("" if text is None else str(text))
    return [part.strip() for part in parts if part.strip()]


def merge_token_dicts(left, right):
    """Concatenate per-encoder chunk lists (each BREAK segment is extra windows)."""
    if left is None:
        return {key: list(chunks) for key, chunks in right.items()}
    merged = {key: list(chunks) for key, chunks in left.items()}
    for key, chunks in right.items():
        merged[key] = merged.get(key, []) + list(chunks)
    return merged


def tokenize_prompt(clip, text):
    """Tokenize like A1111 BREAK: each segment is its own clip.tokenize() call."""
    segments = break_segments(text)
    if not segments:
        return clip.tokenize("")
    merged = None
    for segment in segments:
        merged = merge_token_dicts(merged, clip.tokenize(segment))
    return merged


def encoder_tokenizer(root_tokenizer, name):
    """Resolve the sub-tokenizer for an encoder key from clip.tokenize()."""
    if root_tokenizer is None:
        return None
    if name in ("l", "l/g") and hasattr(root_tokenizer, "clip_l"):
        return root_tokenizer.clip_l
    if name == "g" and hasattr(root_tokenizer, "clip_g"):
        return root_tokenizer.clip_g
    attr = f"clip_{name}"
    if hasattr(root_tokenizer, attr):
        return getattr(root_tokenizer, attr)
    return root_tokenizer


def _pair_token(pair):
    return pair[0] if pair else None


def content_from_chunk(chunk, start_token, end_token):
    """Return content items (token_id_or_embedding, weight) after BOS until EOS."""
    if not chunk:
        return []

    content = []
    past_start = start_token is None

    for pair in chunk:
        token = _pair_token(pair)
        if not past_start:
            if token == start_token:
                past_start = True
            continue
        if end_token is not None and token == end_token:
            break
        content.append(pair)

    return content


def content_token_count(content):
    """Count content slots; embeddings count as one each."""
    return len(content)


def _content_token_key(token):
    if isinstance(token, int):
        return ("int", token)
    return ("embed", id(token))


def content_signature(chunks, tokenizer):
    """Comparable chunk content signature (ignores padding after EOS)."""
    window = _tokenizer_window(tokenizer)
    if window is None:
        return tuple(tuple(_content_token_key(_pair_token(pair)) for pair in chunk) for chunk in chunks)

    start_token = window["start_token"]
    end_token = window["end_token"]
    signature = []
    for chunk in chunks:
        content = content_from_chunk(chunk, start_token, end_token)
        signature.append(tuple(_content_token_key(_pair_token(pair)) for pair in content))
    return tuple(signature)


def _decode_ids(token_ids, tokenizer):
    if not token_ids:
        return ""
    decode = getattr(tokenizer, "decode", None)
    if callable(decode):
        return decode(token_ids, skip_special_tokens=True)
    return ""


def reconstruct_content(content, tokenizer):
    """Rebuild readable text from chunk content pairs."""
    if not content:
        return ""

    pieces = []
    int_ids = []

    def flush_ids():
        nonlocal int_ids
        if int_ids:
            pieces.append(_decode_ids(int_ids, tokenizer))
            int_ids = []

    for pair in content:
        token = _pair_token(pair)
        if isinstance(token, int):
            int_ids.append(token)
            continue
        flush_ids()
        if pieces:
            pieces[-1] = pieces[-1].rstrip()
        pieces.append(" [embedding] ")

    flush_ids()
    return "".join(pieces)


def _tokenizer_window(tokenizer):
    max_length = getattr(tokenizer, "max_length", None)
    if max_length is None or max_length > CLIP_WINDOW_THRESHOLD:
        return None
    start_token = getattr(tokenizer, "start_token", None)
    end_token = getattr(tokenizer, "end_token", None)
    has_end = end_token is not None
    content_capacity = max_length - (1 if start_token is not None else 0)
    if has_end:
        content_capacity -= 1
    content_capacity = max(content_capacity, 0)
    return {
        "max_length": max_length,
        "start_token": start_token,
        "end_token": end_token,
        "content_capacity": content_capacity,
    }


def _format_unlimited_section(label, chunks, tokenizer):
    total = 0
    lines = [label, ""]
    for chunk in chunks:
        window = _tokenizer_window(tokenizer)
        if window is None:
            content = [pair for pair in chunk]
        else:
            content = content_from_chunk(
                chunk, window["start_token"], window["end_token"]
            )
        total += content_token_count(content)
    lines.append(f"tokens: {total}")
    lines.append("")
    return "\n".join(lines)


def _format_window_section(label, chunks, tokenizer, window):
    max_length = window["max_length"]
    content_capacity = window["content_capacity"]
    start_token = window["start_token"]
    end_token = window["end_token"]

    chunk_contents = []
    total_content = 0
    for chunk in chunks:
        content = content_from_chunk(chunk, start_token, end_token)
        chunk_contents.append(content)
        total_content += content_token_count(content)

    chunk_count = len(chunks) if chunks else 1
    overflow = total_content > content_capacity

    lines = [
        f"{label}  window {max_length}, content capacity {content_capacity}",
        (
            f"chunks: {chunk_count}    content tokens: {total_content}    "
            f"overflow: {'yes' if overflow else 'no'}"
        ),
        "",
    ]

    if not chunks:
        chunks = [[]]

    for index, content in enumerate(chunk_contents, start=1):
        used = content_token_count(content)
        lines.append(f"[chunk {index}/{chunk_count}]  {used}/{content_capacity}")
        lines.append(reconstruct_content(content, tokenizer))
        lines.append("")

    return "\n".join(lines).rstrip()


def format_encoder_section(name, chunks, root_tokenizer, label=None):
    tokenizer = encoder_tokenizer(root_tokenizer, name)
    label = label or encoder_label(name)
    window = _tokenizer_window(tokenizer)

    if window is None:
        return _format_unlimited_section(label, chunks, tokenizer)

    return _format_window_section(label, chunks, tokenizer, window)


def _iter_report_sections(token_dict, root_tokenizer):
    """Yield (encoder_name, chunks, label) with identical SDXL L/G merged."""
    names = list(token_dict.keys())
    merge_l_g = False

    if "l" in token_dict and "g" in token_dict:
        tok_l = encoder_tokenizer(root_tokenizer, "l")
        tok_g = encoder_tokenizer(root_tokenizer, "g")
        merge_l_g = content_signature(token_dict["l"], tok_l) == content_signature(
            token_dict["g"], tok_g
        )

    for name in names:
        if merge_l_g and name == "l":
            yield "l/g", token_dict["l"], encoder_label("l/g")
            continue
        if merge_l_g and name == "g":
            continue
        yield name, token_dict[name], encoder_label(name)


def format_clip_token_report(token_dict, root_tokenizer):
    """Build the full multi-encoder report string."""
    if not token_dict:
        return ""

    sections = []
    for name, chunks, label in _iter_report_sections(token_dict, root_tokenizer):
        sections.append(format_encoder_section(name, chunks, root_tokenizer, label=label))

    return "\n\n".join(section for section in sections if section)


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
        "tokenized separately so BREAK is not counted as a content token."
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

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("report",)
    FUNCTION = "inspect"
    CATEGORY = "Dynamic Prompt Engine"
    OUTPUT_NODE = True

    def inspect(self, clip, text, report=""):
        del report  # preview widget only; filled from execution result
        if clip is None:
            raise RuntimeError(CLIP_INVALID_MESSAGE)

        tokens = tokenize_prompt(clip, text)
        report_text = format_clip_token_report(tokens, clip.tokenizer)

        return {
            "ui": {"report": [report_text]},
            "result": (report_text,),
        }
