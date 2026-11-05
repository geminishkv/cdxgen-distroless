"""Тесты релизных скриптов: CHANGELOG, шаблоны заметок и описания Docker Hub, SBOM из реестра, Release с вложениями; сеть - только localhost."""
import contextlib
import hashlib
import http.server
import io
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dockerhub_description  # noqa: E402
import release_notes  # noqa: E402
import release_sbom  # noqa: E402
import release_summary  # noqa: E402
import release_version  # noqa: E402

CHANGELOG = "# Changelog\n\n## [Unreleased]\n\n## [2.0.0] - 2026-02-01\n\n- второй\n\n## [1.0.0] - 2026-01-01\n\n- первый\n  с переносом\n"
DIGEST = "sha256:" + "a" * 64
DOCKERFILE = "".join(f"ARG {name}_IMAGE={ref}@sha256:{str(n) * 64}\n" for n, (name, ref) in enumerate((
    ("BUILD", "docker.io/library/node:24-alpine"), ("UV", "ghcr.io/astral-sh/uv:0.9.9"),
    ("PYTHON", "docker.io/library/python:3.12-slim"), ("BASE", "gcr.io/distroless/nodejs24-debian13:nonroot"))))
LABEL = 'LABEL org.opencontainers.image.description="short text" \\\n'
FILES = [(Path("docs/diagrams/image.svg"), "image/svg+xml", "схема"), (Path("out/bom-linux-amd64.spdx.json"), "application/json", "SBOM")]


def spdx(version="1.0.0", packages=None):
    return {"SPDX": {"spdxVersion": "SPDX-2.3",
                     "packages": [{"name": "@cyclonedx/cdxgen", "versionInfo": version}] if packages is None else packages}}


class ChangelogTest(unittest.TestCase):
    def test_section_is_cut_at_the_next_heading(self):
        self.assertEqual(release_notes.changelog_section(CHANGELOG, "2.0.0"), "- второй")
        self.assertEqual(release_notes.changelog_section(CHANGELOG, "1.0.0"), "- первый\n  с переносом")

    def test_subsections_stay_inside_the_section(self):
        text = "## [1.0.0]\n\n### Добавлено\n\n- a\n\n### Безопасность\n\n- b\n\n## [0.9.0]\n\n- c\n"
        self.assertEqual(release_notes.changelog_section(text, "1.0.0"), "### Добавлено\n\n- a\n\n### Безопасность\n\n- b")

    def test_missing_or_empty_section_is_an_error(self):
        self.assertEqual(release_notes.changelog_section(CHANGELOG, "3.0.0"), "")
        for version in ("3.0.0", "Unreleased"):
            with self.assertRaises(SystemExit):
                release_notes.notes(version, DIGEST, CHANGELOG, DOCKERFILE, FILES)

    def test_version_is_matched_literally(self):
        self.assertEqual(release_notes.changelog_section("## [1.0.0]\n\n- a\n", "1x0y0"), "")


class VersionTest(unittest.TestCase):
    def check(self, ref_type, ref, changelog=CHANGELOG):
        return release_version.problem("1.0.0", ref_type, ref, "main", changelog)

    def test_tag_must_match_version_and_a_filled_changelog_section(self):
        self.assertEqual(self.check("tag", "v1.0.0"), "")
        self.assertIn("не совпадает", self.check("tag", "v1.0.1"))
        self.assertIn("CHANGELOG", self.check("tag", "v1.0.0", "## [Unreleased]\n\n### [1.0.0]\n\n- x\n"))
        self.assertIn("CHANGELOG", self.check("tag", "v1.0.0", "## [1.0.0] - 2026-01-01\n\n## [0.9.0]\n\n- x\n"))

    def test_manual_run_is_allowed_only_from_the_default_branch(self):
        self.assertEqual(self.check("branch", "main"), "")
        self.assertIn("только с ветки main", self.check("branch", "feature/x"))
        self.assertEqual(self.check("", ""), "")

    def test_preflight_renders_both_texts_before_the_build(self):
        release_version.preflight("1.0.0", CHANGELOG, DOCKERFILE + LABEL)
        for dockerfile in (DOCKERFILE, DOCKERFILE.replace("nodejs24", "node") + LABEL):
            with self.assertRaises(SystemExit):
                release_version.preflight("1.0.0", CHANGELOG, dockerfile)
        with mock.patch.object(release_summary, "IMAGES", ("index.docker.io/owner/repo", "ghcr.io/owner/repo")), self.assertRaises(SystemExit):
            release_version.preflight("1.0.0", CHANGELOG, DOCKERFILE + LABEL)

    def test_repository_files_pass_the_preflight(self):
        root = release_notes.ROOT
        release_version.preflight(release_notes.package_version(), (root / "CHANGELOG.md").read_text(encoding="utf-8"),
                                  (root / "Dockerfile").read_text(encoding="utf-8"))


