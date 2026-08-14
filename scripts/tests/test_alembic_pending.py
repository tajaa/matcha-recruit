"""Regression tests for the multi-head migration preview."""

import importlib.util
from pathlib import Path
import unittest

from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "alembic_pending.py"
SPEC = importlib.util.spec_from_file_location("alembic_pending", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PendingRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config = Config(str(ROOT / "server" / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "server" / "alembic"))
        cls.script = ScriptDirectory.from_config(config)

    def pending_ids(self, *current):
        return [rev.revision for rev in MODULE.pending_revisions(self.script, current)]

    def test_sibling_head_does_not_hide_ems04(self):
        pending = self.pending_ids("mwperm02")

        self.assertIn("ems04", pending)
        self.assertLess(pending.index("ems04"), pending.index("cappeaiaccess01"))

    def test_merge_head_is_not_reported_as_applied_when_parent_is_missing(self):
        pending = self.pending_ids("ems03")

        self.assertIn("ems04", pending)
        self.assertIn("mwperm02", pending)
        self.assertIn("cappeaiaccess01", pending)

    def test_all_current_heads_have_no_pending_revisions(self):
        pending = self.pending_ids(*self.script.get_heads())

        self.assertEqual(pending, [])


if __name__ == "__main__":
    unittest.main()
