"""Тесты локального гейта: версии одного инструмента в хуке pre-commit и в пинах CI совпадают."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "security"))
import common  # noqa: E402


class HookPinsTest(unittest.TestCase):
    def test_gitleaks_hook_matches_the_ci_pin(self):
        config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        hook = re.search(r"repo: https://github\.com/gitleaks/gitleaks\s+rev: v([\d.]+)", config)
        self.assertEqual(hook.group(1), common.VERSIONS["gitleaks"])


if __name__ == "__main__":
    unittest.main()