class TemplateTest(unittest.TestCase):
    def test_fill_substitutes_once(self):
        self.assertEqual(release_notes.fill("a %%X%% b %%X%%", {"X": "%%Y%%"}), "a %%Y%% b %%Y%%")

    def test_unknown_malformed_and_unpaired_names_are_errors(self):
        for template in ("%%MISSING%%", "%%x%%", "%% X %%", "%%X2%%", "%%X%% и %%", "%%X\n%%"):
            with self.assertRaises(SystemExit):
                release_notes.fill(template, {"X": "1"})

    def test_components_come_from_pinned_dockerfile_args(self):
        for dockerfile in (DOCKERFILE, DOCKERFILE.replace("_IMAGE=", '_IMAGE="').replace("\n", '"\n')):
            table = release_notes.components(dockerfile, "1.0.0")
            self.assertIn("| cdxgen | 1.0.0 |", table)
            self.assertIn(f"| Node.js | 24 | `gcr.io/distroless/nodejs24-debian13:nonroot@sha256:{'3' * 64}` |", table)
            self.assertIn(f"| uv | 0.9.9 | `ghcr.io/astral-sh/uv:0.9.9@sha256:{'1' * 64}` |", table)
            self.assertIn("| Python, только stdlib | 3.12 |", table)

    def test_unpinned_or_renamed_base_is_an_error(self):
        for broken in (DOCKERFILE.replace(f"@sha256:{'1' * 64}", ""), DOCKERFILE.replace("nodejs24", "node"),
                       DOCKERFILE.replace("ARG PYTHON_IMAGE", "ARG PY_IMG")):
            with self.assertRaises(SystemExit):
                release_notes.components(broken, "1.0.0")

    def test_repository_dockerfile_is_parsed(self):
        version = release_notes.package_version()
        self.assertIn(f"| cdxgen | {version} |", release_notes.components((release_notes.ROOT / "Dockerfile").read_text(encoding="utf-8"), version))


