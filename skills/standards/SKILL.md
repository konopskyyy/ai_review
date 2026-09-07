---
name: standards
description: Standardy kodowania dla projektu. Zawiera reguły, których musi przestrzegać każda zmiana w MR. Reguły znajdują się w katalogu rules/ i mogą być nadpisane przez projekt (`.opencode/skills/standards`).
license: MIT
compatibility: opencode
metadata:
  scope: code-review
---

# Skill: standards

Egzekwuje standardy kodowania projektu podczas przeglądu Merge Requestów.

## Struktura

Reguły żyją w `rules/*.md` — **jedna reguła na plik**. Repozytorium może dostarczyć własny zestaw reguł, umieszczając swoje pliki w `.opencode/skills/standards/rules/` — wtedy mają pierwszeństwo nad domyślnymi.

Format reguły:

```md
---
id: nazwa-reguly
severity: critical | warning | info
scope: [scopes, w których obowiązuje, np. php, frontend, wszyscy]
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
2. Dla każdej reguły sprawdź zmienione linie diffa.
3. Zgłoszenie w polu `rule` komentarza JSON: `standards:<id-reguly>`.
4. Zgłaszaj tylko naruszenia reguł, które dotyczą zmienionych linii.

## Reguły domyślne

Reguły domyślne żyją w `rules/`. Kolejne reguły dodawaj jako osobne pliki w `rules/`.
