"""Clone a pinned ComfyUI-Impact-Pack commit into .dev/ for tests (no ComfyUI)."""

from pathlib import Path
import sys

_ROOT = Path(__file__).resolve().parent
if str(_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_ROOT.parent))

from dynamic_prompt_engine.impact_loader import (
    DEV_IMPACT_DIR,
    IMPACT_PACK_COMMIT,
    clone_impact_pack,
)


def main():
    root = clone_impact_pack()
    print(f"Impact Pack test fixture ready at {root}")
    print(f"pinned commit: {IMPACT_PACK_COMMIT}")
    print(f"default location: {DEV_IMPACT_DIR}")


if __name__ == "__main__":
    main()
