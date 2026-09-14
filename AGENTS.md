# AGENTS.md — guide for AI coding agents

ComfyUI custom-node pack for seed-reproducible prompt building.
Python 3.10+ backend, vanilla-JS frontend. **The repo root IS the Python
package** (`dynamic_prompt_engine/` folder = package): run Python from repo
root with `PYTHONPATH=".."`, never from inside the package.

## Commands

```bash
# Python suite (from repo root; 90 skips are expected without the Impact fixture)
PYTHONPATH=".." python -m unittest discover -s tests -v

# Frontend tests (must run from web/)
cd web && node --test        # `node --test web/` is broken on Node 24/Windows

# Optional Impact Pack fixture — enables wildcard-oracle tests (removes the 90 skips)
pip install -r dev-requirements.txt
PYTHONPATH=. python -m dynamic_prompt_engine.setup_dev   # run from the PARENT dir
```

CI (`.github/workflows/ci.yml`) runs both suites; wildcard tests self-skip via
`@unittest.skipUnless(IMPACT_PROCESS_AVAILABLE, ...)` — never let a fixture gap
become a red CI.

## Layout

| Path | Role |
|---|---|
| `__init__.py` | Only node registration (`NODE_CLASS_MAPPINGS`) + `WEB_DIRECTORY` + onprompt handler registration |
| `core/` | Pure logic. **Zero ComfyUI imports.** `rng.py` (stream seeds, PCG64 pick/gate), `seeding.py` (seed contract: `PICKER_HIDDEN`, `master_seed_from_dpe`, `PICKER_NODE_CLASSES`), `text.py` (chance weights, comma hygiene), `dynamic_inputs.py` (dynamic socket schemas), `token_report.py` (CLIP tokenization/report/overflow helpers), `wildcards.py` + `impact_loader.py` (Impact expansion + peer-dep loader) |
| `nodes/` | Thin ComfyUI adapters, one file per node family. INPUT_TYPES/DESCRIPTION + delegation to `core/`. `nodes/global_seed.py` also owns the queue-time injection handler (`apply_global_seed_onprompt`); `nodes/resolution.py` imports torch and is registered via a try/except in `__init__.py` |
| `setup_dev.py` | Dev-only: clones the Impact fixture. Only module allowed at repo root besides `__init__.py` |
| `web/` | Frontend. `dynamic_prompt_engine.js` registrations; tests colocated (`*.test.js`) |
| `tests/` | stdlib `unittest`, no pytest/conftest |

Import direction: `nodes → core`. Never the reverse. `numpy` is imported
inside functions (keeps modules importable without it).

## Seed system (do not break)

- Exactly one **DPE Global Seed** per workflow; at queue time it injects a
  hidden `dpe_seed` INT into every node class listed in `PICKER_NODE_CLASSES`
  (global_seed.py). A seeded node executed without the inject raises
  `GlobalSeedError` (via `master_seed_from_dpe`) — this is intentional.
- Pickers have **no seed widgets**; adding one breaks the architecture.
- Determinism contract: same master seed + same node `unique_id` → same output.
  Stream seed = `int(sha256(f"{seed}:node:{id}")[:16], 16)` (`derive_stream_seed`).
- All randomness is seeded: PCG64 (`np.random.default_rng(stream_seed).integers`)
  for picks and the 50% bypass gate (gate uses suffix `":gate"`); Routing
  Switch uses `stream_seed % total_weight` with a cumulative walk.
  Never use the stdlib `random` module or unseeded numpy.
- Routing Switch weights: `Default=2, 1.5x=3, 2x=4`; `Off`/unconnected slots
  are excluded and add no weight. `P(slot) = weight / Σweights`.

## Adding a node (checklist)

1. `nodes/<name>.py` — class with `INPUT_TYPES`, `FUNCTION`, `RETURN_TYPES`,
   `CATEGORY = "Dynamic Prompt Engine"`, user-facing `DESCRIPTION`.
2. Export in `nodes/__init__.py`; register in root `__init__.py`
   (both mapping dicts; `PICKER_NODE_CLASSES` too if it consumes `dpe_seed`).
3. Tests in `tests/test_<name>.py` (see conventions below). TDD: watch tests
   fail first.
4. Frontend registration in `web/dynamic_prompt_engine.js` only if it needs
   dynamic sockets/previews.
5. README: node table row + section; AGENTS.md layout table if new dir.

## Test conventions

- **Spec oracles**: tests re-implement the documented math independently
  (e.g. `spec_pick` in test_branch_nodes.py) and compare node output against
  them over seed sweeps. Keep oracles independent of production code.
- **Patch where the name is used**, not where it is defined — e.g. Routing
  Switch's seed derivation is patched at
  `dynamic_prompt_engine.nodes.routing_switch.derive_stream_seed`.
- Distribution tests: `monte_carlo_route_wins` + 4σ binomial bands
  (test_branch_nodes.py). Deterministic hash → never flaky once green.
- Reusable fakes live in the test files (`FakeClipTokenizer`, MagicMock CLIP).
  When a test builds a MagicMock CLIP, always set `clip.tokenizer` if the code
  path reads it.

## Style

- Node `DESCRIPTION`s are end-user documentation — update them when behavior
  changes. Same for the README node table/sections.
- Match existing tone: plain statements of behavior, edge cases spelled out.
- Commit only when the user asks.
