"""Сводка пайплайна: один markdown в GITHUB_STEP_SUMMARY и в комментарий PR (обновляемый), вердикт гейта.

    python3 scripts/security/report.py render --results '<json needs>' [--pr-comment true]   — сводка (и комментарий в PR)
    python3 scripts/security/report.py gate   --results '<json needs>'               — код 1, если гейтящий слой не success

Сводки слоёв — <OUT>/<tool>.json (артефакты job'ов). Рейтинг — только по новым находкам: E есть critical;
D high > 5; C high 1–5 или medium > 10; B есть medium; A ничего из этого. Эмодзи — только здесь: ✅ ❌ 🔴 🟠 🟡 ⚪ 🟢."""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

import common

GATING = ("gitleaks", "hadolint", "trivy-config", "trivy-image")
REPORT_ONLY = ("sbom",)
MARKER = "<!-- security-report -->"
BOT = "github-actions[bot]"
COUNTS = "<!-- security-counts:"
CIRCLE = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}
MAX_ROWS = 25


def load_layers(out: Path) -> dict[str, dict]:
    layers = {}
    for path in sorted(out.glob("*.json")):
        if path.name.endswith(".raw.json") or path.name.startswith("sbom-"):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "tool" in data:
            layers[data["tool"]] = data
    return layers


def new_counts(layers: dict[str, dict]) -> dict[str, int]:
    counts = dict.fromkeys(CIRCLE, 0)
    for layer in layers.values():
        for f in layer.get("findings", []):
            if f.get("status", "new") == "new":  # UNKNOWN считается как low, иначе итог расходится с таблицей по инструментам
                counts[f["severity"] if f["severity"] in counts else "LOW"] += 1
    return counts


def rating(counts: dict[str, int]) -> str:
    if counts["CRITICAL"]:
        return "E"
    if counts["HIGH"] > 5:
        return "D"
    if counts["HIGH"] or counts["MEDIUM"] > 10:
        return "C"
    if counts["MEDIUM"]:
        return "B"
    return "A"


def scale(counts: dict[str, int], width: int = 12) -> str:
    """Полоса из width кружков: доля пропорциональна числу, ненулевая критичность — минимум один кружок."""
    total = sum(counts.values())
    if not total:
        return ""
    cells = {s: (1 if n else 0) for s, n in counts.items()}
    rest = width - sum(cells.values())
    extra = {s: (n / total) * rest for s, n in counts.items() if n}
    for s in sorted(extra, key=lambda k: extra[k] - int(extra[k]), reverse=True):
        cells[s] += int(extra[s])
    for s in sorted(extra, key=lambda k: extra[k] - int(extra[k]), reverse=True):
        if sum(cells.values()) >= width:
            break
        cells[s] += 1
    return "".join(CIRCLE[s] * cells[s] for s in CIRCLE)


def previous_counts(body: str) -> dict[str, dict[str, int]]:
    """Счётчики прошлого комментария: {слой: {"new": n}}; битый или подменённый маркер даёт пусто."""
    m = re.search(re.escape(COUNTS) + r"(\{.*?\}) -->", body or "", re.S)
    try:
        data = json.loads(m.group(1)) if m else {}
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {name: {"new": value["new"]} for name, value in data.items() if isinstance(value, dict) and isinstance(value.get("new"), int)}


