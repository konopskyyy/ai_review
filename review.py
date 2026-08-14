#!/usr/bin/env python3
"""AI Review — bot do przeglądu Merge Requestów w GitLab oparty o opencode.

Przepływ:
  1. Pobiera zmiany MR z API GitLab (diff + diff_refs).
  2. Buduje kontekst review (skille + diff).
  3. Odpala `opencode run` (ten sam model co lokalnie).
  4. Parsuje wynik JSON (komentarze + podsumowanie).
  5. Publikuje inline komentarze i notatkę-podsumowanie na MR.

Zmienne środowiskowe (GitLab CI dostarcza automatycznie):
  GITLAB_TOKEN | CI_JOB_TOKEN  - token do API GitLab (zakres: api)
  CI_API_V4_URL                - np. https://gitlab.com/api/v4
  CI_PROJECT_ID / CI_PROJECT_PATH
  CI_MERGE_REQUEST_IID
  CI_PROJECT_DIR               - katalog z repozytorium (checkout)

Zmienne opcjonalne:
  AI_REVIEW_MODEL            domyślnie "opencode/big-pickle"
  AI_REVIEW_SKILLS           domyślnie "standards,architecture" (rozdzielone przecinkiem)
  AI_REVIEW_FAIL_ON          domyślnie "critical" (none|critical|warning)
  AI_REVIEW_MAX_COMMENTS     domyślnie 25
  AI_REVIEW_MAX_DIFF_CHARS   domyślnie 200000
  AI_REVIEW_DEDUPE           domyślnie false — usuń poprzednie komentarze bota przed publikacją
  AI_REVIEW_APPROVE          domyślnie false — zatwierdź/odrzuć MR na podstawie werdyktu
  AI_REVIEW_LANGUAGE         domyślnie pl
  AI_REVIEW_TITLE            domyślnie "AI Review"
  AI_REVIEW_TIMEOUT_SECONDS  domyślnie 600 (limit czasu na opencode run)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SUMMARY_MARKER = "<!-- ai-review:summary -->"
COMMENT_MARKER = "<!-- ai-review:comment -->"

DEFAULTS = {
    "model": "opencode/big-pickle",
    "skills": "standards,architecture",
    "fail_on": "critical",
    "max_comments": 25,
    "max_diff_chars": 200000,
    "dedupe": False,
    "approve": False,
    "language": "pl",
    "title": "AI Review",
    "timeout": 600,
}


def env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def log(msg: str) -> None:
    print(f"[ai-review] {msg}", file=sys.stderr, flush=True)


def die(msg: str, code: int = 2) -> None:
    log(f"BŁĄD: {msg}")
    sys.exit(code)


def cfg(name: str):
    v = os.environ.get(f"AI_REVIEW_{name.upper()}")
    if v is None or v.strip() == "":
        return DEFAULTS[name]
    v = v.strip()
    if isinstance(DEFAULTS[name], bool):
        return env_bool(f"AI_REVIEW_{name.upper()}", DEFAULTS[name])
    if isinstance(DEFAULTS[name], int):
        try:
            return int(v)
        except ValueError:
            return DEFAULTS[name]
    return v


# --------------------------------------------------------------------------- #
# GitLab API
# --------------------------------------------------------------------------- #

class GitLab:
    def __init__(self, base_url: str, project_id: str, mr_iid: str):
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id
        self.mr_iid = mr_iid
        token = os.environ.get("GITLAB_TOKEN") or os.environ.get("CI_JOB_TOKEN")
        if not token:
            die("Brak tokenu: ustaw GITLAB_TOKEN (zakres 'api') albo polegaj na CI_JOB_TOKEN.")
        if os.environ.get("GITLAB_TOKEN"):
            self.headers = {"PRIVATE-TOKEN": token}
        else:
            self.headers = {"JOB-TOKEN": token}

    def _request(self, method: str, path: str, data=None):
        url = f"{self.base_url}{path}"
        body = None
        headers = dict(self.headers)
        headers["Accept"] = "application/json"
        if data is not None:
            body = urllib.parse.urlencode(data, doseq=True).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                if not raw:
                    return None
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            log(f"API {method} {path} → HTTP {e.code}: {detail[:400]}")
            raise

    def mr_changes(self) -> dict:
        path = f"/projects/{urllib.parse.quote(self.project_id, safe='')}/merge_requests/{self.mr_iid}/changes"
        return self._request("GET", path)

    def list_notes(self) -> list:
        notes = []
        page = 1
        while True:
            path = (
                f"/projects/{urllib.parse.quote(self.project_id, safe='')}"
                f"/merge_requests/{self.mr_iid}/notes?per_page=100&page={page}&sort=asc"
            )
            batch = self._request("GET", path) or []
            notes.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return notes

    def delete_note(self, note_id) -> None:
        path = (
            f"/projects/{urllib.parse.quote(self.project_id, safe='')}"
            f"/merge_requests/{self.mr_iid}/notes/{note_id}"
        )
        self._request("DELETE", path)

    def post_discussion(self, body: str, position: dict) -> int:
        data = {"body": body}
        for k, v in position.items():
            data[f"position[{k}]"] = v
        path = (
            f"/projects/{urllib.parse.quote(self.project_id, safe='')}"
            f"/merge_requests/{self.mr_iid}/discussions"
        )
        resp = self._request("POST", path, data=data) or {}
        return resp.get("notes", [{}])[0].get("id")

    def post_note(self, body: str) -> int:
        path = (
            f"/projects/{urllib.parse.quote(self.project_id, safe='')}"
            f"/merge_requests/{self.mr_iid}/notes"
        )
        resp = self._request("POST", path, data={"body": body}) or {}
        return resp.get("id")

    def approve(self) -> None:
        path = (
            f"/projects/{urllib.parse.quote(self.project_id, safe='')}"
            f"/merge_requests/{self.mr_iid}/approve"
        )
        self._request("POST", path)

    def unapprove(self) -> None:
        path = (
            f"/projects/{urllib.parse.quote(self.project_id, safe='')}"
            f"/merge_requests/{self.mr_iid}/unapprove"
        )
        self._request("POST", path)


# --------------------------------------------------------------------------- #
# Diff / pozycje
# --------------------------------------------------------------------------- #

def added_lines_for(diff: str) -> set[int]:
    """Zwraca zbiór numerów linii (nowa wersja) dodanych w unified diff."""
    lines = set()
    new_line = 0
    for raw in diff.splitlines():
        if raw.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
            new_line = int(m.group(1)) - 1 if m else new_line
            continue
        if not raw:
            continue
        if raw.startswith("+"):
            if raw.startswith("+++"):
                continue
            new_line += 1
            lines.add(new_line)
        elif raw.startswith("-"):
            continue
        elif raw.startswith(r"\ No newline"):
            continue
        elif raw.startswith(" "):
            new_line += 1
    return lines


def build_diff_context(changes: list) -> tuple[str, dict]:
    """Zwraca (tekst diff, mapa path -> zbiór dodanych linii)."""
    parts = []
    line_map: dict[str, set[int]] = {}
    total = 0
    max_chars = int(cfg("max_diff_chars"))
    for ch in changes:
        path = ch.get("new_path") or ch.get("old_path")
        diff = ch.get("diff", "")
        if not path or not diff:
            continue
        parts.append(f"### FILE: {path}\n{diff}")
        line_map[path] = added_lines_for(diff)
        total += len(diff)
    text = "\n\n".join(parts)
    if total > max_chars:
        log(f"Diff przekracza limit {max_chars} znaków ({total}), przycinam.")
        text = text[:max_chars]
        text += "\n\n[UWAGA: diff został przycięty do limitu rozmiaru]"
    return text, line_map


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #

def build_prompt(skills: list[str], diff_path: str, mr_title: str, mr_url: str, lang: str) -> str:
    skill_list = ", ".join(f"`{s}`" for s in skills)
    max_comments = int(cfg("max_comments"))
    if lang == "pl":
        return f"""Jesteś doświadczonym inżynierem prowadzącym rygorystyczny, ale życzliwy przegląd kodu (code review) dla MR: "{mr_title}" ({mr_url}).

