---
id: example-test-rule
severity: warning
scope: [wszyscy]
---

## Dlaczego

Reguła testowa pokazująca format. Nie powinna być już używana w produkcji — zastąp ją
własnymi regułami odpowiednimi dla Twojego projektu (np. dotyczącymi stylu, typowania,
bezpieczeństwa, testów).

## Jak sprawdzać

Poszukaj w zmienionych liniach stałych debugowych:
- `console.log` / `console.debug` (JS/TS)
- `var_dump`, `print_r`, `dd(`, `dump(` (PHP)
- `print(...)`, `pp.pprint(...)` (Python)
- `println(...)`, `debugPrint(...)` (Kotlin/Dart)

Zgłoś naruszenie tylko wtedy, gdy dana linia jest dodana w MR.

## Przykład złego

```php
public function calculate(int $a, int $b): int {
    dump($a, $b); // debug na produkcji
    return $a + $b;
}
```

## Przykład dobrego

```php
public function calculate(int $a, int $b): int {
    return $a + $b;
}
```
