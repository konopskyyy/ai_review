---
name: architecture
description: Zasady architektury projektu — warstwy, zależności, granice modułów. Reguły w rules/, nadpisywalne przez projekt (`.opencode/skills/architecture`).
license: MIT
compatibility: opencode
metadata:
  scope: code-review
---

# Skill: architecture

Egzekwuje zasady architektury podczas przeglądu Merge Requestów.

## Struktura

Reguły żyją w `rules/*.md` — **jedna reguła na plik**. Repozytorium może dostarczyć własny zestaw reguł w `.opencode/skills/architecture/rules/` — mają pierwszeństwo nad domyślnymi.

Format reguły:

```md
---
id: nazwa-reguly
severity: critical | warning | info
scope: [np. backend, frontend, domena]
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

## Jak używać w review

1. Wczytaj wszystkie pliki z `rules/` (domyślne + projektowe, jeśli istnieją).
2. Sprawdź, czy zmiana nie łamie granic architektonicznych (importy, zależności, przepływ danych).
3. Zgłoszenie w polu `rule` komentarza JSON: `architecture:<id-reguly>`.
4. Zgłaszaj tylko naruszenia, które dotyczą zmienionych linii.

## Reguły domyślne

Poniżej jedna testowa reguła. Kolejne reguły dodawaj jako osobne pliki w `rules/`.
