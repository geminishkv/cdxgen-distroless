"""Тесты локального гейта: версии инструмента в хуке pre-commit и в пинах CI совпадают; исключение Trivy для zlib
существует только вместе с наложением пакета в Dockerfile."""
import re
import sys
import unittest
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "security"))
import common  # noqa: E402


class HookPinsTest(unittest.TestCase):
    def test_gitleaks_hook_matches_the_ci_pin(self):
        config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        hook = re.search(r"repo: https://github\.com/gitleaks/gitleaks\s+rev: v([\d.]+)", config)
        self.assertEqual(hook.group(1), common.VERSIONS["gitleaks"])


class ZlibOverlayTest(unittest.TestCase):
    def test_trivy_exception_exists_only_together_with_the_overlay(self):
        overlaid = set(re.findall(r"zlib1g_([^_\s]+)_(?:amd64|arm64)\.deb", (ROOT / "Dockerfile").read_text(encoding="utf-8")))
        ignored = set(re.findall(r"pkg:deb/debian/zlib1g@([^\s\"?]+)", (ROOT / ".trivyignore.yaml").read_text(encoding="utf-8")))
        self.assertEqual({urllib.parse.unquote(version) for version in ignored}, overlaid)


if __name__ == "__main__":
    unittest.main()
