# Сервис исполнения платежей

Сервис на FastAPI регулярно выбирает из PostgreSQL платежи с `execute_on <= сегодняшняя дата` и отправляет их в фабрику. Это позволяет автоматически догонять платежи, которые не были отправлены из-за падения кластера. Фоновый цикл запускается через FastAPI `lifespan`, поэтому отдельные Celery worker, Beat и брокер не нужны.

## Как это работает

1. При старте FastAPI запускает polling-loop.
2. Цикл каждые `POLL_INTERVAL_SECONDS` выбирает платежи на текущую дату и просроченные платежи через `FOR UPDATE SKIP LOCKED`, начиная с самой ранней даты исполнения.
3. Выбранные записи переводятся в `processing` и обрабатываются с ограниченной параллельностью `MAX_CONCURRENCY`.
4. Успешный ответ фабрики переводит платёж в `submitted`.
5. Ошибки повторяются с exponential backoff; после исчерпания попыток платёж получает статус `failed`.
6. Зависшие `processing` записи переиспользуются после `PROCESSING_LEASE_SECONDS`.

Несколько Pod’ов, в том числе в разных Kubernetes-кластерах, могут работать с одной primary PostgreSQL: блокировка строки распределит платежи между ними. Фабрика должна соблюдать `Idempotency-Key`, потому что при падении процесса после HTTP-запроса возможна повторная попытка.

## Запуск

```powershell
Copy-Item .env.example .env
docker compose -f compose.yml up --build
```

Запускаются PostgreSQL, миграция и `payment-executor`. HTTP-проверки доступны на `http://localhost:8000/health/live` и `http://localhost:8000/health/ready`.

Для локального запуска:

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+psycopg2://payments:payments@localhost:5432/payments"
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Не запускайте несколько Uvicorn workers в одном контейнере без необходимости: для масштабирования лучше использовать несколько Pod’ов, управляемых Kubernetes.

## Таблица платежей

Миграция создаёт таблицу `payments`. Вставка платежа для выполнения сегодня выглядит так:

```sql
INSERT INTO payments (external_id, execute_on, amount, currency, payload, factory_request_id)
VALUES (
  'order-10001',
  CURRENT_DATE,
  1250.00,
  'RUB',
  '{"payer_account":"40817810000000000001","payee_account":"40817810000000000002"}'::jsonb,
  gen_random_uuid()
);
```

Если в окружении не включено расширение `pgcrypto`, передайте UUID из приложения или выполните `CREATE EXTENSION IF NOT EXISTS pgcrypto;`. Статус нового платежа — `pending`.

## Контракт фабрики

Запрос отправляется на `FACTORY_EXECUTE_URL`:

```http
POST /api/v1/payments/execute
Authorization: Bearer <FACTORY_TOKEN>  # если задан
Idempotency-Key: <factory_request_id>
Content-Type: application/json
```

```json
{
  "payment_id": "42",
  "external_id": "order-10001",
  "execute_on": "2026-10-15",
  "amount": "1250.00",
  "currency": "RUB",
  "data": {
    "payer_account": "40817810000000000001",
    "payee_account": "40817810000000000002"
  }
}
```

Фабрика должна отвечать HTTP `2xx`. Необязательное поле `factory_payment_id` (или `id`) из JSON-ответа сохраняется в платеже.

## Настройки

- `POLL_INTERVAL_SECONDS` — интервал опроса PostgreSQL;
- `MAX_CONCURRENCY` — число одновременных запросов к фабрике в одном Pod;
- `PROCESSING_LEASE_SECONDS` — время, после которого зависший платёж можно забрать повторно;
- `MAX_RETRIES` — число повторов после первой попытки;
- `HTTP_TIMEOUT_SECONDS` — таймаут запроса в фабрику.

