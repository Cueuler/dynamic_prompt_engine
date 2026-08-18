"""CLIP token chunk inspection for ComfyUI SDXL / SD1.5 encoders."""

CLIP_WINDOW_THRESHOLD = 256

ENCODER_LABELS = {
    "l": "CLIP-L",
    "g": "CLIP-G",
    "t5xxl": "T5-XXL",
}

CLIP_INVALID_MESSAGE = (
    "ERROR: clip input is invalid: None\n\n"
    "If the clip is from a checkpoint loader node your checkpoint does not "
    "contain a valid clip or text encoder model."
)


def encoder_label(name):
    return ENCODER_LABELS.get(name, name)


def encoder_tokenizer(root_tokenizer, name):
    """Resolve the sub-tokenizer for an encoder key from clip.tokenize()."""
    if root_tokenizer is None:
        return None
    if name == "l" and hasattr(root_tokenizer, "clip_l"):
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


def _decode_ids(token_ids, tokenizer):
    if not token_ids:
        return ""
    decode = getattr(tokenizer, "decode", None)
    if callable(decode):
        return decode(token_ids, skip_special_tokens=True)
    inv_vocab = getattr(tokenizer, "inv_vocab", {})
    text = "".join(inv_vocab.get(token_id, f"[{token_id}]") for token_id in token_ids)
    return text.replace("</w>", " ")


def reconstruct_content(content, tokenizer):
    """Rebuild readable text from chunk content pairs."""
    if not content:
        return ""

    parts = []
    int_ids = []

    for pair in content:
        token = _pair_token(pair)
        if isinstance(token, int):
            int_ids.append(token)
            continue
        if int_ids:
            parts.append(_decode_ids(int_ids, tokenizer))
            int_ids = []
        parts.append("[embedding]")

    if int_ids:
        parts.append(_decode_ids(int_ids, tokenizer))

    return " ".join(part for part in parts if part)


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


def format_encoder_section(name, chunks, root_tokenizer):
    tokenizer = encoder_tokenizer(root_tokenizer, name)
    label = encoder_label(name)
    window = _tokenizer_window(tokenizer)

    if window is None:
        return _format_unlimited_section(label, chunks, tokenizer)

    return _format_window_section(label, chunks, tokenizer, window)


def format_clip_token_report(token_dict, root_tokenizer):
    """Build the full multi-encoder report string."""
    if not token_dict:
        return ""

    sections = []
    for name, chunks in token_dict.items():
        sections.append(format_encoder_section(name, chunks, root_tokenizer))

    return "\n\n".join(section for section in sections if section)


class CLIPTokenReport:
    """Inspect CLIP token chunks without encoding."""

    DESCRIPTION = (
        "Tokenizes the prompt with the connected CLIP model and reports how "
        "ComfyUI splits it into 77-token CLIP windows (75 content tokens each "
        "for SDXL CLIP-L/G). Inspect-only: does not output conditioning.\n"
        "\n"
        "Wire the same CLIP and prompt you use with CLIPTextEncode. The on-node "
        "preview and report STRING show per-encoder chunk usage and reconstructed "
        "text per chunk."
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
                        "multiline": True,
                        "dynamicPrompts": False,
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("report",)
    FUNCTION = "inspect"
    CATEGORY = "Dynamic Prompt Engine"
    OUTPUT_NODE = True

    def inspect(self, clip, text):
        if clip is None:
            raise RuntimeError(CLIP_INVALID_MESSAGE)

        tokens = clip.tokenize(text)
        report = format_clip_token_report(tokens, clip.tokenizer)

        return {
            "ui": {"text": [report]},
            "result": (report,),
        }