class NotesTest(unittest.TestCase):
    def test_notes_carry_changelog_images_verification_and_assets(self):
        body = release_notes.notes("1.0.0", DIGEST, CHANGELOG, DOCKERFILE, FILES)
        self.assertTrue(body.startswith("Образ генератора SBOM"))
        self.assertIn("## Изменения\n\n- первый\n  с переносом\n\n## Образ", body)
        self.assertNotIn("- второй", body)
        for image in release_summary.IMAGES:
            self.assertIn(f"`{image}@{DIGEST}`", body)
        self.assertIn(f"cosign verify {release_summary.IMAGES[1]}@{DIGEST}", body)
        self.assertIn(r"/\.github/workflows/release\.yml@refs/'", body)
        self.assertIn("/v1.0.0/docs/diagrams/image.svg)", body)
        self.assertIn(f"| [`image.svg`](https://github.com/{release_summary.REPOSITORY}/releases/download/v1.0.0/image.svg) | схема |", body)
        self.assertIn("bom-linux-amd64.spdx.json) | SBOM |", body)
        self.assertNotIn("%%", body)

    def test_changelog_text_is_not_expanded_as_a_template(self):
        body = release_notes.notes("1.0.0", DIGEST, "## [1.0.0]\n\n- текст %%DIGEST%% и %%NOPE%%\n", DOCKERFILE, FILES)
        self.assertIn("- текст %%DIGEST%% и %%NOPE%%", body)

    def test_run_url_points_to_the_release_run(self):
        with mock.patch.dict(os.environ, {"GITHUB_RUN_ID": "42"}):
            self.assertIn(f"https://github.com/{release_summary.REPOSITORY}/actions/runs/42)", release_notes.notes("1.0.0", DIGEST, CHANGELOG, DOCKERFILE, FILES))

    def test_platforms_follow_the_configuration(self):
        for platforms, text in (("linux/amd64,linux/arm64", "платформы `linux/amd64` и `linux/arm64`."), ("linux/amd64", "платформы `linux/amd64`."),
                                ("linux/amd64, linux/arm64 ,linux/arm/v7", "платформы `linux/amd64`, `linux/arm64` и `linux/arm/v7`.")):
            with mock.patch.object(release_summary, "PLATFORMS", platforms):
                self.assertIn(text, release_notes.notes("1.0.0", DIGEST, CHANGELOG, DOCKERFILE, FILES))

    def test_empty_version_or_malformed_digest_is_an_error(self):
        for version, digest in (("", DIGEST), ("1.0.0", ""), ("1.0.0", "sha256:abc"), ("1.0.0", DIGEST.upper())):
            with self.assertRaises(SystemExit):
                release_notes.values(version, digest, DOCKERFILE)


class SbomTest(unittest.TestCase):
    def test_platform_list_ignores_spaces_and_rejects_empty_or_malformed(self):
        self.assertEqual(release_sbom.platforms(" linux/amd64, linux/arm64 ,"), ["linux/amd64", "linux/arm64"])
        for raw in ("", " , ", "linux", "linux/amd64 linux/arm64"):
            with self.assertRaises(SystemExit):
                release_sbom.platforms(raw)

    def test_documents_are_split_by_platform(self):
        raw = json.dumps({"linux/amd64": spdx(), "linux/arm64": spdx()})
        self.assertEqual(sorted(release_sbom.documents(raw, ["linux/amd64", "linux/arm64"], "1.0.0")), ["linux/amd64", "linux/arm64"])

    def test_single_platform_image_has_no_platform_key(self):
        self.assertEqual(list(release_sbom.documents(json.dumps(spdx()), ["linux/amd64"], "1.0.0")), ["linux/amd64"])

    def test_missing_platform_empty_or_foreign_sbom_is_an_error(self):
        for data in ({}, {"linux/amd64": spdx()}, {"linux/amd64": spdx(), "linux/arm64": spdx(packages=[])},
                     {"linux/amd64": spdx(), "linux/arm64": spdx(version="0.9.0")}, {"linux/amd64": spdx(), "linux/arm64": None},
                     spdx(), None, []):
            with self.assertRaises(SystemExit):
                release_sbom.documents(json.dumps(data), ["linux/amd64", "linux/arm64"], "1.0.0")
        with self.assertRaises(SystemExit):
            release_sbom.documents("not json", ["linux/amd64"], "1.0.0")

    def test_file_name_carries_version_and_platform(self):
        self.assertEqual(release_sbom.path("1.0.0", "linux/arm/v7").name, "cdxgen-distroless-1.0.0-linux-arm-v7.spdx.json")


