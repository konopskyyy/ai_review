# AI Review — bot do przeglądu Merge Requestów w GitLab

Kontener uruchamiany w pipeline GitLab CI, który przegląda Merge Requesty przy użyciu
**opencode** z tym samym modelem, którego używasz lokalnie (domyślnie
`opencode/big-pickle`). Bot:

- wczytuje **skille** `standards` i `architecture` (standardy + architektura projektu),
- analizuje diff MR (tylko zmienione linie),
- publikuje **inline komentarze** na konkretnych liniach,
- dodaje **notatkę-podsumowanie** z werdyktem,
- może blokować pipeline (`fail_on`) i opcjonalnie zatwierdzać/odrzucać MR.

---

## Struktura repozytorium

```
ai_review/
├── Dockerfile                 # obraz: python + opencode + skille + bot
├── .gitlab-ci.yml             # pipeline budujący i wgrywający obraz do registry
├── review.py                  # logika bota (GitLab API, opencode run, publikacja)
├── entrypoint.sh              # punkt wejścia obrazu (preflight, --self-test)
├── opencode/
│   ├── opencode.json          # permissions dla opencode (bez bash/edit)
│   └── agent/ai-review.md     # agent-review (persona + ograniczenia)
└── skills/
    ├── standards/             # skill: standardy kodowania
    │   ├── SKILL.md
    │   └── rules/             # no-secrets-in-repo, php-symfony-code, migration-conventions
    └── architecture/          # skill: zasady architektury
        ├── SKILL.md
        └── rules/
```

---

## 1. Zbuduj i wgraj obraz do registry GitLab

Po wrzuceniu repo do GitLaba (np. grupa `tools/ai-review`), obraz buduje się
automatycznie przez `.gitlab-ci.yml` i ląduje w:

```
registry.gitlab.com/<twoja-grupa>/ai-review:latest
```

Możesz też zbudować lokalnie:

```bash
docker build -t ai-review:dev .
docker run --rm ai-review:dev --self-test   # test bez API
```

### GitHub (GHCR)

Obraz publikowany jest też do GitHub Container Registry przez ten workflow:

```
.github/workflows/publish.yml
```

Po pushu na `main` (lub tagu `v*`) obraz ląduje w:

```
ghcr.io/<owner>/ai_review:latest
```

Projekt na GitHubie uruchamia review kontenerem z tego obrazu:

```yaml
run: |
    docker run --rm \
        --network=host \
        -e GITHUB_TOKEN \
        -e OPENCODE_API_KEY \
        -e GITHUB_REPOSITORY \
        -e PR_NUMBER \
        -e GITHUB_WORKSPACE \
        -e AI_REVIEW_MODEL \
        -e AI_REVIEW_SKILLS \
        -e AI_REVIEW_FAIL_ON \
        -v "${{ github.workspace }}:${{ github.workspace }}" \
        -v "${{ github.workspace }}/.github/scripts/ai-review.py:/opt/ai-review/github-review.py" \
        -w "${{ github.workspace }}" \
        ghcr.io/<owner>/ai_review:latest \
        python3 /opt/ai-review/github-review.py
```

---

## 2. Użycie w innych pipeline — minimalny przykład

W jobie **w swoim projekcie**:

```yaml
# .gitlab-ci.yml
ai-review:
  image: registry.gitlab.com/<twoja-grupa>/ai-review:latest
  stage: test
  variables:
    OPENCODE_API_KEY: $OPENCODE_API_KEY   # masked CI variable (zakres: api)
    GITLAB_TOKEN: $GITLAB_REVIEW_TOKEN    # masked CI variable (zakres: api)
  script:
    - /opt/ai-review/entrypoint.sh
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
```

### Reuse przez `include` (zalecane)

Wrzuć ten szablon do projektu `tools/ai-review` i włącz go w innych repo:

```yaml
# .gitlab-ci.yml (projekt docelowy)
include:
  - project: 'tools/ai-review'
    ref: main
    file: 'examples/ai-review.yml'
```

Szablon: [`examples/ai-review.yml`](examples/ai-review.yml) — wszystkie opcje
parametryzowane zmiennymi, domyślnie działa od ręki.

---

## 3. Zmienne środowiskowe

### Wymagane (GitLab dostarcza automatycznie, poza tokenami)

| Zmienna | Opis |
|---|---|
| `CI_API_V4_URL` | np. `https://gitlab.com/api/v4` (automatyczna) |
| `CI_PROJECT_ID` | id projektu (automatyczna) |
| `CI_MERGE_REQUEST_IID` | numer MR (automatyczna) |
| `CI_PROJECT_DIR` | katalog checkoutu (automatyczna) |
| `GITLAB_TOKEN` | token z zakresem `api` — masked CI variable (osobisty lub projektowy) |
| `OPENCODE_API_KEY` | klucz API modelu (masked CI variable) |

> Bez `GITLAB_TOKEN` bot spróbuje użyć `CI_JOB_TOKEN` (działa tylko z pełnymi
> uprawnieniami do pisania notatek na MR).

### Opcjonalne

