# Horizon Local API

Horizon can run as a local FastAPI backend for desktop or local automation clients.

## Start

```bash
uv run horizon-api
```

Default address:

```text
http://127.0.0.1:8765
```

Interactive API docs:

- Swagger UI: `/docs`
- OpenAPI schema: `/openapi.json`

## Response Envelope

All API routes return the same envelope shape:

```json
{
  "code": 200,
  "success": true,
  "data": {},
  "errorCode": null,
  "errorMessage": null
}
```

Errors use the same envelope with `success: false`.

## Error Code Ranges

| Range | Area |
|-------|------|
| `1000-1999` | Common request and unknown errors |
| `2000-2999` | Configuration errors |
| `3000-3999` | Schedule and cron errors |
| `4000-4999` | Run and pipeline errors |
| `5000-5999` | Item query errors |
| `6000-6999` | Summary errors |
| `7000-7999` | Database errors |

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/config` | Read current config |
| `PUT` | `/config` | Validate and save config |
| `POST` | `/config/validate` | Validate a config payload |
| `POST` | `/runs` | Start a background pipeline run |
| `GET` | `/runs` | List runs |
| `GET` | `/runs/{run_id}` | Read a run |
| `POST` | `/runs/{run_id}/cancel` | Request run cancellation |
| `GET` | `/runs/{run_id}/logs` | List run logs |
| `GET` | `/items` | Query persisted items |
| `GET` | `/items/{item_id}` | Read one item |
| `GET` | `/summaries` | List summaries |
| `GET` | `/runs/{run_id}/summaries` | List summaries for a run |
| `POST` | `/schedules/validate-cron` | Validate a cron expression |
| `POST` | `/schedules` | Create a schedule |
| `GET` | `/schedules` | List schedules |
| `DELETE` | `/schedules/{schedule_id}` | Delete a schedule |

## Cron

Schedules support standard 5-field cron expressions only:

```text
0 8 * * *
```

Example validation request:

```bash
curl -X POST http://127.0.0.1:8765/schedules/validate-cron \
  -H 'Content-Type: application/json' \
  -d '{"cron_expr":"0 8 * * *","timezone":"Asia/Shanghai"}'
```

## Environment Variables

By default, Horizon Trace stores local API data in `~/.horizon`.

| Variable | Default | Description |
|----------|---------|-------------|
| `HORIZON_HOME` | `~/.horizon` | Horizon Trace user data directory |
| `HORIZON_DATA_DIR` | `~/.horizon` | Local data directory |
| `HORIZON_DB_PATH` | `~/.horizon/horizon.db` | SQLite database path |
| `HORIZON_CONFIG_PATH` | `~/.horizon/config.json` | Config file path |
| `HORIZON_SECRETS_PATH` | `~/.horizon/secrets.env` | Local user secrets file |
| `HORIZON_HOST` | `127.0.0.1` | API host |
| `HORIZON_PORT` | `8765` | API port |