class AttachmentsTest(unittest.TestCase):
    def test_diagrams_and_one_sbom_per_configured_platform(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(release_sbom, "OUT", Path(tmp)), \
                mock.patch.object(release_summary, "PLATFORMS", "linux/amd64,linux/arm64"):
            preview = release_notes.attachments("1.0.0", require=False)
            self.assertEqual([file.name for file, _, _ in preview], ["image.svg", "security.svg", "delivery.svg",
                             "cdxgen-distroless-1.0.0-linux-amd64.spdx.json", "cdxgen-distroless-1.0.0-linux-arm64.spdx.json"])
            self.assertEqual(preview[-1][1:], ("application/json", "SBOM образа linux/arm64, SPDX"))
            with self.assertRaises(SystemExit):
                release_notes.attachments("1.0.0")
            release_sbom.path("1.0.0", "linux/amd64").write_text("{}", encoding="utf-8")
            release_sbom.path("1.0.0", "linux/arm64").write_text("", encoding="utf-8")
            (Path(tmp) / "cdxgen-distroless-1.0.0-linux-amd64 2.spdx.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(SystemExit):
                release_notes.attachments("1.0.0")
            release_sbom.path("1.0.0", "linux/arm64").write_text("{}", encoding="utf-8")
            self.assertEqual(release_notes.attachments("1.0.0"), preview)


class PublishTest(unittest.TestCase):
    RELEASE = {"id": 7, "upload_url": "https://uploads.example.invalid/releases/7/assets{?name,label}", "assets": [],
               "tag_name": "v1.0.0", "html_url": "https://example.invalid/release"}

    def run_publish(self, pages, release=None):
        calls = []

        def api(method, url, body=None, content_type="application/json"):
            calls.append((method, url.split("example.invalid")[-1] if "example.invalid" in url else url.rsplit("/releases", 1)[1],
                          body, content_type))
            if method == "GET":
                return pages[int(url.rsplit("page=", 1)[1]) - 1]
            return release or self.RELEASE
        with tempfile.TemporaryDirectory() as tmp:
            files = [(Path(tmp) / "image.svg", "image/svg+xml", ""), (Path(tmp) / "bom file.json", "application/json", "")]
            for file, _, _ in files:
                file.write_bytes(file.name.encode())
            with contextlib.redirect_stdout(io.StringIO()):
                url = release_notes.publish("owner/repo", "v1.0.0", "name", "text", files, api)
        self.assertEqual(url, "https://example.invalid/release")
        return calls

    def test_new_tag_gets_a_draft_then_assets_then_publication(self):
        self.assertEqual(self.run_publish([[]]), [
            ("GET", "?per_page=100&page=1", None, "application/json"),
            ("POST", "", {"tag_name": "v1.0.0", "name": "name", "body": "text", "draft": True}, "application/json"),
            ("POST", "/releases/7/assets?name=image.svg", b"image.svg", "image/svg+xml"),
            ("POST", "/releases/7/assets?name=bom%20file.json", b"bom file.json", "application/json"),
            ("PATCH", "/7", {"draft": False}, "application/json")])

    def test_existing_release_keeps_identical_assets_and_replaces_changed_ones(self):
        same = f"sha256:{hashlib.sha256(b'image.svg').hexdigest()}"
        existing = {**self.RELEASE, "assets": [{"name": "image.svg", "id": 11, "digest": same}, {"name": "bom file.json", "id": 12, "digest": "sha256:old"},
                                               {"name": "other.txt", "id": 13}]}
        calls = self.run_publish([[{"tag_name": "v0.9.0", "id": 1}, existing]], existing)
        self.assertEqual([call[:2] for call in calls], [
            ("GET", "?per_page=100&page=1"), ("PATCH", "/7"), ("DELETE", "/assets/12"),
            ("POST", "/releases/7/assets?name=bom%20file.json"), ("PATCH", "/7")])
        self.assertEqual(calls[1][2], {"name": "name", "body": "text"})

    def test_asset_without_a_digest_is_replaced(self):
        existing = {**self.RELEASE, "assets": [{"name": "image.svg", "id": 11}]}
        self.assertIn(("DELETE", "/assets/11"), [call[:2] for call in self.run_publish([[existing]], existing)])

    def test_release_is_found_beyond_the_first_page(self):
        calls = self.run_publish([[{"tag_name": f"v0.0.{n}", "id": n} for n in range(100)], [self.RELEASE]])
        self.assertEqual([call[:2] for call in calls][:3], [("GET", "?per_page=100&page=1"), ("GET", "?per_page=100&page=2"), ("PATCH", "/7")])

    def test_several_releases_of_one_tag_stop_the_run(self):
        with self.assertRaises(SystemExit) as stop:
            self.run_publish([[{**self.RELEASE, "draft": True}, {**self.RELEASE, "id": 8}]])
        self.assertIn("7 (черновик), 8 (опубликован)", str(stop.exception))


class Handler(http.server.BaseHTTPRequestHandler):
    seen = []

    def reply(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        Handler.seen.append((self.command, self.path, self.headers.get("Authorization"), self.headers.get("Content-Type"), body))
        status = 422 if self.path == "/fail" else 403 if "forbidden" in self.path else 204 if self.command == "DELETE" else 200
        payload = b"" if status == 204 else b"<html>" if self.path == "/notjson" else json.dumps({"ok": self.path}).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PATCH = do_DELETE = reply

    def log_message(self, *args):
        pass


class LocalServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        with socket.socket() as closed:
            closed.bind(("127.0.0.1", 0))
            cls.dead = f"http://127.0.0.1:{closed.getsockname()[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Handler.seen.clear()

    def patch(self, *args):
        patcher = mock.patch.object(*args) if len(args) == 3 else mock.patch.dict(*args)
        patcher.start()
        self.addCleanup(patcher.stop)


class GithubApiTest(LocalServer):
    def setUp(self):
        super().setUp()
        self.patch(os.environ, {"GITHUB_TOKEN": "token-for-test"})
        self.patch(release_notes, "HOSTS", (f"{self.base}/", f"{self.dead}/"))

    def test_json_bytes_and_empty_responses(self):
        self.assertEqual(release_notes.github("POST", f"{self.base}/json", {"a": "я"}), {"ok": "/json"})
        self.assertEqual(release_notes.github("POST", f"{self.base}/upload?name=x.svg", b"<svg/>", "image/svg+xml"), {"ok": "/upload?name=x.svg"})
        self.assertIsNone(release_notes.github("DELETE", f"{self.base}/assets/1"))
        self.assertEqual(Handler.seen, [
            ("POST", "/json", "Bearer token-for-test", "application/json", json.dumps({"a": "я"}).encode()),
            ("POST", "/upload?name=x.svg", "Bearer token-for-test", "image/svg+xml", b"<svg/>"),
            ("DELETE", "/assets/1", "Bearer token-for-test", "application/json", b"")])

    def test_failures_stop_with_a_message_and_without_the_token(self):
        for url, expected in ((f"{self.base}/fail", "422"), (f"{self.base}/notjson", "нет разборчивого ответа"), (f"{self.dead}/x", "нет разборчивого ответа")):
            with self.assertRaises(SystemExit) as stop:
                release_notes.github("GET", url)
            self.assertIn(expected, str(stop.exception))
            self.assertIn(url, str(stop.exception))
            self.assertNotIn("token-for-test", str(stop.exception))

    def test_addresses_outside_the_allowlist_are_not_opened(self):
        with mock.patch.object(release_notes, "HOSTS", ("https://api.github.com/", "https://uploads.github.com/")):
            for url in ("file:///etc/hostname", f"{self.base}/json", "https://api.github.com.example.invalid/x", "http://api.github.com/x"):
                with self.assertRaises(SystemExit) as stop:
                    release_notes.github("GET", url)
                self.assertIn("вне списка разрешённых", str(stop.exception))
        self.assertEqual(Handler.seen, [])


class DockerHubTest(unittest.TestCase):
    def test_short_description_is_the_image_label_within_the_limit(self):
        self.assertEqual(dockerhub_description.short(LABEL), "short text")
        for broken in ("LABEL other=1\n", LABEL.replace("short text", "x" * 101), LABEL.replace("short text", "я" * 51),
                       LABEL.replace("short text", 'say \\"hi\\"')):
            with self.assertRaises(SystemExit):
                dockerhub_description.short(broken)
        self.assertTrue(dockerhub_description.short((release_notes.ROOT / "Dockerfile").read_text(encoding="utf-8")))

    def test_repository_comes_from_the_docker_hub_image_address(self):
        for image, expected in (("docker.io/owner/repo", "owner/repo"), ("owner/re.po-x_y", "owner/re.po-x_y")):
            with mock.patch.object(release_summary, "IMAGES", (image, "")):
                self.assertEqual(dockerhub_description.repository(), expected)
        for image in ("index.docker.io/owner/repo", "docker.io/owner/repo:1.0", "Docker.io/owner/repo", "docker.io/repo", ""):
            with mock.patch.object(release_summary, "IMAGES", (image, "")), self.assertRaises(SystemExit):
                dockerhub_description.repository()

    def test_overview_is_rendered_from_the_template_within_the_limit(self):
        text = dockerhub_description.overview("1.0.0", DIGEST, DOCKERFILE)
        self.assertTrue(text.startswith("# cdxgen-distroless\n"))
        self.assertIn("| `1.0.0`, `latest` | текущий выпуск: cdxgen 1.0.0, `linux/amd64` и `linux/arm64` |", text)
        self.assertIn(f"docker pull {release_summary.IMAGES[0]}@{DIGEST}", text)
        self.assertIn(f"https://github.com/{release_summary.REPOSITORY}/releases/tag/v1.0.0", text)
        self.assertNotIn("%%", text)
        with mock.patch.object(dockerhub_description, "FULL_LIMIT", 100), self.assertRaises(SystemExit):
            dockerhub_description.overview("1.0.0", DIGEST, DOCKERFILE)

    def test_publish_logs_in_then_patches_the_repository(self):
        calls = []

        def api(method, path, body, token=""):
            calls.append((method, path, body, token))
            return {"access_token": "jwt"}
        dockerhub_description.publish("owner/repo", "user", "secret", "short", "full", api)
        self.assertEqual(calls, [("POST", "/auth/token", {"identifier": "user", "secret": "secret"}, ""),
                                 ("PATCH", "/repositories/owner/repo", {"description": "short", "full_description": "full"}, "jwt")])

    def test_login_without_a_token_in_the_response_stops_before_the_patch(self):
        calls = []
        with self.assertRaises(SystemExit):
            dockerhub_description.publish("owner/repo", "user", "secret", "short", "full", lambda *args: calls.append(args) or {})
        self.assertEqual(len(calls), 1)


class DockerHubApiTest(LocalServer):
    def setUp(self):
        super().setUp()
        self.patch(dockerhub_description, "HUB", self.base)

    def test_login_and_patch_send_json_and_the_bearer_token(self):
        self.assertEqual(dockerhub_description.hub("POST", "/auth/token", {"identifier": "user", "secret": "s3cret"}), {"ok": "/auth/token"})
        self.assertEqual(dockerhub_description.hub("PATCH", "/repositories/o/r", {"description": "я"}, "jwt"), {"ok": "/repositories/o/r"})
        self.assertEqual([(seen[0], seen[2], seen[3]) for seen in Handler.seen],
                         [("POST", None, "application/json"), ("PATCH", "Bearer jwt", "application/json")])
        self.assertEqual(json.loads(Handler.seen[1][4]), {"description": "я"})

    def test_failures_name_the_cause_but_not_the_credentials(self):
        with self.assertRaises(SystemExit) as stop:
            dockerhub_description.hub("PATCH", "/repositories/forbidden/r", {"full_description": "x"}, "jwt-value")
        self.assertIn("403", str(stop.exception))
        self.assertIn("Read, Write, Delete", str(stop.exception))
        self.assertNotIn("jwt-value", str(stop.exception))
        for path, expected in (("/fail", "422"), ("/notjson", "нет разборчивого ответа")):
            with self.assertRaises(SystemExit) as stop:
                dockerhub_description.hub("POST", path, {"identifier": "user", "secret": "s3cret"})
            self.assertIn(expected, str(stop.exception))
            self.assertNotIn("s3cret", str(stop.exception))
            self.assertNotIn("Read, Write, Delete", str(stop.exception))
        with mock.patch.object(dockerhub_description, "HUB", self.dead), self.assertRaises(SystemExit) as stop:
            dockerhub_description.hub("POST", "/auth/token", {"identifier": "user", "secret": "s3cret"})
        self.assertNotIn("s3cret", str(stop.exception))


if __name__ == "__main__":
    unittest.main()
