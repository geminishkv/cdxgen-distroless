"""Тесты разборщиков отчётов (на фикстурах) и таблицы пинов инструментов."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "security"))
import common  # noqa: E402
import hadolint  # noqa: E402
import trivy_config  # noqa: E402
import trivy_image  # noqa: E402

TRIVY = {"Metadata": {"OS": {"Family": "debian", "Name": "13.7"}},
         "Results": [{"Target": "img (debian 13.7)", "Type": "debian", "Packages": [{"Name": "zlib1g"}, {"Name": "libc6"}],
                      "Vulnerabilities": [{"VulnerabilityID": "CVE-A", "PkgName": "zlib1g", "InstalledVersion": "1.3", "Severity": "HIGH"},
                                          {"VulnerabilityID": "CVE-B", "PkgName": "libc6", "InstalledVersion": "2.41", "Severity": "CRITICAL", "FixedVersion": "2.42"}]},
                     {"Target": "Node.js", "Type": "node-pkg", "Packages": [{"Name": "glob"}],
                      "Vulnerabilities": [{"VulnerabilityID": "CVE-C", "PkgName": "glob", "InstalledVersion": "13.0.6", "Severity": "MEDIUM", "FixedVersion": "14.0.2"}]}]}


class TrivyImageTest(unittest.TestCase):
    def test_gate_blocks_only_fixable_critical_and_high(self):
        findings, coverage = trivy_image.parse(TRIVY)
        self.assertEqual(coverage, {"targets": 2, "packages": 3, "os": "debian 13.7", "os_packages": 2, "npm_packages": 1})
        self.assertEqual([f["id"] for f in trivy_image.blocking(findings)], ["CVE-B"])
        self.assertEqual(findings[0]["fix"], "исправления нет")

    def test_missing_package_layer_is_visible_in_coverage(self):
        _, coverage = trivy_image.parse({**TRIVY, "Results": TRIVY["Results"][:1]})
        self.assertEqual((coverage["os_packages"], coverage["npm_packages"]), (2, 0))

    def test_accepted_findings_do_not_block(self):
        findings, _ = trivy_image.parse(TRIVY)
        for f in findings:
            f["status"] = "accepted"
        self.assertEqual(trivy_image.blocking(findings), [])


class TrivyConfigTest(unittest.TestCase):
    def test_parse_counts_checks_and_maps_severity(self):
        report = {"Results": [{"Target": "Dockerfile", "MisconfSummary": {"Successes": 26, "Failures": 1},
                               "Misconfigurations": [{"ID": "DS002", "Severity": "HIGH", "Title": "root user", "Resolution": "Add USER",
                                                      "CauseMetadata": {"StartLine": 7}}]}]}
        findings, checked = trivy_config.parse(report)
        self.assertEqual(checked, 27)
        self.assertEqual(findings[0]["where"], "Dockerfile:7")
        self.assertEqual(findings[0]["severity"], "HIGH")


class HadolintTest(unittest.TestCase):
    def test_levels_map_to_severities(self):
        findings = hadolint.parse([{"code": "DL3007", "level": "warning", "line": 3, "file": "Dockerfile", "message": "latest tag"},
                                   {"code": "DL3059", "level": "info", "line": 9, "file": "Dockerfile", "message": "consolidate"}])
        self.assertEqual([f["severity"] for f in findings], ["MEDIUM", "LOW"])
        self.assertEqual(findings[0]["where"], "Dockerfile:3")


class PinsTest(unittest.TestCase):
    def test_every_tool_is_pinned_for_the_ci_platform_with_sha256(self):
        for name in common.VERSIONS:
            asset, digest = common.ASSETS[(name, "linux-x86_64")]
            if version_in_name := re.search(r"\d+\.\d+\.\d+", asset):   # у hadolint версии в имени ассета нет, она в пути релиза
                self.assertEqual(version_in_name.group(0), common.VERSIONS[name])
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

    def test_every_layer_reports_a_tool_version(self):
        for layer in ("gitleaks", "hadolint", "trivy-config", "trivy-image", "sbom"):
            self.assertRegex(common.layer_version(layer), r"^\d+\.\d+\.\d+$", layer)

    def test_severity_normalisation(self):
        self.assertEqual(common.severity("warning"), "MEDIUM")
        self.assertEqual(common.severity("Critical"), "CRITICAL")
        self.assertEqual(common.severity(None), "UNKNOWN")

    def test_platform_key_shape(self):
        self.assertRegex(common.platform_key(), r"^(linux|darwin)-(x86_64|aarch64|arm64)$")


if __name__ == "__main__":
    unittest.main()