KROKI:
1. Za pomocą narzędzia `skill` wczytaj skille: {skill_list}. Zastosuj ich reguły.
2. Przeanalizuj diff dołączony jako plik ({diff_path}). Możesz też czytać pliki w repozytorium, aby zweryfikować kontekst.
3. Zidentyfikuj realne problemy WYŁĄCZNIE dotyczące zmienionych linii. Nie zgłaszaj drobiazgów bez znaczenia. Każde zgłoszenie musi być konkretne, uzasadnione i wykonalne.

FORMAT ODPOWIEDZI (TYLKO JSON, bez żadnego tekstu poza blokiem JSON):
{{
  "summary": {{
    "verdict": "approved" | "changes_requested",
    "title": "krótki tytuł po polsku",
    "body": "pełne podsumowanie w Markdown (po polsku): mocne strony, najważniejsze uwagi, sugestie"
  }},
  "comments": [
    {{
      "path": "ścieżka pliku z diff",
      "new_line": 42,
      "severity": "critical" | "warning" | "info",
      "message": "opis problemu po polsku wraz z konkretną sugestią naprawy",
      "rule": "nazwa_skilla:nazwa_reguly"
    }}
  ]
}}

ZASADY:
- `comments` zgłaszaj tylko dla linii, które faktycznie istnieją po stronie nowej wersji (linie dodane w diff). Podawaj NUMER nowej linii.
- Maksymalnie {max_comments} komentarzy. Priorytet: critical > warning > info.
- `verdict` = "approved" tylko gdy nie ma problemów critical/warning; inaczej "changes_requested".
- Odpowiedz WYŁĄCZNIE obiektem JSON."""
    return f"""You are a senior engineer performing a rigorous but kind code review for MR "{mr_title}" ({mr_url}).

