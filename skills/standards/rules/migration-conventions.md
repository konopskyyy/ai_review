---
id: migration-conventions
severity: warning
scope: [php]
---

## Dlaczego

Migracje Doctrine są śledzone w historii repo. Konwencje projektu (opis w `getDescription()`, brak auto-generowanych komentarzy, heredoc dla SQL, spójny suffix DDL) ułatwiają review i rollback.

## Jak sprawdzać

- Brak auto-generowanych docblocków/inline komentarzy (`// this up() migration is auto-generated` itd.) — zmień opis w `getDescription()`.
- Zapytania DDL/`UPDATE` zapisane jako `addSql(<<<SQL ... SQL)` (heredoc).
- `CREATE TABLE` zachowuje suffix `DEFAULT CHARACTER SET utf8mb4 COLLATE \`utf8mb4_unicode_ci\` ENGINE = InnoDB`.
- Wzorcowy plik: `migrations/Version20260810190000.php`.

## Przykład złego

```php
public function up(Schema $schema): void
{
    // this up() migration is auto-generated, please modify it to your needs
    $this->addSql('CREATE TABLE foo ...');
}
```

## Przykład dobrego

```php
public function getDescription(): string
{
    return 'Dodaje tabelę foo';
}

public function up(Schema $schema): void
{
    $this->addSql(<<<SQL
        CREATE TABLE foo (...) DEFAULT CHARACTER SET utf8mb4 COLLATE `utf8mb4_unicode_ci` ENGINE = InnoDB
        SQL);
}
```