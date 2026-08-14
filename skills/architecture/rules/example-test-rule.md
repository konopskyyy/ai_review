---
id: example-test-rule
severity: warning
scope: [backend]
---

## Dlaczego

Reguła testowa pokazująca format. Zastąp ją własnymi regułami architektury, np. dotyczącymi
warstw (domena / aplikacja / infrastruktura), CQRS, event-driven, hexagonal, etc.

## Jak sprawdzać

W zmienionych liniach poszukaj importów/zależności z warstwy infrastrukturalnej
(framework, ORM, HTTP klient) w kodzie warstwy domeny. Przykłady sygnałów:
- PHP: `use Symfony\...`, `use Doctrine\ORM\...` wewnątrz klasy domenowej
- Python: `import sqlalchemy`, `import requests` w module domeny
- Java/Kotlin: `import org.springframework...` w klasie domenowej

Zgłoś naruszenie tylko wtedy, gdy dana linia jest dodana w MR.

## Przykład złego

```php
namespace App\Domain\Order;

use Doctrine\ORM\Mapping as ORM; // zależność infrastruktury w domenie

final class Order
{
    #[ORM\Id]
    private int $id;
}
```

## Przykład dobrego

```php
namespace App\Domain\Order;

final class Order
{
    private OrderId $id;
}
```