STEPS:
1. Using the `skill` tool, load skills: {skill_list}. Apply their rules.
2. Analyze the diff attached as a file ({diff_path}). You may also read repository files to verify context.
3. Report real issues ONLY on changed lines. Do not nitpick. Each finding must be specific, justified, and actionable.

OUTPUT FORMAT (JSON ONLY, no text outside the JSON block):
{{
  "summary": {{
    "verdict": "approved" | "changes_requested",
    "title": "short summary title",
    "body": "full Markdown summary"
  }},
  "comments": [
    {{
      "path": "file path from the diff",
      "new_line": 42,
      "severity": "critical" | "warning" | "info",
      "message": "issue description with a concrete fix suggestion",
      "rule": "skill_name:rule_name"
    }}
  ]
}}

RULES:
- Only report `comments` for lines that exist in the new version (added lines in the diff). Use the NEW line number.
- At most {max_comments} comments. Priority: critical > warning > info.
- `verdict` = "approved" only when there are no critical/warning issues; otherwise "changes_requested".
- Reply with ONLY the JSON object."""


# --------------------------------------------------------------------------- #
# opencode
# --------------------------------------------------------------------------- #

def setup_opencode_auth(model: str) -> None:
    provider = model.split("/", 1)[0] if "/" in model else model
    key_env = f"{provider.upper().replace('-', '_')}_API_KEY"
    key = os.environ.get(key_env) or os.environ.get("OPENCODE_API_KEY")
    if not key:
        log(f"Brak klucza API dla providera '{provider}' (zmienna {key_env}). "
            "Ustaw AI_REVIEW_MODEL oraz zmienną <PROVIDER>_API_KEY (np. OPENCODE_API_KEY).")
        return
    auth_dir = os.path.expanduser("~/.local/share/opencode")
    os.makedirs(auth_dir, exist_ok=True)
    auth_path = os.path.join(auth_dir, "auth.json")
    auth = {}
    if os.path.exists(auth_path):
        try:
            with open(auth_path, encoding="utf-8") as f:
                auth = json.load(f)
        except (json.JSONDecodeError, OSError):
            auth = {}
    auth[provider] = {"type": "api", "key": key}
    with open(auth_path, "w", encoding="utf-8") as f:
        json.dump(auth, f, indent=2)
    log(f"Zapisano klucz API dla providera '{provider}'.")


def extract_json(text: str) -> dict:
    candidates = [
        r"```json\s*(\{.*?\})\s*```",
        r"```\s*(\{.*?\})\s*```",
        r"(\{.*\})",
    ]
    for pat in candidates:
        m = re.search(pat, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    raise ValueError("Nie udało się sparsować odpowiedzi modelu jako JSON.")


def run_opencode(prompt: str, diff_path: str, model: str, workdir: str) -> str:
    cmd = [
        "opencode", "run",
        "--model", model,
        "--agent", "ai-review",
        "--auto",
        "--file", diff_path,
        "--title", "AI Review",
        prompt,
    ]
    log("Uruchamiam: " + " ".join(cmd))
    env = dict(os.environ)
    env.setdefault("OPENCODE_DISABLE_AUTOUPDATE", "1")
    proc = subprocess.run(
        cmd,
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=int(cfg("timeout")),
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if err:
        log(f"stderr opencode (pierwsze 2000 znaków):\n{err[:2000]}")
    if proc.returncode != 0:
        log(f"opencode zakończył się kodem {proc.returncode}.")
    if not out:
        die(f"opencode nie zwrócił żadnego wyjścia.{('\n' + err[:2000]) if err else ''}")
    return out


# --------------------------------------------------------------------------- #
# Publikacja
# --------------------------------------------------------------------------- #

SEVERITY_EMOJI = {"critical": "🚨", "warning": "⚠️", "info": "💡"}


def format_comment(c: dict, marker: bool = True) -> str:
    sev = c.get("severity", "info")
    icon = SEVERITY_EMOJI.get(sev, "💡")
    parts = [f"{icon} **{sev.upper()}**"]
    rule = c.get("rule")
    if rule:
        parts.append(f"`{rule}`")
    head = " ".join(parts)
    marker_html = f"\n{COMMENT_MARKER}" if marker else ""
    return f"{head}\n\n{c.get('message', '')}{marker_html}"


def post_inline(gitlab: GitLab, comments: list, line_map: dict, diff_refs: dict) -> list:
    """Publikuje inline discussions. Zwraca komentarze, które nie miały ważnej pozycji."""
    pending = []
    base_sha = diff_refs.get("base_sha")
    start_sha = diff_refs.get("start_sha")
    head_sha = diff_refs.get("head_sha")
    if not all([base_sha, start_sha, head_sha]):
        log("Brak diff_refs — nie mogę publikować inline komentarzy.")
        return comments
    for c in comments:
        path = c.get("path")
        line = c.get("new_line")
        valid = path in line_map and isinstance(line, int) and line in line_map[path]
        if not valid:
            log(f"Pominięto inline ({path}:{line}) — linia nie występuje w diffie.")
            pending.append(c)
            continue
        position = {
            "position_type": "text",
            "base_sha": base_sha,
            "start_sha": start_sha,
            "head_sha": head_sha,
            "new_path": path,
            "new_line": line,
        }
        try:
            nid = gitlab.post_discussion(format_comment(c), position)
            log(f"Opublikowano inline komentarz {path}:{line} (note {nid}).")
        except urllib.error.HTTPError as e:
            if e.code == 400:
                log(f"GitLab odrzucił pozycję {path}:{line} — przenoszę do podsumowania.")
                pending.append(c)
            else:
                raise
    return pending


def build_summary(data: dict, comments: list, pending: list, skills: list, model: str) -> str:
    summary = data.get("summary", {})
    verdict = summary.get("verdict", "changes_requested")
    if verdict == "approved":
        verdict_line = "✅ **Werdykt: Akceptuję**"
    else:
        verdict_line = "🔴 **Werdykt: Wymaga poprawek**"

    counts = {"critical": 0, "warning": 0, "info": 0}
    for c in comments:
        counts[c.get("severity", "info")] = counts.get(c.get("severity", "info"), 0) + 1
    counts_str = " | ".join(
        f"{SEVERITY_EMOJI[k]} {k}: {v}" for k, v in counts.items() if v
    ) or "brak zgłoszeń"

    body = summary.get("body", "")
    lines = [
        f"{SUMMARY_MARKER}",
        f"🤖 **{cfg('title')}** — model: `{model}`",
        "",
        verdict_line,
        "",
        f"**Zgłoszenia:** {counts_str}",
        "",
    ]
    if body:
        lines += ["---", "", body, ""]
    if pending:
        lines += [
            "---",
            "### ⚠️ Uwagi bez pozycji inline (linia nie występuje w diffie)",
            "",
        ]
        for p in pending:
            sev = p.get("severity", "info")
            lines.append(f"- {SEVERITY_EMOJI.get(sev, '💡')} **{p.get('path')}** `{sev}`: {p.get('message', '')}")
        lines.append("")
    lines += [
        "---",
        f"_Skille: {', '.join(skills)}_",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #

SAMPLE_DIFF = """diff --git a/src/app.php b/src/app.php
index 111..222 100644
--- a/src/app.php
+++ b/src/app.php
@@ -10,6 +10,8 @@ function run() {
     $x = 1;
-    $y = 2;
+    $y = 3;
+    $z = 4;
 }
