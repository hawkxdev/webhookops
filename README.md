# WebhookOps

A locally runnable gateway for reliable webhook delivery. The implemented ingress path verifies HMAC signatures, deduplicates requests by idempotency key, and atomically stores each event with an outbox row. Subscriber delivery, retries, DLQ handling, and manual replay are planned.

**Reliability model:** `at-least-once` plus idempotency. `exactly-once` is not supported.

> Status: under development.

## Capability status

| Capability | Status |
| --- | --- |
| uv workspace, linting and type checks (`ruff`, `pyright`), Docker Compose infrastructure | Done |
| Django layer, custom user model, domain models `Event`, `OutboxMessage`, `Subscriber`, and `DeliveryAttempt`, migrations | Done |
| `persist_event` write contract: `Event` + `OutboxMessage` in one transaction, idempotency enforced by `UNIQUE` | Done |
| `ingest` service: FastAPI application, asyncpg pool, `/health` endpoint | Done |
| Idempotency tests for the persistence contract | Done |
| HMAC verification: constant-time comparison and timestamp replay protection | Done |
| Signature verification tests | Done |
| Ingress endpoint `POST /v1/webhooks/{source_slug}`: source, signature, and body-size validation | Done |
| Event persistence during ingress: idempotency key, `persist_event`, `202` after transaction commit | Done |
| Ingress tests: endpoint, negative cases, unhandled exception handler | Done |
| Database barrier tests: `UNIQUE` constraint and atomic event + outbox persistence | Done |
| Delivery: outbox publisher, RabbitMQ, Celery worker, subscriber HTTP call | Planned |
| Automatic retries, `DLQ`, manual replay | Planned |
| Django Admin: view accepted events, prevent edits and deletion | Done |
| Django/DRF management layer: source and subscriber CRUD, audit | Planned |
| Demo subscriber (`200`/`500`/timeout), complete Docker packaging | Planned |

## Architecture

Three services around PostgreSQL as the source of truth:

```
webhook -> [ingest: FastAPI]   ingestion, HMAC, idempotency,
                              Event + OutboxMessage in one transaction -> 202
                    |
                    v
            [PostgreSQL]  source of truth (events, outbox, delivery attempts)
                    ^
                    |
[management: Django/DRF] management layer; outbox publisher and Celery workers (planned)
                    |
                    v
              [RabbitMQ] transport (planned) -> subscriber delivery (planned)
```

- `ingest/`: FastAPI webhook ingress hot path. It remains a narrow entry point, not a second management API.
- `management/`: Django models, migrations, read-only event administration, and planned DRF CRUD, audit, outbox publisher, and delivery workers. Django owns the database schema.
- `shared/`: shared persistence contract between services (`persist_event`).
- Redis: planned ingress rate limiting. It is not a source of truth or a broker.

## Technology

- [Python 3.12](https://docs.python.org/3.12/), packages managed with [uv](https://docs.astral.sh/uv/)
- [FastAPI](https://fastapi.tiangolo.com/): webhook ingress hot path
- [Django 5.2](https://docs.djangoproject.com/en/5.2/) + [DRF](https://www.django-rest-framework.org/): Django management foundations, with DRF CRUD planned
- [PostgreSQL 16](https://www.postgresql.org/docs/16/): source of truth, using [asyncpg](https://magicstack.github.io/asyncpg/) and [psycopg 3](https://www.psycopg.org/psycopg3/)
- [RabbitMQ](https://www.rabbitmq.com/) + [Celery](https://docs.celeryq.dev/): planned delivery pipeline
- [Redis](https://redis.io/): planned ingress rate limiting
- Quality: [ruff](https://docs.astral.sh/ruff/), [pytest](https://docs.pytest.org/), [pyright](https://microsoft.github.io/pyright/)

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Docker and Docker Compose

## Run locally

Run every command from the repository root unless a step says otherwise.

```bash
git clone https://github.com/hawkxdev/webhookops.git
cd webhookops
```

Create the local environment file and set local values yourself:

```bash
cp .env.example .env
```

`.env.example` contains `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `SECRET_KEY`, and `GENERIC_JSON_HMAC_SECRET`.

Install dependencies and start the infrastructure:

```bash
uv sync
docker compose up -d postgres rabbitmq redis
```

Apply the database schema and create a superuser from `management/`:

```bash
cd management
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

Django Admin is available at `http://127.0.0.1:8000/admin/` after running `uv run python manage.py runserver`.

Start the `ingest` service from the repository root on port 8001, leaving port 8000 for Django:

```bash
uv run uvicorn ingest.main:app --reload --port 8001
curl http://127.0.0.1:8001/health
```

The response `{"status":"ok"}` confirms that the application is running and the database is reachable.

### Webhook ingestion

```
POST /v1/webhooks/{source_slug}
```

The current minimal version recognizes one source: `generic_json`.

Headers:

| Header | Purpose |
| --- | --- |
| `X-Timestamp` | required: Unix timestamp in seconds, with a 300-second tolerance |
| `X-Signature-256` | required: hexadecimal HMAC-SHA256 digest of `{timestamp}.{raw body}` |
| `Idempotency-Key` | optional: sender-provided deduplication key, up to 255 ASCII characters. If omitted, it is derived as the raw body SHA-256 digest |

The secret comes from the `GENERIC_JSON_HMAC_SECRET` environment variable.

The request body must be a JSON object. It is parsed only after the signature is verified: before verification, the request is untrusted and parsing would perform sender-controlled work.

Response codes:

| Code | Condition |
| --- | --- |
| `202 Accepted` | the event and its `OutboxMessage` row are stored and the transaction is committed. A request with the same key receives the same response and does not create a second event |
| `400 Bad Request` | the signature is valid, but the body cannot be parsed as JSON (`malformed_json`), is not an object (`payload_not_object`), or the idempotency key header fails character or length validation (`invalid_idempotency_key`) |
| `403 Forbidden` | the signature cannot be verified: headers are missing, the signature is invalid, the body changed, or the timestamp expired. The external response does not disclose the specific reason |
| `404 Not Found` | `source_slug` is unknown |
| `413 Content Too Large` | the body exceeds 1 MiB |

The `4xx` responses intentionally differ only after authentication. Before signature verification, all rejection causes return the same `403`; otherwise, a sender could use response differences to iteratively construct a valid request. After verification, the sender is known and the response identifies the relevant request error.

## Quality checks

Run from the repository root:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Trade-offs

- **`at-least-once`, not `exactly-once`.** Retries are unavoidable. PostgreSQL uniqueness provides idempotent duplicate handling instead of an application-level pre-check. The network cannot guarantee single delivery.
- **PostgreSQL-specific SQL, not portable SQL.** The project uses PostgreSQL features (`jsonb`, `ON CONFLICT`, `RETURNING`) to provide idempotency in one query. The cost is database coupling.
- **The dependency boundary is not the deployment boundary.** One `uv.lock` proves that the FastAPI and Django dependencies are compatible, while the services remain separate processes and containers.

## Known limitations

[Issues](https://github.com/hawkxdev/webhookops/issues)

## License

[MIT](LICENSE)

## Author

[hawkxdev](https://github.com/hawkxdev)