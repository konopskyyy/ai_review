---
id: no-secrets-in-repo
severity: critical
scope: [wszyscy]
---

## Dlaczego

`.env`, `.env.local` i sekrety (hasła, klucze API, JWT passphrase) są wyłączone z repo. Wyciek sekretu do historii gita jest praktycznie nieodwracalny.

## Jak sprawdzać

- W diffie lub dodanych plikach nie ma haseł, tokenów, kluczy prywatnych (`*.pem`), hasel w konfiguracji.
- Nowe wartości konfiguracyjne odnoszą się do zmiennych środowiskowych, nie do literalnych sekretów.
- Pliki `*.local`, `/var/`, `/vendor/`, katalogi `config/jwt/*.pem` pozostają poza commitami.

## Przykład złego

```env
MAILER_DSN=smtp://user:super-secret-pass@mail.example.com:587
```

```php
'passphrase' => 'hunter2'
```

## Przykład dobrego

```env
MAILER_DSN=${MAILER_DSN}
```

```php
'passphrase' => $_ENV['JWT_PASSPHRASE']
```