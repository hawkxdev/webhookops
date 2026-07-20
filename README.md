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
| Проверка HMAC: constant-time сравнение, защита от повтора по timestamp | Готово |
| Тесты проверки подписи | Готово |
| Эндпоинт приёма `POST /v1/webhooks/{source_slug}`: проверка источника, подписи и предела размера тела | Готово |
| Запись события на приёме: ключ идемпотентности, `persist_event`, `202` после фиксации транзакции | Готово |
| Тесты приёма и границы транзакции | В плане |
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

### Приём вебхука

```
POST /v1/webhooks/{source_slug}
```

В минимальной версии известен один источник: `generic_json`.

Заголовки:

| Заголовок | Назначение |
| --- | --- |
| `X-Timestamp` | обязательный: момент отправки в секундах Unix, допуск 300 секунд |
| `X-Signature-256` | обязательный: HMAC-SHA256 в hex по строке `{timestamp}.{сырое тело}` |
| `Idempotency-Key` | необязательный: ключ дедупликации от отправителя, до 255 символов ASCII. При отсутствии выводится как `sha256` сырого тела |

Секрет берётся из переменной окружения `GENERIC_JSON_HMAC_SECRET`.

Тело должно быть JSON-объектом. Оно разбирается только после подтверждённой подписи: до неё запрос недоверенный, а разбор - работа по команде отправителя.

Коды ответа:

| Код | Когда |
| --- | --- |
| `202 Accepted` | событие сохранено вместе со строкой `OutboxMessage`, транзакция зафиксирована. Повтор с тем же ключом получает такой же ответ и второго события не создаёт |
| `400 Bad Request` | подпись верна, но тело непригодно: не разбирается как JSON (`malformed_json`), разобралось не в объект (`payload_not_object`) или заголовок ключа не проходит по набору символов и длине (`invalid_idempotency_key`) |
| `403 Forbidden` | подпись не подтверждена: нет заголовков, неверная подпись, изменённое тело или просроченная метка. Причина наружу не раскрывается |
| `404 Not Found` | неизвестный `source_slug` |
| `413 Content Too Large` | тело больше 1 МиБ |

Ответы `4xx` различаются по строгости намеренно. До проверки подписи все причины отказа дают один и тот же `403`, иначе отправитель подбирал бы верный запрос по различиям в ответах. После подписи отправитель известен, и код ответа называет конкретную причину.

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