def gate_failed(results: dict[str, dict]) -> list[str]:
    """Гейтящие слои, чей job не success: failure, cancelled, skipped и отсутствующий — одинаково отказ."""
    return [n for n in GATING if (results.get(n) or {}).get("result") != "success"]


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render(layers: dict[str, dict], results: dict[str, dict], previous: dict[str, dict[str, int]] | None = None) -> str:
    """previous — счётчики прошлого комментария в PR; без него (сводка job'а, первый комментарий) дельта не печатается."""
    status = {name: (results.get(name) or {}).get("result", "skipped") for name in (*GATING, *REPORT_ONLY)}
    failed = gate_failed(results)
    counts = new_counts(layers)
    total_new = sum(counts.values())
    per_tool = {name: {"new": 0, "false_positive": 0, "accepted": 0} for name in layers}
    for name, layer in layers.items():
        for f in layer.get("findings", []):
            per_tool[name][f.get("status", "new") if f.get("status", "new") in per_tool[name] else "new"] += 1
    delta = ""
    if previous is not None:
        diff = total_new - sum(v["new"] for n, v in previous.items() if n in per_tool)
        delta = f" ({'+' if diff > 0 else ''}{diff} к прошлому прогону)"
    reviewed = sum(v["false_positive"] + v["accepted"] for v in per_tool.values())
    mark = {"success": "✅ success", "failure": "❌ failure"}
    lines = [MARKER, "## Пайплайн безопасности",
             "### ✅ Гейт: пройден" if not failed else f"### ❌ Гейт: не пройден — {', '.join(failed)}", "",
             "| Слой | Результат |", "| --- | --- |"]
    lines += [f"| {n} | {mark.get(status[n], '⚪ ' + status[n])} |" for n in (*GATING, *REPORT_ONLY)]
    if failed:
        lines += ["", "Слой, который не прошёл, находок не сообщает — счётчики ниже неполны, пока он не починен."]
    lines += ["", f"**Рейтинг {rating(counts)}** · новых {total_new}{delta} · разобрано {reviewed} · всего {total_new + reviewed}"]
    if total_new:
        lines += [scale(counts)]
    bold = lambda n: f"**{n}**" if n else str(n)  # noqa: E731
    lines += [f"Новые находки по критичности: 🔴 critical {bold(counts['CRITICAL'])} · 🟠 high {bold(counts['HIGH'])} · "
              f"🟡 medium {bold(counts['MEDIUM'])} · ⚪ low {bold(counts['LOW'])} · Σ {total_new}", "",
              "| Инструмент | Новых | Ложных | Принятых | Всего |", "| --- | ---: | ---: | ---: | ---: |"]
    lines += [f"| {n} | {v['new']} | {v['false_positive']} | {v['accepted']} | {sum(v.values())} |" for n, v in per_tool.items()]
    lines += ["", "### Новые находки", ""]
    rows = [(f, n) for n, layer in layers.items() for f in layer.get("findings", []) if f.get("status", "new") == "new"]
    rows.sort(key=lambda r: common.SEVERITIES.index(r[0]["severity"]))
    if rows:
        lines += ["| Крит. | Инструмент | ID | Где | Что делать |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| {CIRCLE.get(f['severity'], '⚪')} {f['severity']} | {n} | {cell(f['id'])} | {cell(f['where'])} | {cell(f['fix'])} |" for f, n in rows[:MAX_ROWS]]
        if len(rows) > MAX_ROWS:
            lines += ["", f"ещё {len(rows) - MAX_ROWS} — в артефактах security-*"]
    else:
        lines += ["🟢 Новых находок нет." + (" Всё перечисленное записано в файлах подавлений." if reviewed else "")]
    lines += ["", "### Покрытие", "", "| Инструмент | Проверено |", "| --- | --- |"]
    lines += [f"| {n} {layer.get('version', '')} | {', '.join(f'{k} {v}' for k, v in layer.get('coverage', {}).items())} |" for n, layer in layers.items()]
    if reviewed:
        lines += ["", "### Разобрано", "", "| Решение | Количество |", "| --- | ---: |",
                  f"| ложное срабатывание | {sum(v['false_positive'] for v in per_tool.values())} |",
                  f"| принято (baseline .trivyignore.yaml) | {sum(v['accepted'] for v in per_tool.values())} |"]
    lines += ["", "Подробности — артефакты `security-*` прогона; baseline — `.trivyignore.yaml`.",
              f"{COUNTS}{json.dumps({n: {'new': v['new']} for n, v in per_tool.items()})} -->"]
    return "\n".join(lines) + "\n"


def github(method: str, url: str, body: dict | None = None) -> object:
    token = os.environ.get("GITHUB_TOKEN") or common.die("нет GITHUB_TOKEN для комментария")
    request = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                              "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 — только api.github.com
        return json.loads(response.read() or b"null")


def comment(layers: dict[str, dict], results: dict[str, dict], api=github) -> None:
    """Один комментарий бота на PR: ищется по маркеру среди комментариев самого бота и обновляется, дельта — из его
    прошлых счётчиков. Токен только на чтение (PR из форка, Dependabot) — не отказ: сводка уже в GITHUB_STEP_SUMMARY."""
    repo = os.environ["GITHUB_REPOSITORY"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    number = (event.get("pull_request") or {}).get("number") or (event.get("issue") or {}).get("number")
    if not number:
        print("не pull request — комментарий не нужен")
        return
    base = f"https://api.github.com/repos/{repo}"
    mine = [c for c in api("GET", f"{base}/issues/{number}/comments?per_page=100")
            if (c.get("user") or {}).get("login") == BOT and (c.get("body") or "").startswith(MARKER)]
    body = render(layers, results, previous_counts(mine[0]["body"]) if mine else None)
    try:
        if mine:
            api("PATCH", f"{base}/issues/comments/{mine[0]['id']}", {"body": body})
            print(f"комментарий обновлён: {mine[0]['html_url']}")
        else:
            print(f"комментарий создан: {api('POST', f'{base}/issues/{number}/comments', {'body': body})['html_url']}")
    except urllib.error.HTTPError as error:
        if error.code != 403:
            raise
        error.close()
        print(("::notice::" if os.environ.get("GITHUB_ACTIONS") else "") + "комментарий в PR не записан: у токена нет права записи "
              "(PR из форка или от Dependabot); сводка — в GITHUB_STEP_SUMMARY")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["render", "gate"])
    parser.add_argument("--results", default="{}", help="JSON контекста needs: {job: {result: ...}}")
    parser.add_argument("--pr-comment", default="false", help="render: true — ещё и комментарий в PR (upsert по маркеру)")
    args = parser.parse_args()
    results = json.loads(args.results)
    if args.command == "gate":
        failed = gate_failed(results)
        print("гейт: пройден" if not failed else f"гейт: не пройден — {', '.join(failed)}")
        return 1 if failed else 0
    layers = load_layers(common.OUT)
    if not layers:
        common.die(f"в {common.OUT} нет сводок слоёв — артефакты не скачаны")
    markdown = render(layers, results)
    print(markdown)
    if summary_path := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary_path).open("a", encoding="utf-8") as fh:
            fh.write(markdown)
    if args.pr_comment == "true":
        comment(layers, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
