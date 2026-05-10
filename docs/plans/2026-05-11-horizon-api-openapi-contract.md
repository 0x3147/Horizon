# Horizon API OpenAPI Contract Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Swagger/OpenAPI useful for frontend integration by documenting request bodies, query parameters, response envelopes, and restricting MVP API methods to GET and POST.

**Architecture:** Keep FastAPI as the thin HTTP layer and add explicit Pydantic API schemas at the boundary. Each route declares `response_model=ApiResponse[DataModel]`, query parameters use `Query(...)` metadata, and mutating actions use POST endpoints only.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, FastAPI TestClient.

---

### Task 1: Lock OpenAPI Contract With Tests

**Files:**
- Create: `tests/test_openapi_contract.py`
- Modify: `tests/test_config_api.py`
- Modify: `tests/test_schedules_api.py`

**Steps:**
1. Add a test that loads `/openapi.json` and asserts every operation method is either `get` or `post`.
2. Add tests that assert removed methods are not exposed: no `PUT /config`, no `DELETE /schedules/{schedule_id}`.
3. Add tests that assert key request schemas exist: `RunStartRequest`, `ScheduleCreateRequest`, `CronValidationRequest`.
4. Add tests that assert key response schemas exist: `ApiResponse_HealthData_`, `ApiResponse_RunAcceptedData_`, `ApiResponse_ScheduleListData_`.
5. Update config save test from `client.put("/config")` to `client.post("/config")`.
6. Update schedule delete test to use `POST /schedules/{schedule_id}/delete`.
7. Run focused tests and confirm they fail for the expected OpenAPI/schema/method reasons.

### Task 2: Add API Boundary Schemas

**Files:**
- Modify: `src/api/schemas.py`

**Steps:**
1. Add models for common list/delete/action data: `DeleteResultData`, `ValidationResultData`.
2. Add config response models using the existing `src.models.Config` model.
3. Add run models: `RunStartRequest`, `RunData`, `RunListData`, `RunAcceptedData`, `RunLogData`, `RunLogListData`, `RunCancelData`.
4. Add item models: `ItemData`, `ItemListData`.
5. Add summary models: `SummaryData`, `SummaryListData`.
6. Add schedule models: `CronValidationData`, `ScheduleData`, `ScheduleListData`.
7. Use descriptions/examples where they materially improve Swagger readability.

### Task 3: Wire Schemas Into Routes

**Files:**
- Modify: `src/api/app.py`
- Modify: `src/api/routes/config.py`
- Modify: `src/api/routes/runs.py`
- Modify: `src/api/routes/items.py`
- Modify: `src/api/routes/summaries.py`
- Modify: `src/api/routes/schedules.py`

**Steps:**
1. Add FastAPI tags metadata for `health`, `config`, `runs`, `items`, `summaries`, and `schedules`.
2. Add `response_model` to every route.
3. Add route `summary` text for Swagger operation names.
4. Replace `PUT /config` with `POST /config`.
5. Replace `DELETE /schedules/{schedule_id}` with `POST /schedules/{schedule_id}/delete`.
6. Add `Query(...)` constraints for pagination, scores, and filters.
7. Keep runtime behavior unchanged except for method changes.

### Task 4: Verify Runtime And Docs

**Files:**
- No new production files expected.

**Steps:**
1. Run focused API/OpenAPI tests.
2. Run the existing API/storage route tests.
3. Start `uv run horizon-api` against a temporary `HORIZON_HOME`.
4. Verify `/health`, `/openapi.json`, and `/docs`.
5. Inspect `/openapi.json` to confirm no PUT/DELETE methods remain.
