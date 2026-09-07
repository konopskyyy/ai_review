---
id: php-symfony-code
severity: warning
scope: [php]
---

## Dlaczego

Projekt działa na PHP >=8.5 i Symfony 8.1. Spójny styl (atrybuty, typed properties, konstruktor z `private readonly`) to podstawa utrzymywalności i zgodności z ekosystemem Symfony.

## Jak sprawdzać

- Routing/rejestracja handlerów przez atrybuty Symfony: `#[Route]`, `#[AsMessage]`, `#[AsMessageHandler]`.
- Wstrzykiwanie zależności w konstruktorze przez `private readonly` properties.
- Typowane właściwości i sygnatury metod (typy parametrów i zwracane).
- Brak zbędnych komentarzy/docblocków — kod ma być samoopisowy.

## Przykład złego

```php
public function __construct(public MailerInterface $mailer) { } // public + brak readonly
// stary docblock
/** @return void */
public function send() { ... }
```

## Przykład dobrego

```php
public function __construct(private readonly MailerInterface $mailer) { }

public function send(string $to): void { ... }
```