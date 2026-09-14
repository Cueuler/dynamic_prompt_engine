"""Deterministic per-node randomness: stream seeds and the PCG64 pick/gate."""

import hashlib


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


def derive_stream_seed(master_seed, stream_key, suffix=""):
    """Deterministic 64-bit seed from master seed + stream key (+ optional suffix)."""
    key_str = f"{master_seed}:{stream_key}"
    if suffix:
        key_str = f"{key_str}:{suffix}"
    return int(hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:16], 16)


def pick_unique_line(pool_text, bypass_chance=False, dpe_seed=None, unique_id=None):
    """PCG64 line pick and 50% gate used by Unique Line Picker and Seeded Text Pool.

    Returns (text, master_seed, gated). gated is True when the 50% gate skipped
    the pick (Impact expand must not run).
    """
    import numpy as np

    master_seed = int(dpe_seed)
    stream_key = stream_key_from_unique_id(unique_id)
    lines = [
        line.strip()
        for line in str(pool_text or "").splitlines()
        if line.strip()
    ]

    if bypass_chance:
        gate_seed = derive_stream_seed(master_seed, stream_key, "gate")
        if int(np.random.default_rng(gate_seed).integers(0, 2)) == 0:
            return ("", master_seed, True)

    if not lines:
        return ("", master_seed, False)

    stream_seed = derive_stream_seed(master_seed, stream_key)
    index = int(np.random.default_rng(stream_seed).integers(0, len(lines)))
    chosen = lines[index]
    text = "" if chosen == "[empty]" else chosen
    return (text, master_seed, False)
