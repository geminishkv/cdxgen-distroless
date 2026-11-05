"""Тесты сводки: рейтинг, шкала, дельта из прошлого комментария, вердикт гейта, комментарий в PR без сети."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "security"))
import report  # noqa: E402

LAYER = {"tool": "trivy-image", "version": "0.76.1", "status": "success", "coverage": {"packages": 645},
         "findings": [{"severity": "HIGH", "id": "CVE-1", "where": "zlib1g (debian)", "fix": "исправления нет", "status": "new"},
                      {"severity": "MEDIUM", "id": "CVE-2", "where": "glob (node-pkg)", "fix": "обновить до 14.0.2", "status": "new"},
                      {"severity": "LOW", "id": "CVE-3", "where": "x", "fix": "", "status": "accepted"}]}
OK = {n: {"result": "success"} for n in (*report.GATING, *report.REPORT_ONLY)}


class RatingTest(unittest.TestCase):
    def counts(self, **kw):
        return {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, **kw}

    def test_rating_ladder(self):
        self.assertEqual(report.rating(self.counts()), "A")
        self.assertEqual(report.rating(self.counts(LOW=40)), "A")
        self.assertEqual(report.rating(self.counts(MEDIUM=1)), "B")
        self.assertEqual(report.rating(self.counts(MEDIUM=11)), "C")
        self.assertEqual(report.rating(self.counts(HIGH=1)), "C")
        self.assertEqual(report.rating(self.counts(HIGH=6)), "D")
        self.assertEqual(report.rating(self.counts(CRITICAL=1, LOW=100)), "E")

    def test_scale_is_twelve_cells_with_a_cell_per_nonzero_severity(self):
        bar = report.scale(self.counts(CRITICAL=1, LOW=50))
        self.assertEqual(len(bar), 12)
        self.assertIn("🔴", bar)
        self.assertEqual(report.scale(self.counts()), "")


class RenderTest(unittest.TestCase):
    def test_render_has_verdict_marker_delta_and_counts(self):
        md = report.render({"trivy-image": LAYER}, OK, previous={"trivy-image": {"new": 1}})
        self.assertTrue(md.startswith(report.MARKER))
        self.assertIn("### ✅ Гейт: пройден", md)
        self.assertIn("**Рейтинг C** · новых 2 (+1 к прошлому прогону) · разобрано 1 · всего 3", md)
        self.assertIn('<!-- security-counts:{"trivy-image": {"new": 2}} -->', md)
        self.assertEqual(report.previous_counts(md), {"trivy-image": {"new": 2}})

    def test_failed_layer_is_named_and_counts_marked_incomplete(self):
        md = report.render({"trivy-image": LAYER}, {**OK, "gitleaks": {"result": "failure"}})
        self.assertIn("### ❌ Гейт: не пройден — gitleaks", md)
        self.assertIn("счётчики ниже неполны", md)

    def test_overflow_note_is_separated_from_the_table(self):
        many = {"tool": "trivy-image", "coverage": {}, "findings": [
            {"severity": "LOW", "id": f"CVE-{i}", "where": "x", "fix": "", "status": "new"} for i in range(report.MAX_ROWS + 2)]}
        lines = report.render({"trivy-image": many}, OK).splitlines()
        note = lines.index("ещё 2 — в артефактах security-*")
        self.assertEqual(lines[note - 1], "")
        self.assertTrue(lines[note - 2].startswith("| "))

    def test_no_new_findings_line(self):
        md = report.render({"hadolint": {"tool": "hadolint", "coverage": {"files": 1}, "findings": []}}, OK)
        self.assertIn("🟢 Новых находок нет", md)
        self.assertNotIn("файлах подавлений", md)
        self.assertIn("**Рейтинг A**", md)

    def test_delta_is_shown_only_against_a_previous_comment(self):
        self.assertNotIn("к прошлому прогону", report.render({"trivy-image": LAYER}, OK))
        self.assertIn("новых 2 (0 к прошлому прогону)", report.render({"trivy-image": LAYER}, OK, previous={"trivy-image": {"new": 2}}))

    def test_unknown_severity_is_counted_once_and_cells_are_escaped(self):
        layer = {"tool": "trivy-image", "coverage": {}, "findings": [{"severity": "UNKNOWN", "id": "X|1", "where": "a", "fix": "", "status": "new"}]}
        first = report.render({"trivy-image": layer}, OK)
        md = report.render({"trivy-image": layer}, OK, previous=report.previous_counts(first))
        self.assertIn("новых 1 (0 к прошлому прогону)", md)
        self.assertIn("X\\|1", md)

    def test_foreign_or_broken_counters_are_ignored(self):
        self.assertEqual(report.previous_counts('<!-- security-counts:{"trivy-image": {"new": "x"}} -->'), {})
        self.assertEqual(report.previous_counts("<!-- security-counts:{oops} -->"), {})


class GateTest(unittest.TestCase):
    def test_gate_fails_closed(self):
        self.assertEqual(report.gate_failed(OK), [])
        self.assertEqual(report.gate_failed({}), list(report.GATING))
        for bad in ("failure", "cancelled", "skipped"):
            self.assertEqual(report.gate_failed({**OK, "hadolint": {"result": bad}}), ["hadolint"])
        self.assertEqual(report.gate_failed({**OK, "sbom": {"result": "failure"}}), [])


class CommentTest(unittest.TestCase):
    def run_comment(self, comments, fail_write=False):
        calls = []

        def api(method, url, body=None):
            calls.append(method)
            if method == "GET":
                return comments
            if fail_write:
                raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)
            return {"html_url": "https://example.invalid/comment"}

        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(json.dumps({"pull_request": {"number": 5}}), encoding="utf-8")
            env = {"GITHUB_REPOSITORY": "owner/repo", "GITHUB_EVENT_PATH": str(event)}
            with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()) as out:
                report.comment({"trivy-image": LAYER}, OK, api)
        return calls, out.getvalue()

    def test_read_only_token_is_reported_but_not_an_error(self):
        calls, out = self.run_comment([], fail_write=True)
        self.assertEqual(calls, ["GET", "POST"])
        self.assertIn("не записан", out)

    def test_only_the_bot_comment_is_updated(self):
        foreign = {"id": 1, "user": {"login": "someone"}, "body": report.MARKER + '\n<!-- security-counts:{"x": {"new": "y"}} -->'}
        calls, _ = self.run_comment([foreign])
        self.assertEqual(calls, ["GET", "POST"])
        mine = {"id": 2, "user": {"login": report.BOT}, "body": report.MARKER, "html_url": "https://example.invalid/comment"}
        calls, _ = self.run_comment([foreign, mine])
        self.assertEqual(calls, ["GET", "PATCH"])


if __name__ == "__main__":
    unittest.main()
