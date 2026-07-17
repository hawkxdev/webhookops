# WebhookOps

Локально запускаемый шлюз надёжной доставки вебхуков. Принимает внешние вебхуки на горячем пути, проверяет HMAC-подпись, дедуплицирует по ключу идемпотентности, атомарно сохраняет событие вместе с записью на доставку (`transactional outbox`) и асинхронно доставляет подписчикам с повторами, `DLQ` и ручным повтором.

**Модель надёжности:** `at-least-once` плюс идемпотентность. `exactly-once` не поддерживается.

> Статус: в разработке.

## Статус по возможностям

| Возможность | Статус |
| --- | --- |
| uv workspace, линт/типы (`ruff`, `pyright`), инфраструктура Docker Compose | Готово |
| Django-слой, кастомная модель пользователя, доменные модели `Event` и `OutboxMessage`, миграции | Готово |
| Контракт записи `persist_event`: `Event` + `OutboxMessage` в одной транзакции, идемпотентность на `UNIQUE` | Готово |
| Сервис `ingest`: приложение FastAPI, пул asyncpg, эндпоинт `/health` | Готово |
| Тесты идемпотентности контракта записи | Готово |
| Эндпоинт приёма вебхуков: валидация, HMAC, ответ `202 Accepted` | В разработке |
| Тесты HMAC и границы транзакции | В разработке |
| Доставка: публикатор outbox, RabbitMQ, Celery-воркер, HTTP подписчику, `DeliveryAttempt` | В плане |
| Автоповторы, `DLQ`, ручной повтор | В плане |
| Управляющий слой Django/DRF (CRUD источников и подписчиков, админка, аудит) | В плане |
| Демо-подписчик (`200`/`500`/таймаут), полная упаковка Docker | В плане |

## Архитектура

Три сервиса вокруг PostgreSQL как источника истины:

```
вебхук -> [ingest: FastAPI]   приём, HMAC, идемпотентность,
                              Event + OutboxMessage в одной транзакции -> 202
                    |
                    v
            [PostgreSQL]  источник истины (события, outbox, попытки доставки)
                    ^
                    |
[management: Django/DRF] управляющий слой, публикатор outbox, Celery-воркеры
                    |
                    v
              [RabbitMQ] транспорт -> доставка подписчику
```

- `ingest/` - FastAPI, горячий путь приёма (планируется как узкий вход, не второй управляющий API).
- `management/` - Django/DRF: модели, миграции, админка, аудит, публикатор outbox, воркеры доставки. Django владеет схемой.
- `shared/` - общий контракт записи между сервисами (`persist_event`).
- Redis - ограничение частоты на приёме (не источник истины, не брокер).

## Технологии

- [Python 3.12](https://docs.python.org/3.12/), пакеты через [uv](https://docs.astral.sh/uv/)
- [FastAPI](https://fastapi.tiangolo.com/) - горячий путь приёма
- [Django 5.2](https://docs.djangoproject.com/en/5.2/) + [DRF](https://www.django-rest-framework.org/) - управляющий слой
- [PostgreSQL 16](https://www.postgresql.org/docs/16/) - источник истины, драйвер [asyncpg](https://magicstack.github.io/asyncpg/) и [psycopg 3](https://www.psycopg.org/psycopg3/)
- [RabbitMQ](https://www.rabbitmq.com/) + [Celery](https://docs.celeryq.dev/) - доставка
- [Redis](https://redis.io/) - ограничение частоты приёма
- Качество: [ruff](https://docs.astral.sh/ruff/), [pytest](https://docs.pytest.org/), [pyright](https://microsoft.github.io/pyright/)

## Требования

- Python 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker и Docker Compose

## Запуск

Все команды из корня репозитория.

```bash
git clone https://github.com/hawkxdev/webhookops.git
cd webhookops
```

Переменные окружения (значения для локали задай сам):

```bash
cp .env.example .env
```

`.env.example` содержит `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `SECRET_KEY`, `GENERIC_JSON_HMAC_SECRET`.

Зависимости и инфраструктура:

```bash
uv sync
docker compose up -d postgres rabbitmq redis
```

Схема базы и суперпользователь (из каталога `management/`):

```bash
cd management
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

Django-админка поднимается на `http://127.0.0.1:8000/admin/` после `uv run python manage.py runserver`.

Сервис приёма `ingest` (из корня репозитория, порт 8001, чтобы не спорить с Django на 8000):

```bash
uv run uvicorn ingest.main:app --reload --port 8001
curl http://127.0.0.1:8001/health
```

Ответ `{"status":"ok"}` означает, что приложение поднялось и база отвечает.

> Эндпоинт приёма вебхуков (`202 Accepted`) в разработке: `ingest` пока отдаёт только `/health`.

## Проверки качества

Из корня репозитория:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Компромиссы

- **`at-least-once`, не `exactly-once`.** Повторы неизбежны, дубли ловятся идемпотентностью на уникальном ограничении PostgreSQL, а не проверкой в коде. Однократная доставка через сеть не гарантируется.
- **SQL-диалект PostgreSQL, не переносимый SQL.** Проект использует родные сильные стороны Postgres (`jsonb`, `ON CONFLICT`, `RETURNING`) ради идемпотентности одним запросом. Цена - привязка к СУБД.
- **Граница зависимостей не равна границе деплоя.** Один `uv.lock` на все сервисы доказывает совместимость FastAPI и Django, но сервисы остаются отдельными процессами и контейнерами.

## Автор

[hawkxdev](https://github.com/hawkxdev)
