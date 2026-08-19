"""Impact Pack is a runtime peer dependency; tests use a pinned gitignored clone.

Runtime (ComfyUI): import the user's installed pack. Never clone, never stub ComfyUI.
Dev/tests: clone a pinned commit into .dev/ and stub ComfyUI-only imports.
"""

import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

PACKAGE_ROOT = Path(__file__).resolve().parent
IMPACT_PACK_REPO = "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git"
# Pin so oracle tests stay stable. Bump this when deliberately tracking Impact.
IMPACT_PACK_COMMIT = "429d0159ad429e64d2b3916e6e7be9c22d025c3c"
DEV_IMPACT_DIR = PACKAGE_ROOT / ".dev" / "ComfyUI-Impact-Pack"


def _modules_dir(root):
    modules = Path(root) / "modules"
    if (modules / "impact" / "wildcards.py").is_file():
        return modules
    return None


def runtime_impact_roots():
    """ComfyUI custom_nodes siblings only — not .dev or explore copies."""
    parent = PACKAGE_ROOT.parent
    return [
        parent / "ComfyUI-Impact-Pack",
        parent / "comfyui-impact-pack",
    ]


def dev_impact_roots():
    """Test fixture locations. IMPACT_PACK_ROOT overrides the default clone dir."""
    env = os.environ.get("IMPACT_PACK_ROOT")
    roots = []
    if env:
        roots.append(Path(env))
    roots.append(DEV_IMPACT_DIR)
    return roots


def find_runtime_impact_modules():
    for root in runtime_impact_roots():
        found = _modules_dir(root)
        if found:
            return found
    return None


def find_dev_impact_modules():
    for root in dev_impact_roots():
        found = _modules_dir(root)
        if found:
            return found
    return None


def clone_impact_pack(dest=DEV_IMPACT_DIR, commit=IMPACT_PACK_COMMIT):
    """Clone or update the gitignored test fixture to the pinned commit."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    git_dir = dest / ".git"
    if git_dir.is_dir():
        subprocess.run(
            ["git", "-C", str(dest), "fetch", "--depth", "1", "origin", commit],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(dest), "checkout", "--force", "FETCH_HEAD"],
            check=True,
        )
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not git_dir.is_dir():
        raise RuntimeError(
            f"{dest} exists but is not a git clone. Remove it or set IMPACT_PACK_ROOT."
        )
    subprocess.run(
        ["git", "init", str(dest)],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "remote", "add", "origin", IMPACT_PACK_REPO],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "fetch", "--depth", "1", "origin", commit],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(dest), "checkout", "--force", "FETCH_HEAD"],
        check=True,
    )
    return dest


def _install_comfy_stubs():
    """wildcards.py imports ComfyUI; stub only when ComfyUI is not installed."""
    if "folder_paths" not in sys.modules:
        try:
            import folder_paths  # noqa: F401
        except ImportError:
            folder_paths = ModuleType("folder_paths")
            folder_paths.get_filename_list = lambda name: []
            folder_paths.get_full_path = lambda *a, **k: None
            folder_paths.supported_pt_extensions = set()
            folder_paths.models_dir = "/tmp"
            folder_paths._dpe_stub = True
            sys.modules["folder_paths"] = folder_paths
    if "nodes" not in sys.modules:
        try:
            import nodes  # noqa: F401
        except ImportError:
            nodes = ModuleType("nodes")
            nodes.NODE_CLASS_MAPPINGS = {}
            sys.modules["nodes"] = nodes
    if "impact.utils" not in sys.modules:
        sys.modules["impact.utils"] = ModuleType("impact.utils")


def _import_process(modules, stub_comfy):
    modules_str = str(modules)
    if modules_str not in sys.path:
        sys.path.insert(0, modules_str)
    if stub_comfy:
        _install_comfy_stubs()
    from impact.wildcards import process

    return process


def is_comfyui_runtime():
    """True only for a real ComfyUI install, not the test stub."""
    try:
        import folder_paths
    except ImportError:
        return False
    return not getattr(folder_paths, "_dpe_stub", False)


def ensure_impact_wildcards(mode=None):
    """Load impact.wildcards.process.

    mode="runtime": user's ComfyUI-installed pack only. No clone, no ComfyUI stubs.
    mode="dev": pinned .dev clone or IMPACT_PACK_ROOT, with ComfyUI stubs.
    mode=None: runtime inside ComfyUI, otherwise the test fixture.
    """
    if mode is None:
        mode = "runtime" if is_comfyui_runtime() else "dev"
    if mode == "runtime":
        try:
            from impact.wildcards import process

            return process
        except ImportError:
            modules = find_runtime_impact_modules()
            if modules is None:
                raise ImportError(
                    "ComfyUI-Impact-Pack is not installed as a sibling custom node."
                )
            return _import_process(modules, stub_comfy=False)

    modules = find_dev_impact_modules()
    if modules is None:
        raise ImportError(
            "Impact Pack test fixture missing. Run: "
            "PYTHONPATH=. python -m dynamic_prompt_engine.setup_dev"
        )
    return _import_process(modules, stub_comfy=True)
