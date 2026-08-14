#!/usr/bin/env bash
set -euo pipefail

# Użycie:
#   entrypoint.sh            → pełne review MR (wymaga zmiennych CI GitLab)
#   entrypoint.sh --self-test → test bez API (parser diffa + prompt)
#   entrypoint.sh --help      → krótka pomoc

if [[ "${1:-}" == "--self-test" ]]; then
  exec python3 /opt/ai-review/review.py --self-test
fi

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat <<'HELP'
AI Review — bot do przeglądu Merge Requestów w GitLab (oparty o opencode).

Wymagane zmienne (dostarcza GitLab CI automatycznie):
  CI_API_V4_URL            np. https://gitlab.com/api/v4
  CI_PROJECT_ID
  CI_MERGE_REQUEST_IID
  CI_PROJECT_DIR           katalog z repozytorium
  GITLAB_TOKEN             token z zakresem `api` (masked CI variable) — wymagany

Opcjonalne:
  AI_REVIEW_MODEL          domyślnie opencode/big-pickle
  AI_REVIEW_SKILLS         domyślnie standards,architecture
  AI_REVIEW_FAIL_ON        domyślnie critical (none|critical|warning)
  AI_REVIEW_MAX_COMMENTS   domyślnie 25
  AI_REVIEW_MAX_DIFF_CHARS domyślnie 200000
  AI_REVIEW_DEDUPE         true → usuwa poprzednie komentarze bota
  AI_REVIEW_APPROVE        true → zatwierdza/odrzuca MR na podstawie werdyktu
  AI_REVIEW_LANGUAGE       pl | en
  AI_REVIEW_TITLE          tytuł notatki, domyślnie "AI Review"
  AI_REVIEW_TIMEOUT_SECONDS domyślnie 600

Model (ten sam co w opencode lokalnie):
  OPENCODE_API_KEY         klucz API dla providera `opencode` (lub <PROVIDER>_API_KEY)

Przykład użycia w .gitlab-ci.yml:
  ai-review:
    image: registry.gitlab.com/<grupa>/ai-review:latest
    stage: test
    script:
      - /opt/ai-review/entrypoint.sh
    rules:
      - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
HELP
  exit 0
fi

if [[ -z "${CI_API_V4_URL:-}" || -z "${CI_PROJECT_ID:-}" || -z "${CI_MERGE_REQUEST_IID:-}" ]]; then
  echo "[ai-review] Brak zmiennych CI (CI_API_V4_URL / CI_PROJECT_ID / CI_MERGE_REQUEST_IID)." >&2
  echo "[ai-review] Ten obraz uruchamia się w jobie pipeline MR. Użyj --self-test do testu lokalnego." >&2
  exit 1
fi

if [[ -z "${CI_PROJECT_DIR:-}" || ! -d "${CI_PROJECT_DIR}" ]]; then
  echo "[ai-review] CI_PROJECT_DIR nie wskazuje na katalog z repozytorium (${CI_PROJECT_DIR:-puste})." >&2
  exit 1
fi

exec python3 /opt/ai-review/review.py
