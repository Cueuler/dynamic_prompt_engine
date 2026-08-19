"""Tests for Impact Pack peer-dependency vs pinned test fixture."""

import unittest

from dynamic_prompt_engine.impact_loader import (
    DEV_IMPACT_DIR,
    IMPACT_PACK_COMMIT,
    PACKAGE_ROOT,
    dev_impact_roots,
    runtime_impact_roots,
)


class TestImpactPackPin(unittest.TestCase):
    def test_commit_is_full_sha(self):
        self.assertRegex(IMPACT_PACK_COMMIT, r"^[0-9a-f]{40}$")

    def test_dev_fixture_lives_under_gitignored_dot_dev(self):
        self.assertEqual(DEV_IMPACT_DIR, PACKAGE_ROOT / ".dev" / "ComfyUI-Impact-Pack")

    def test_runtime_roots_are_comfy_siblings_only(self):
        roots = runtime_impact_roots()
        self.assertTrue(all(root.parent == PACKAGE_ROOT.parent for root in roots))
        self.assertFalse(any(".dev" in str(root) or ".tmp_explore" in str(root) for root in roots))

    def test_dev_roots_do_not_use_explore_cache(self):
        roots = [str(path) for path in dev_impact_roots()]
        self.assertFalse(any(".tmp_explore" in path for path in roots))
        self.assertTrue(any(str(DEV_IMPACT_DIR) == path for path in roots))

    def test_without_comfyui_loader_is_not_runtime(self):
        from dynamic_prompt_engine.impact_loader import is_comfyui_runtime

        self.assertFalse(is_comfyui_runtime())


if __name__ == "__main__":
    unittest.main()