"""


def self_test() -> None:
    log("Tryb self-test — sprawdzam parsowanie diffa i budowanie promptu (bez API).")
    changes = [{
        "new_path": "src/app.php",
        "old_path": "src/app.php",
        "diff": SAMPLE_DIFF,
    }]
    text, line_map = build_diff_context(changes)
    assert line_map["src/app.php"] == {11, 12}, line_map
    prompt = build_prompt(["standards", "architecture"], "/tmp/diff.txt", "Test MR", "https://gitlab.test/mr/1", "pl")
    print(json.dumps({"diff": text, "added_lines": sorted(line_map["src/app.php"]), "prompt": prompt}, indent=2, ensure_ascii=False))
    log("Self-test OK.")
    sys.exit(0)


# --------------------------------------------------------------------------- #
# Główny przepływ
# --------------------------------------------------------------------------- #

def main() -> None:
    if "--self-test" in sys.argv:
        self_test()

    required = ["CI_API_V4_URL", "CI_PROJECT_ID", "CI_MERGE_REQUEST_IID", "CI_PROJECT_DIR"]
    missing = [r for r in required if not os.environ.get(r)]
    if missing:
        die("Brak wymaganych zmiennych CI: " + ", ".join(missing) +
            ". Obraz działa w jobie pipeline MR (rules: merge_request_event).")

    source = os.environ.get("CI_PIPELINE_SOURCE", "")
    if source != "merge_request_event" and not env_bool("AI_REVIEW_ALLOW_ANY_PIPELINE", False):
        log("To nie jest pipeline MR (CI_PIPELINE_SOURCE=%s). Kończę bez review." % source)
        sys.exit(0)

    gitlab = GitLab(
        os.environ["CI_API_V4_URL"],
        os.environ["CI_PROJECT_ID"],
        os.environ["CI_MERGE_REQUEST_IID"],
    )

    model = str(cfg("model"))
    skills = [s.strip() for s in str(cfg("skills")).split(",") if s.strip()]
    setup_opencode_auth(model)

    log("Pobieram zmiany MR...")
    changes_resp = gitlab.mr_changes()
    diff_text, line_map = build_diff_context(changes_resp.get("changes", []))
    if not diff_text.strip():
        die("MR nie zawiera żadnych zmian w diffie.")
    diff_refs = changes_resp.get("diff_refs", {}) or {}

    mr_title = changes_resp.get("title", f"MR !{gitlab.mr_iid}")
    project_url = os.environ.get("CI_PROJECT_URL", "")
    mr_url = changes_resp.get("web_url") or f"{project_url}/-/merge_requests/{gitlab.mr_iid}"

    tmp = "/tmp/ai-review"
    os.makedirs(tmp, exist_ok=True)
    diff_path = os.path.join(tmp, "diff.txt")
    with open(diff_path, "w", encoding="utf-8") as f:
        f.write(diff_text)
    log(f"Diff ({len(diff_text)} znaków) zapisano w {diff_path}.")

    prompt = build_prompt(skills, diff_path, mr_title, mr_url, str(cfg("language")))
    log("Uruchamiam model...")
    raw = run_opencode(prompt, diff_path, model, os.environ["CI_PROJECT_DIR"])
    try:
        data = extract_json(raw)
    except ValueError as e:
        log(f"{e} Zapisuję surową odpowiedź do notatki.")
        gitlab.post_note(
            f"{SUMMARY_MARKER}\n🤖 **{cfg('title')}** — nie udało się sparsować odpowiedzi modelu.\n\n"
            f"```\n{raw[:4000]}\n```"
        )
        sys.exit(1)

    comments = data.get("comments", []) or []
    max_c = int(cfg("max_comments"))
    if len(comments) > max_c:
        comments = comments[:max_c]

    if env_bool("AI_REVIEW_DEDUPE", False):
        log("Usuwam poprzednie komentarze bota (dedupe).")
        for note in gitlab.list_notes():
            body = note.get("body", "")
            if SUMMARY_MARKER in body or COMMENT_MARKER in body:
                try:
                    gitlab.delete_note(note["id"])
                    log(f"Usunięto notatkę {note['id']}.")
                except urllib.error.HTTPError as e:
                    log(f"Nie udało się usunąć notatki {note['id']}: {e.code}")

    pending = post_inline(gitlab, comments, line_map, diff_refs)
    summary_body = build_summary(data, comments, pending, skills, model)
    nid = gitlab.post_note(summary_body)
    log(f"Opublikowano podsumowanie (note {nid}).")

    verdict = (data.get("summary") or {}).get("verdict", "changes_requested")
    if env_bool("AI_REVIEW_APPROVE", False):
        try:
            if verdict == "approved":
                gitlab.approve()
                log("MR zatwierdzony.")
            else:
                gitlab.unapprove()
                log("MR oznaczony jako wymagający poprawek.")
        except urllib.error.HTTPError as e:
            log(f"Nie udało się zaktualizować zatwierdzenia: {e.code}")

    fail_on = str(cfg("fail_on")).lower()
    critical = sum(1 for c in comments if c.get("severity") == "critical")
    warning = sum(1 for c in comments if c.get("severity") == "warning")
    if fail_on == "critical" and critical:
        log(f"{critical} zgłoszeń critical — kończę z kodem 1.")
        sys.exit(1)
    if fail_on == "warning" and (critical + warning):
        log(f"{critical + warning} zgłoszeń critical/warning — kończę z kodem 1.")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        die(str(e))