| Zmienna | Domyślna | Opis |
|---|---|---|
| `AI_REVIEW_MODEL` | `opencode/big-pickle` | model w formacie `provider/model` |
| `AI_REVIEW_SKILLS` | `standards,architecture` | lista skilli (rozdzielona przecinkiem) |
| `AI_REVIEW_FAIL_ON` | `critical` | `none` \| `critical` \| `warning` — kiedy pipeline ma spaść |
| `AI_REVIEW_MAX_COMMENTS` | `25` | limit komentarzy inline |
| `AI_REVIEW_MAX_DIFF_CHARS` | `200000` | limit rozmiaru diffa w kontekście |
| `AI_REVIEW_DEDUPE` | `false` | `true` → usuń poprzednie komentarze bota przed publikacją |
| `AI_REVIEW_APPROVE` | `false` | `true` → zatwierdza/odrzuca MR na podstawie werdyktu |
| `AI_REVIEW_LANGUAGE` | `pl` | `pl` \| `en` |
| `AI_REVIEW_TITLE` | `AI Review` | tytuł notatki |
| `AI_REVIEW_TIMEOUT_SECONDS` | `600` | limit czasu na `opencode run` |
| `AI_REVIEW_ALLOW_ANY_PIPELINE` | `false` | `true` → uruchom także poza pipeline MR (wymaga GITLAB_TOKEN i MR IID) |

---

## 4. Model

Domyślnie używany jest `opencode/big-pickle` — ten sam model co w Twoim lokalnym
opencode. Zmienisz go przez `AI_REVIEW_MODEL`. Klucz podaje się zmienną
`<PROVIDER>_API_KEY` (np. `OPENCODE_API_KEY`, `ANTHROPIC_API_KEY`).

```yaml
variables:
  AI_REVIEW_MODEL: anthropic/claude-sonnet-4-5
  ANTHROPIC_API_KEY: $ANTHROPIC_API_KEY
```

---

## 5. Skille — standardy i architektura

Bot wczytuje skille przez natywny mechanizm opencode. Domyślne templatki siedzą
w obrazie (`skills/`), a **projekt może je nadpisać** własnymi plikami w repo:

```
.opencode/skills/standards/SKILL.md          # reguły standardów projektu
.opencode/skills/standards/rules/<regula>.md
.opencode/skills/architecture/SKILL.md       # reguły architektury projektu
.opencode/skills/architecture/rules/<regula>.md
```

Domyślny zestaw reguł żyje w `rules/` (standardy: `no-secrets-in-repo`,
`php-symfony-code`, `migration-conventions`; architektura: brak reguł domyślnych —
dodaj własne albo dostarcz projektowe). **Projekt może je nadpisać/dodać** własnymi
plikami w `.opencode/skills/`. Format reguły:

```md
---
id: moja-regula
severity: warning            # critical | warning | info
scope: [php, frontend]
---

## Dlaczego
...

## Jak sprawdzać
...

## Przykład złego
...

## Przykład dobrego
...
```

Model odnosi się do reguły w komentarzu jako `standards:<id>` / `architecture:<id>`.

---

## 6. Jak działa review

1. Pobiera zmiany MR z API GitLab (`changes` + `diff_refs`).
2. Buduje kontekst: diff + skille + dostęp do plików repo.
3. `opencode run --agent ai-review` zwraca JSON:
   - `summary.verdict` → `approved` / `changes_requested`
   - `summary.body` → podsumowanie w Markdown
   - `comments[]` → `{ path, new_line, severity, message, rule }`
4. Publikuje inline discussions (tylko dla linii istniejących w nowej wersji diffa;
   pozostałe lądują w podsumowaniu) oraz notatkę-podsumowanie.
5. Zgodnie z `AI_REVIEW_FAIL_ON` kończy z kodem `0`/`1` — tym samym blokuje (lub nie) pipeline.

> Bot jest bezpieczny: `bash` i `edit` są zablokowane w konfiguracji opencode
> (`opencode/opencode.json` + agent `ai-review`), więc nie uruchamia kodu z repo.

---

## 7. Test lokalny

Bez klucza API i bez GitLaba sprawdzisz parsowanie diffa i budowanie promptu:

```bash
docker run --rm registry.gitlab.com/<twoja-grupa>/ai-review:latest --self-test
```

---

## 8. Troubleshooting

- **„Brak klucza API dla providera"** → ustaw `OPENCODE_API_KEY` (lub `<PROVIDER>_API_KEY`) jako masked CI variable.
- **„To nie jest pipeline MR"** → job musi mieć `rules: if: $CI_PIPELINE_SOURCE == "merge_request_event"`.
- **Komentarze nie są inline** → nowe linie nie występują w diffie (np. `new_line` poza zakresem) — bot przenosi je do podsumowania. Zawęża to do linii dodanych.
- **HTTP 403 przy publikacji** → token nie ma zakresu `api` / bot nie ma uprawnień do projektu.
- **Powtarzające się komentarze po re-runcie** → ustaw `AI_REVIEW_DEDUPE: "true"`.
