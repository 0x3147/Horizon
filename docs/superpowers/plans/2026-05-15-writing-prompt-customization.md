# Writing Prompt Customization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users edit the system prompt and user prompt templates used for Horizon Trace report and blog generation, while leaving scoring and enrichment prompts hidden.

**Architecture:** Store optional writing prompt overrides in the existing Horizon config file, expose default prompt metadata through the config API, resolve effective prompts inside `WritingService`, and add a new `提示词` settings page in `horizon-trace`. A `null` or missing override means the built-in prompt from `src/ai/prompts.py` remains active; user templates replace defaults instead of appending to them. The existing workbench `custom_prompt` remains a per-run insertion through `{custom_prompt_block}`.

**Tech Stack:** Python 3, FastAPI, Pydantic, pytest for `Horizon`; React 19, TypeScript, TanStack Router, Radix UI/shadcn components, Vitest and Testing Library for `horizon-trace`.

---

## File Structure

### Horizon Backend

- Modify: `src/models.py`
  - Add optional prompt configuration models:
    - `WritingPromptConfig`
    - `PromptsConfig`
  - Add optional `prompts: PromptsConfig | None` to `Config`.
- Create: `src/ai/writing_prompts.py`
  - Own prompt template metadata, defaults, variable validation, override resolution, and API serialization.
  - Keep `src/ai/prompts.py` as the raw prompt text source.
- Modify: `src/ai/writer.py`
  - Convert config prompt overrides into `WritingPrompts`.
  - Preserve existing injection-based tests by keeping `WritingService(ai_client, prompts=None)`.
- Modify: `src/api/schemas.py`
  - Add response schemas for prompt defaults/status.
- Modify: `src/api/routes/config.py`
  - Add `GET /config/prompt-defaults` so the desktop UI can show built-in defaults and required variables.
- Modify: `src/core/config_service.py`
  - Validate writing prompt templates during `/config/validate` and `/config` save.
- Modify: `docs/configuration.md`
  - Document the `prompts.writing` config section.
- Test: `tests/test_writer_service.py`
  - Verify prompt overrides replace built-ins and validation rejects invalid templates.
- Test: `tests/test_config_api.py`
  - Verify prompt config round-trip, invalid template rejection, and defaults endpoint.

### horizon-trace Frontend

- Modify: `src/renderer/lib/api/types.ts`
  - Add `prompts.writing` to `HorizonConfig`.
  - Add prompt-default response types.
- Modify: `src/renderer/lib/api/client.ts`
  - Add `getPromptDefaults()`.
- Test: `src/renderer/lib/api/client.test.ts`
  - Verify the new API method calls `/config/prompt-defaults`.
- Create: `src/renderer/features/settings/promptSettingsModel.ts`
  - Define prompt field metadata, validation, and config merge helpers.
- Test: `src/renderer/features/settings/promptSettingsModel.test.ts`
  - Verify variable validation and null-for-default config payloads.
- Create: `src/renderer/features/settings/PromptSettingsView.tsx`
  - New settings UI for report, single blog, and compile blog prompt editing.
- Test: `src/renderer/features/settings/PromptSettingsView.test.tsx`
  - Verify loading defaults/current overrides, saving, restoring default, and validation blocking.
- Modify: `src/renderer/routes/paths.ts`
  - Add `promptSettings: '/settings/prompts'`.
- Modify: `src/renderer/routes/router.tsx`
  - Add prompt settings route.
- Modify: `src/renderer/features/settings/SettingsLayout.tsx`
  - Add `提示词` nav item using a lucide icon such as `SquarePen` or `MessagesSquare`.
- Test: `src/renderer/routes/paths.test.ts`
  - Update route contract.

---

## Data Model

Backend config shape:

```json
{
  "prompts": {
    "writing": {
      "report_system": null,
      "report_user_template": null,
      "blog_system": null,
      "blog_user_template": null,
      "blog_compile_user_template": null
    }
  }
}
```

Meaning:

- `null`, missing `prompts`, or missing `prompts.writing`: use built-in defaults.
- A non-empty string: replace that specific built-in prompt.
- Empty or whitespace-only strings must normalize to `null` in the frontend before saving.

Allowed variables:

```python
REPORT_USER_TEMPLATE_VARIABLES = {
    "length_label",
    "style_label",
    "time_range_label",
    "language_label",
    "item_count",
    "custom_prompt_block",
    "items_json",
}

BLOG_USER_TEMPLATE_VARIABLES = {
    "length_label",
    "style_label",
    "language_label",
    "custom_prompt_block",
    "items_json",
}

BLOG_COMPILE_USER_TEMPLATE_VARIABLES = {
    "item_count",
    "length_label",
    "style_label",
    "language_label",
    "custom_prompt_block",
    "items_json",
}
```

Required variables:

```python
REPORT_USER_TEMPLATE_REQUIRED = {"items_json"}
BLOG_USER_TEMPLATE_REQUIRED = {"items_json"}
BLOG_COMPILE_USER_TEMPLATE_REQUIRED = {"items_json", "item_count"}
```

`{custom_prompt_block}` is recommended but not required. If users remove it, the workbench one-off custom prompt will not be inserted for that template.

---

## Task 1: Backend Prompt Override Model and Validation

**Files:**
- Modify: `src/models.py`
- Create: `src/ai/writing_prompts.py`
- Test: `tests/test_writer_service.py`

- [ ] **Step 1: Add failing tests for override resolution and variable validation**

Append these tests to `tests/test_writer_service.py`:

```python
import pytest

from src.ai.writer import create_writing_prompts
from src.models import PromptsConfig, WritingPromptConfig


def test_create_writing_prompts_uses_writing_prompt_overrides():
    prompts = create_writing_prompts(
        PromptsConfig(
            writing=WritingPromptConfig(
                report_system="Custom report system",
                report_user_template="Report {items_json}",
                blog_system="Custom blog system",
                blog_user_template="Blog {items_json}",
                blog_compile_user_template="Compile {item_count} {items_json}",
            )
        )
    )

    assert prompts.report_system == "Custom report system"
    assert prompts.report_user_template == "Report {items_json}"
    assert prompts.blog_system == "Custom blog system"
    assert prompts.blog_user_template == "Blog {items_json}"
    assert prompts.blog_compile_user_template == "Compile {item_count} {items_json}"


def test_create_writing_prompts_falls_back_to_defaults_for_missing_overrides():
    prompts = create_writing_prompts(PromptsConfig(writing=WritingPromptConfig()))

    assert "senior editor" in prompts.report_system
    assert "{items_json}" in prompts.report_user_template
    assert "technical blog editor" in prompts.blog_system
    assert "{items_json}" in prompts.blog_user_template
    assert "{item_count}" in prompts.blog_compile_user_template


def test_create_writing_prompts_rejects_unknown_template_variables():
    with pytest.raises(ValueError, match="Unknown variable"):
        create_writing_prompts(
            PromptsConfig(
                writing=WritingPromptConfig(
                    report_user_template="Report {items_json} {unknown_variable}"
                )
            )
        )


def test_create_writing_prompts_rejects_missing_required_template_variables():
    with pytest.raises(ValueError, match="Missing required variable"):
        create_writing_prompts(
            PromptsConfig(
                writing=WritingPromptConfig(
                    blog_compile_user_template="Compile {item_count}"
                )
            )
        )
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
uv run pytest tests/test_writer_service.py -q
```

Expected: FAIL because `create_writing_prompts`, `PromptsConfig`, and `WritingPromptConfig` do not exist.

- [ ] **Step 3: Add prompt config models**

In `src/models.py`, add these models after `DomainConfig` and before `Config`:

```python
class WritingPromptConfig(BaseModel):
    """Optional user overrides for report and blog writing prompts."""

    report_system: Optional[str] = None
    report_user_template: Optional[str] = None
    blog_system: Optional[str] = None
    blog_user_template: Optional[str] = None
    blog_compile_user_template: Optional[str] = None


class PromptsConfig(BaseModel):
    """Optional prompt customization config."""

    writing: Optional[WritingPromptConfig] = None
```

Then add this field to `Config`:

```python
    prompts: Optional[PromptsConfig] = None
```

- [ ] **Step 4: Create backend prompt helper module**

Create `src/ai/writing_prompts.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from string import Formatter

from src.ai.prompts import (
    BLOG_COMPILE_USER_PROMPT_TEMPLATE,
    BLOG_SYSTEM_PROMPT,
    BLOG_USER_PROMPT_TEMPLATE,
    REPORT_SYSTEM_PROMPT,
    REPORT_USER_PROMPT_TEMPLATE,
)
from src.models import PromptsConfig, WritingPromptConfig


REPORT_USER_TEMPLATE_VARIABLES = {
    "length_label",
    "style_label",
    "time_range_label",
    "language_label",
    "item_count",
    "custom_prompt_block",
    "items_json",
}
BLOG_USER_TEMPLATE_VARIABLES = {
    "length_label",
    "style_label",
    "language_label",
    "custom_prompt_block",
    "items_json",
}
BLOG_COMPILE_USER_TEMPLATE_VARIABLES = {
    "item_count",
    "length_label",
    "style_label",
    "language_label",
    "custom_prompt_block",
    "items_json",
}

REPORT_USER_TEMPLATE_REQUIRED = {"items_json"}
BLOG_USER_TEMPLATE_REQUIRED = {"items_json"}
BLOG_COMPILE_USER_TEMPLATE_REQUIRED = {"items_json", "item_count"}


@dataclass(frozen=True)
class WritingPrompts:
    report_system: str = REPORT_SYSTEM_PROMPT
    report_user_template: str = REPORT_USER_PROMPT_TEMPLATE
    blog_system: str = BLOG_SYSTEM_PROMPT
    blog_user_template: str = BLOG_USER_PROMPT_TEMPLATE
    blog_compile_user_template: str = BLOG_COMPILE_USER_PROMPT_TEMPLATE


def create_writing_prompts(config: PromptsConfig | None) -> WritingPrompts:
    writing = config.writing if config else None
    prompts = WritingPrompts(
        report_system=_override(writing.report_system if writing else None, REPORT_SYSTEM_PROMPT),
        report_user_template=_override(
            writing.report_user_template if writing else None,
            REPORT_USER_PROMPT_TEMPLATE,
        ),
        blog_system=_override(writing.blog_system if writing else None, BLOG_SYSTEM_PROMPT),
        blog_user_template=_override(
            writing.blog_user_template if writing else None,
            BLOG_USER_PROMPT_TEMPLATE,
        ),
        blog_compile_user_template=_override(
            writing.blog_compile_user_template if writing else None,
            BLOG_COMPILE_USER_PROMPT_TEMPLATE,
        ),
    )
    validate_writing_prompts(prompts)
    return prompts


def validate_writing_prompts(prompts: WritingPrompts) -> None:
    _validate_template(
        "report_user_template",
        prompts.report_user_template,
        REPORT_USER_TEMPLATE_VARIABLES,
        REPORT_USER_TEMPLATE_REQUIRED,
    )
    _validate_template(
        "blog_user_template",
        prompts.blog_user_template,
        BLOG_USER_TEMPLATE_VARIABLES,
        BLOG_USER_TEMPLATE_REQUIRED,
    )
    _validate_template(
        "blog_compile_user_template",
        prompts.blog_compile_user_template,
        BLOG_COMPILE_USER_TEMPLATE_VARIABLES,
        BLOG_COMPILE_USER_TEMPLATE_REQUIRED,
    )


def writing_prompt_defaults() -> dict:
    return {
        "writing": {
            "report_system": {
                "default": REPORT_SYSTEM_PROMPT,
                "required_variables": [],
                "allowed_variables": [],
            },
            "report_user_template": {
                "default": REPORT_USER_PROMPT_TEMPLATE,
                "required_variables": sorted(REPORT_USER_TEMPLATE_REQUIRED),
                "allowed_variables": sorted(REPORT_USER_TEMPLATE_VARIABLES),
            },
            "blog_system": {
                "default": BLOG_SYSTEM_PROMPT,
                "required_variables": [],
                "allowed_variables": [],
            },
            "blog_user_template": {
                "default": BLOG_USER_PROMPT_TEMPLATE,
                "required_variables": sorted(BLOG_USER_TEMPLATE_REQUIRED),
                "allowed_variables": sorted(BLOG_USER_TEMPLATE_VARIABLES),
            },
            "blog_compile_user_template": {
                "default": BLOG_COMPILE_USER_PROMPT_TEMPLATE,
                "required_variables": sorted(BLOG_COMPILE_USER_TEMPLATE_REQUIRED),
                "allowed_variables": sorted(BLOG_COMPILE_USER_TEMPLATE_VARIABLES),
            },
        }
    }


def _override(value: str | None, default: str) -> str:
    if value is None:
        return default
    stripped = value.strip()
    return stripped or default


def _template_variables(template: str) -> set[str]:
    variables = set()
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            variables.add(field_name.split(".", 1)[0].split("[", 1)[0])
    return variables


def _validate_template(
    name: str,
    template: str,
    allowed_variables: set[str],
    required_variables: set[str],
) -> None:
    variables = _template_variables(template)
    unknown = variables - allowed_variables
    if unknown:
        raise ValueError(f"Unknown variable in {name}: {', '.join(sorted(unknown))}")

    missing = required_variables - variables
    if missing:
        raise ValueError(f"Missing required variable in {name}: {', '.join(sorted(missing))}")
```

- [ ] **Step 5: Wire helper exports into writer module**

In `src/ai/writer.py`, remove the local `WritingPrompts` dataclass and prompt imports, then import the helper objects:

```python
from src.ai.writing_prompts import WritingPrompts, create_writing_prompts
```

Keep `WritingPrompts` import available because tests and constructor typing use it.

- [ ] **Step 6: Run the focused test and verify it passes**

Run:

```bash
uv run pytest tests/test_writer_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit backend prompt helper**

```bash
git add src/models.py src/ai/writing_prompts.py src/ai/writer.py tests/test_writer_service.py
git commit -m "feat: add writing prompt override model"
```

---

## Task 2: Backend Config API and Writing Service Integration

**Files:**
- Modify: `src/ai/writer.py`
- Modify: `src/api/schemas.py`
- Modify: `src/api/routes/config.py`
- Modify: `src/core/config_service.py`
- Modify: `src/api/routes/writing.py`
- Test: `tests/test_config_api.py`
- Test: `tests/test_writing_api.py`

- [ ] **Step 1: Add failing config API tests**

Append these tests to `tests/test_config_api.py`:

```python
def test_post_config_accepts_writing_prompt_overrides(tmp_path):
    s = settings(tmp_path)
    s.data_dir.mkdir()
    config = minimal_config()
    config["prompts"] = {
        "writing": {
            "report_system": "Custom report system",
            "report_user_template": "Report {items_json}",
            "blog_system": "Custom blog system",
            "blog_user_template": "Blog {items_json}",
            "blog_compile_user_template": "Compile {item_count} {items_json}",
        }
    }
    client = TestClient(create_app(s))

    response = client.post("/config", json=config)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["prompts"]["writing"]["report_system"] == "Custom report system"
    saved = json.loads(s.config_path.read_text(encoding="utf-8"))
    assert saved["prompts"]["writing"]["blog_compile_user_template"] == "Compile {item_count} {items_json}"


def test_prompt_defaults_endpoint_returns_writing_defaults(tmp_path):
    client = TestClient(create_app(settings(tmp_path)))

    response = client.get("/config/prompt-defaults")

    assert response.status_code == 200
    data = response.json()["data"]["writing"]
    assert "senior editor" in data["report_system"]["default"]
    assert "technical blog editor" in data["blog_system"]["default"]
    assert "items_json" in data["report_user_template"]["required_variables"]
    assert "item_count" in data["blog_compile_user_template"]["required_variables"]


def test_validate_config_rejects_invalid_writing_prompt_template(tmp_path):
    config = minimal_config()
    config["prompts"] = {
        "writing": {
            "report_user_template": "Report {items_json} {unknown_variable}"
        }
    }
    client = TestClient(create_app(settings(tmp_path)))

    response = client.post("/config/validate", json=config)

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert response.json()["errorCode"] == 2002
```

- [ ] **Step 2: Add failing writing API integration test**

Append this test to `tests/test_writing_api.py`:

```python
def test_writing_route_builds_service_with_prompt_overrides(tmp_path):
    app = create_app(settings(tmp_path))
    seed(app)
    app.state.settings.config_path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "version": "1.0",
        "ai": {"provider": "openai", "model": "gpt-4", "api_key": "sk-local"},
        "sources": {
            "github": [],
            "hackernews": {"enabled": False},
            "rss": [],
            "reddit": {"enabled": False, "subreddits": [], "users": []},
            "telegram": {"enabled": False, "channels": []},
        },
        "filtering": {"ai_score_threshold": 7.0, "time_window_hours": 24},
        "prompts": {
            "writing": {
                "report_system": "Custom report system",
                "report_user_template": "Custom report {items_json}",
            }
        },
    }
    app.state.settings.config_path.write_text(json.dumps(config), encoding="utf-8")
    captured = {}

    class FakeCreatedWritingService:
        def __init__(self, prompts):
            captured["prompts"] = prompts

        async def compose_report(self, items, params):
            return "# Generated"

    def fake_factory(ai_config, prompts_config=None):
        from src.ai.writer import create_writing_prompts

        return FakeCreatedWritingService(create_writing_prompts(prompts_config))

    import src.api.routes.writing as writing_route

    original = writing_route.create_writing_service
    writing_route.create_writing_service = fake_factory
    try:
        client = TestClient(app)
        response = client.post(
            "/write/report",
            json={
                "time_range": "custom",
                "start_date": "2026-05-01",
                "end_date": "2026-05-31",
                "style": "professional",
                "language": "zh",
                "item_ids": ["rss:1"],
            },
        )
    finally:
        writing_route.create_writing_service = original

    assert response.status_code == 200
    assert captured["prompts"].report_system == "Custom report system"
    assert captured["prompts"].report_user_template == "Custom report {items_json}"
```

- [ ] **Step 3: Run focused tests and verify they fail**

Run:

```bash
uv run pytest tests/test_config_api.py tests/test_writing_api.py::test_writing_route_builds_service_with_prompt_overrides -q
```

Expected: FAIL because `/config/prompt-defaults`, prompt template validation during config validation, and `create_writing_service(..., prompts_config=...)` do not exist yet.

- [ ] **Step 4: Add API schemas**

In `src/api/schemas.py`, after `ConfigValidationData`, add:

```python
class PromptFieldDefaults(BaseModel):
    default: str
    required_variables: list[str] = Field(default_factory=list)
    allowed_variables: list[str] = Field(default_factory=list)


class WritingPromptDefaultsData(BaseModel):
    report_system: PromptFieldDefaults
    report_user_template: PromptFieldDefaults
    blog_system: PromptFieldDefaults
    blog_user_template: PromptFieldDefaults
    blog_compile_user_template: PromptFieldDefaults


class PromptDefaultsData(BaseModel):
    writing: WritingPromptDefaultsData
```

- [ ] **Step 5: Add defaults endpoint**

In `src/api/routes/config.py`, import the schema and helper:

```python
from src.ai.writing_prompts import writing_prompt_defaults
from src.api.schemas import ApiResponse, ConfigValidationData, PromptDefaultsData, ok
```

Add this route after `get_config`:

```python
@router.get(
    "/prompt-defaults",
    response_model=ApiResponse[PromptDefaultsData],
    summary="Get built-in prompt defaults",
)
def get_prompt_defaults() -> dict:
    return ok(writing_prompt_defaults())
```

- [ ] **Step 6: Pass prompt config into writing service factory**

In `src/core/config_service.py`, import:

```python
from src.ai.writing_prompts import create_writing_prompts
```

Update `validate_config` so prompt templates are validated before the config is accepted:

```python
    @capture_service_errors("config", ErrorCode.CONFIG_VALIDATION_FAILED)
    def validate_config(self, payload: dict) -> Config:
        try:
            config = Config.model_validate(payload)
            create_writing_prompts(config.prompts)
            return config
        except ValidationError as exc:
            raise HorizonApiError(ErrorCode.CONFIG_VALIDATION_FAILED, "Config validation failed") from exc
        except ValueError as exc:
            raise HorizonApiError(ErrorCode.CONFIG_VALIDATION_FAILED, str(exc)) from exc
```

In `src/ai/writer.py`, change `create_writing_service` to accept prompt config:

```python
from src.models import AIConfig, PromptsConfig


def create_writing_service(config: AIConfig, prompts_config: PromptsConfig | None = None) -> "WritingService":
    return WritingService(
        create_ai_client(build_writing_ai_config(config)),
        prompts=create_writing_prompts(prompts_config),
    )
```

In `src/api/routes/writing.py`, update `_get_writing_service`:

```python
def _get_writing_service(request: Request):
    injected = getattr(request.app.state, "writing_service", None)
    if injected is not None:
        return injected

    config = ConfigService(request.app.state.config_path).get_config()
    return create_writing_service(config.ai, config.prompts)
```

- [ ] **Step 7: Run focused tests and verify they pass**

Run:

```bash
uv run pytest tests/test_config_api.py tests/test_writer_service.py tests/test_writing_api.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit backend API integration**

```bash
git add src/api/schemas.py src/api/routes/config.py src/core/config_service.py src/api/routes/writing.py src/ai/writer.py tests/test_config_api.py tests/test_writing_api.py
git commit -m "feat: expose writing prompt customization"
```

---

## Task 3: Frontend API Types and Prompt Settings Model

**Files:**
- Modify: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/lib/api/types.ts`
- Modify: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/lib/api/client.ts`
- Test: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/lib/api/client.test.ts`
- Create: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/features/settings/promptSettingsModel.ts`
- Test: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/features/settings/promptSettingsModel.test.ts`

- [ ] **Step 1: Add failing API client test**

Append this test to `horizon-trace/src/renderer/lib/api/client.test.ts`:

```typescript
  it('fetches built-in writing prompt defaults', async () => {
    const requests: Array<Parameters<AxiosAdapter>[0]> = []
    const adapter: AxiosAdapter = async (config) => {
      requests.push(config)
      return {
        data: {
          code: 200,
          success: true,
          data: {
            writing: {
              report_system: { default: 'Report system', required_variables: [], allowed_variables: [] },
              report_user_template: { default: 'Report {items_json}', required_variables: ['items_json'], allowed_variables: ['items_json'] },
              blog_system: { default: 'Blog system', required_variables: [], allowed_variables: [] },
              blog_user_template: { default: 'Blog {items_json}', required_variables: ['items_json'], allowed_variables: ['items_json'] },
              blog_compile_user_template: { default: 'Compile {item_count} {items_json}', required_variables: ['items_json', 'item_count'], allowed_variables: ['items_json', 'item_count'] }
            }
          },
          errorCode: null,
          errorMessage: null
        },
        status: 200,
        statusText: 'OK',
        headers: {},
        config
      }
    }
    const client = createHorizonApiClient({ baseURL: 'http://localhost:8000', adapter })

    const defaults = await client.getPromptDefaults()

    expect(requests.map((request) => [request.method, request.url])).toEqual([
      ['get', '/config/prompt-defaults']
    ])
    expect(defaults.writing.report_user_template.default).toBe('Report {items_json}')
  })
```

- [ ] **Step 2: Add failing model tests**

Create `horizon-trace/src/renderer/features/settings/promptSettingsModel.test.ts`:

```typescript
import { describe, expect, it } from 'vitest'

import {
  buildPromptConfig,
  promptDraftFromConfig,
  validatePromptTemplate
} from './promptSettingsModel'

describe('prompt settings model', () => {
  it('loads missing prompt config as default-backed empty overrides', () => {
    const draft = promptDraftFromConfig({})

    expect(draft.report_system).toBe('')
    expect(draft.report_user_template).toBe('')
    expect(draft.blog_system).toBe('')
    expect(draft.blog_user_template).toBe('')
    expect(draft.blog_compile_user_template).toBe('')
  })

  it('normalizes blank overrides to null when saving', () => {
    const config = buildPromptConfig(
      {
        report_system: ' Custom ',
        report_user_template: '   ',
        blog_system: '',
        blog_user_template: 'Blog {items_json}',
        blog_compile_user_template: 'Compile {item_count} {items_json}'
      },
      { ai: { provider: 'openai', model: 'gpt-4' } }
    )

    expect(config.prompts?.writing?.report_system).toBe('Custom')
    expect(config.prompts?.writing?.report_user_template).toBeNull()
    expect(config.prompts?.writing?.blog_system).toBeNull()
    expect(config.prompts?.writing?.blog_user_template).toBe('Blog {items_json}')
  })

  it('rejects unknown variables and missing required variables', () => {
    expect(
      validatePromptTemplate('Report {items_json} {unknown}', ['items_json'], ['items_json'])
    ).toContain('存在不支持的变量：unknown')

    expect(validatePromptTemplate('Report body', ['items_json'], ['items_json'])).toContain(
      '缺少必要变量：items_json'
    )
  })

  it('ignores Python format escaped braces used by built-in templates', () => {
    expect(
      validatePromptTemplate('End with `[原文]({{url}})` and use {items_json}', ['items_json'], ['items_json'])
    ).toEqual([])
  })
})
```

- [ ] **Step 3: Run focused tests and verify they fail**

Run from `horizon-trace`:

```bash
pnpm exec vitest run src/renderer/lib/api/client.test.ts src/renderer/features/settings/promptSettingsModel.test.ts
```

Expected: FAIL because `getPromptDefaults` and `promptSettingsModel` do not exist.

- [ ] **Step 4: Add frontend API types**

In `horizon-trace/src/renderer/lib/api/types.ts`, add these interfaces after `HorizonConfig`:

```typescript
export interface WritingPromptOverrides {
  report_system?: string | null
  report_user_template?: string | null
  blog_system?: string | null
  blog_user_template?: string | null
  blog_compile_user_template?: string | null
}

export interface PromptFieldDefaults {
  default: string
  required_variables: string[]
  allowed_variables: string[]
}

export interface PromptDefaultsResponse {
  writing: {
    report_system: PromptFieldDefaults
    report_user_template: PromptFieldDefaults
    blog_system: PromptFieldDefaults
    blog_user_template: PromptFieldDefaults
    blog_compile_user_template: PromptFieldDefaults
  }
}
```

Add this optional section to `HorizonConfig`:

```typescript
  prompts?: {
    writing?: WritingPromptOverrides
  }
```

- [ ] **Step 5: Add frontend API method**

In `horizon-trace/src/renderer/lib/api/client.ts`, import `PromptDefaultsResponse`, add the method to `HorizonApiClient`:

```typescript
  getPromptDefaults(): Promise<PromptDefaultsResponse>
```

Then add implementation in the returned client:

```typescript
    getPromptDefaults: () => request('get', '/config/prompt-defaults'),
```

- [ ] **Step 6: Create prompt settings model**

Create `horizon-trace/src/renderer/features/settings/promptSettingsModel.ts`:

```typescript
import type { HorizonConfig, WritingPromptOverrides } from '@renderer/lib/api/types'

export type PromptFieldKey = keyof Required<WritingPromptOverrides>

export interface PromptSettingsDraft extends Record<PromptFieldKey, string> {}

export const PROMPT_FIELD_LABELS: Record<PromptFieldKey, string> = {
  report_system: '报告 System Prompt',
  report_user_template: '报告 User Template',
  blog_system: '博文 System Prompt',
  blog_user_template: '单篇博文 User Template',
  blog_compile_user_template: '汇编博文 User Template'
}

const FIELD_KEYS: PromptFieldKey[] = [
  'report_system',
  'report_user_template',
  'blog_system',
  'blog_user_template',
  'blog_compile_user_template'
]

export function promptDraftFromConfig(config: HorizonConfig): PromptSettingsDraft {
  const writing = config.prompts?.writing ?? {}
  return FIELD_KEYS.reduce((draft, key) => {
    draft[key] = writing[key] ?? ''
    return draft
  }, {} as PromptSettingsDraft)
}

export function buildPromptConfig(
  draft: PromptSettingsDraft,
  baseConfig: HorizonConfig = {}
): HorizonConfig {
  const writing = FIELD_KEYS.reduce((next, key) => {
    const value = draft[key].trim()
    next[key] = value || null
    return next
  }, {} as Required<WritingPromptOverrides>)

  return {
    ...baseConfig,
    prompts: {
      ...(baseConfig.prompts ?? {}),
      writing
    }
  }
}

export function validatePromptTemplate(
  template: string,
  allowedVariables: string[],
  requiredVariables: string[]
): string[] {
  const variables = extractTemplateVariables(template)
  const allowed = new Set(allowedVariables)
  const required = new Set(requiredVariables)
  const unknown = [...variables].filter((name) => !allowed.has(name))
  const missing = [...required].filter((name) => !variables.has(name))
  const errors: string[] = []
  if (unknown.length > 0) errors.push(`存在不支持的变量：${unknown.join(', ')}`)
  if (missing.length > 0) errors.push(`缺少必要变量：${missing.join(', ')}`)
  return errors
}

export function extractTemplateVariables(template: string): Set<string> {
  const variables = new Set<string>()
  for (let index = 0; index < template.length; index += 1) {
    if (template[index] !== '{') continue
    if (template[index + 1] === '{') {
      index += 1
      continue
    }
    const end = template.indexOf('}', index + 1)
    if (end === -1) break
    if (template[end + 1] === '}') {
      index = end + 1
      continue
    }
    const name = template.slice(index + 1, end)
    if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
      variables.add(name)
    }
    index = end
  }
  return variables
}
```

- [ ] **Step 7: Run focused tests and verify they pass**

Run from `horizon-trace`:

```bash
pnpm exec vitest run src/renderer/lib/api/client.test.ts src/renderer/features/settings/promptSettingsModel.test.ts
```

Expected: PASS.

- [ ] **Step 8: Commit frontend API/model**

```bash
cd /Users/mac/Desktop/HorizonDesktop/horizon-trace
git add src/renderer/lib/api/types.ts src/renderer/lib/api/client.ts src/renderer/lib/api/client.test.ts src/renderer/features/settings/promptSettingsModel.ts src/renderer/features/settings/promptSettingsModel.test.ts
git commit -m "feat(settings): add writing prompt settings model"
```

---

## Task 4: Frontend Prompt Settings Page and Routing

**Files:**
- Create: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/features/settings/PromptSettingsView.tsx`
- Test: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/features/settings/PromptSettingsView.test.tsx`
- Modify: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/routes/paths.ts`
- Modify: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/routes/router.tsx`
- Modify: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/features/settings/SettingsLayout.tsx`
- Test: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/routes/paths.test.ts`

- [ ] **Step 1: Add failing route contract test**

In `horizon-trace/src/renderer/routes/paths.test.ts`, update the first test expectation to include:

```typescript
      promptSettings: '/settings/prompts',
```

- [ ] **Step 2: Add failing prompt settings page tests**

Create `horizon-trace/src/renderer/features/settings/PromptSettingsView.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { horizonApi } from '@renderer/lib/api'

import { PromptSettingsView } from './PromptSettingsView'

vi.mock('@renderer/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@renderer/lib/api')>()
  return {
    ...actual,
    horizonApi: {
      getConfig: vi.fn(),
      getPromptDefaults: vi.fn(),
      validateConfig: vi.fn(),
      putConfig: vi.fn()
    }
  }
})

const getConfig = vi.mocked(horizonApi.getConfig)
const getPromptDefaults = vi.mocked(horizonApi.getPromptDefaults)
const validateConfig = vi.mocked(horizonApi.validateConfig)
const putConfig = vi.mocked(horizonApi.putConfig)

const defaults = {
  writing: {
    report_system: { default: 'Default report system', required_variables: [], allowed_variables: [] },
    report_user_template: {
      default: 'Default report {items_json}',
      required_variables: ['items_json'],
      allowed_variables: ['items_json', 'custom_prompt_block']
    },
    blog_system: { default: 'Default blog system', required_variables: [], allowed_variables: [] },
    blog_user_template: {
      default: 'Default blog {items_json}',
      required_variables: ['items_json'],
      allowed_variables: ['items_json', 'custom_prompt_block']
    },
    blog_compile_user_template: {
      default: 'Default compile {item_count} {items_json}',
      required_variables: ['items_json', 'item_count'],
      allowed_variables: ['items_json', 'item_count', 'custom_prompt_block']
    }
  }
}

describe('PromptSettingsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getConfig.mockResolvedValue({})
    getPromptDefaults.mockResolvedValue(defaults)
    validateConfig.mockResolvedValue(undefined)
    putConfig.mockResolvedValue({})
  })

  it('loads default writing prompts and current overrides', async () => {
    getConfig.mockResolvedValueOnce({
      prompts: { writing: { report_system: 'Custom report system' } }
    })

    render(<PromptSettingsView />)

    expect(await screen.findByRole('heading', { name: '提示词' })).toBeVisible()
    expect(screen.getByDisplayValue('Custom report system')).toBeVisible()
    expect(screen.getByText('Default report system')).toBeVisible()
  })

  it('saves edited writing prompt overrides without replacing other config', async () => {
    getConfig.mockResolvedValueOnce({
      ai: { provider: 'openai', model: 'gpt-4' },
      filtering: { ai_score_threshold: 8, time_window_hours: 24 }
    })
    render(<PromptSettingsView />)

    const reportSystem = await screen.findByLabelText('报告 System Prompt')
    await userEvent.clear(reportSystem)
    await userEvent.click(reportSystem)
    await userEvent.paste('Custom report system')
    await userEvent.click(screen.getByRole('button', { name: '保存提示词' }))

    await waitFor(() =>
      expect(putConfig).toHaveBeenCalledWith({
        ai: { provider: 'openai', model: 'gpt-4' },
        filtering: { ai_score_threshold: 8, time_window_hours: 24 },
        prompts: {
          writing: expect.objectContaining({
            report_system: 'Custom report system'
          })
        }
      })
    )
  })

  it('blocks saving invalid user template variables', async () => {
    render(<PromptSettingsView />)

    const reportTemplate = await screen.findByLabelText('报告 User Template')
    await userEvent.clear(reportTemplate)
    await userEvent.click(reportTemplate)
    await userEvent.paste('Broken {unknown}')
    await userEvent.click(screen.getByRole('button', { name: '保存提示词' }))

    expect(await screen.findByText(/存在不支持的变量/)).toBeVisible()
    expect(validateConfig).not.toHaveBeenCalled()
    expect(putConfig).not.toHaveBeenCalled()
  })

  it('restores a field to default by clearing its override', async () => {
    getConfig.mockResolvedValueOnce({
      prompts: { writing: { report_system: 'Custom report system' } }
    })
    render(<PromptSettingsView />)

    await userEvent.click(await screen.findByRole('button', { name: '还原报告 System Prompt' }))
    await userEvent.click(screen.getByRole('button', { name: '保存提示词' }))

    await waitFor(() =>
      expect(putConfig).toHaveBeenCalledWith({
        prompts: {
          writing: expect.objectContaining({
            report_system: null
          })
        }
      })
    )
  })
})
```

- [ ] **Step 3: Run focused tests and verify they fail**

Run from `horizon-trace`:

```bash
pnpm exec vitest run src/renderer/routes/paths.test.ts src/renderer/features/settings/PromptSettingsView.test.tsx
```

Expected: FAIL because the route and view do not exist.

- [ ] **Step 4: Add prompt settings route constants**

In `horizon-trace/src/renderer/routes/paths.ts`, add:

```typescript
  promptSettings: '/settings/prompts',
```

Import a suitable icon in `SettingsLayout.tsx`:

```typescript
import { ArrowLeft, Bot, Crosshair, Rss, Send, Settings2, SquarePen } from 'lucide-react'
```

Add this item after `AI 配置`:

```typescript
  { label: '提示词', to: APP_ROUTES.promptSettings, icon: SquarePen },
```

- [ ] **Step 5: Add router entry**

In `horizon-trace/src/renderer/routes/router.tsx`, import:

```typescript
import { PromptSettingsView } from '../features/settings/PromptSettingsView'
```

Add route:

```typescript
const promptSettingsRoute = createRoute({ getParentRoute: () => settingsRoute, path: '/prompts', component: PromptSettingsView })
```

Add it to `settingsRoute.addChildren([...])` after `aiSettingsRoute`.

- [ ] **Step 6: Create prompt settings view**

Create `horizon-trace/src/renderer/features/settings/PromptSettingsView.tsx`:

```typescript
import * as React from 'react'

import { Alert, AlertDescription, AlertTitle } from '@renderer/components/ui/alert'
import { Button } from '@renderer/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@renderer/components/ui/tabs'
import { Textarea } from '@renderer/components/ui/textarea'
import { HorizonApiError, horizonApi, type HorizonConfig, type PromptDefaultsResponse } from '@renderer/lib/api'

import {
  buildPromptConfig,
  PROMPT_FIELD_LABELS,
  promptDraftFromConfig,
  type PromptFieldKey,
  type PromptSettingsDraft,
  validatePromptTemplate
} from './promptSettingsModel'

type StatusTone = 'idle' | 'saving' | 'success' | 'error'

interface Status {
  tone: StatusTone
  title: string
  description: string
}

const initialStatus: Status = {
  tone: 'idle',
  title: '等待保存',
  description: '自定义提示词会替换内置写作模板；留空则使用默认提示词。'
}

const emptyDraft: PromptSettingsDraft = {
  report_system: '',
  report_user_template: '',
  blog_system: '',
  blog_user_template: '',
  blog_compile_user_template: ''
}

const TAB_FIELDS: Record<string, PromptFieldKey[]> = {
  report: ['report_system', 'report_user_template'],
  blog: ['blog_system', 'blog_user_template'],
  compile: ['blog_compile_user_template']
}

export function PromptSettingsView(): React.JSX.Element {
  const [draft, setDraft] = React.useState<PromptSettingsDraft>(emptyDraft)
  const [loadedConfig, setLoadedConfig] = React.useState<HorizonConfig>({})
  const [defaults, setDefaults] = React.useState<PromptDefaultsResponse | null>(null)
  const [errors, setErrors] = React.useState<Record<string, string[]>>({})
  const [status, setStatus] = React.useState<Status>(initialStatus)

  React.useEffect(() => {
    let isMounted = true
    Promise.all([horizonApi.getConfig(), horizonApi.getPromptDefaults()])
      .then(([config, promptDefaults]) => {
        if (!isMounted) return
        setLoadedConfig(config)
        setDefaults(promptDefaults)
        setDraft(promptDraftFromConfig(config))
      })
      .catch(() => {
        if (!isMounted) return
        setStatus({
          tone: 'error',
          title: '加载失败',
          description: '暂时无法读取本地提示词配置，请确认 Horizon Trace 本地服务正在运行。'
        })
      })
    return () => {
      isMounted = false
    }
  }, [])

  const updateField = (field: PromptFieldKey, value: string): void => {
    const nextDraft = { ...draft, [field]: value }
    setDraft(nextDraft)
    if (Object.keys(errors).length > 0 && defaults) {
      setErrors(validateDraft(nextDraft, defaults))
    }
  }

  const restoreField = (field: PromptFieldKey): void => {
    updateField(field, '')
  }

  const saveDraft = async (): Promise<void> => {
    if (!defaults) return
    const nextErrors = validateDraft(draft, defaults)
    setErrors(nextErrors)
    if (Object.values(nextErrors).some((items) => items.length > 0)) {
      setStatus({ tone: 'error', title: '保存失败', description: '请先修正模板变量错误。' })
      return
    }

    setStatus({ tone: 'saving', title: '正在保存提示词', description: '正在验证并写入本地服务。' })
    try {
      const config = buildPromptConfig(draft, loadedConfig)
      await horizonApi.validateConfig(config)
      const saved = await horizonApi.putConfig(config)
      setLoadedConfig(saved)
      setDraft(promptDraftFromConfig(saved))
      setStatus({ tone: 'success', title: '提示词已保存', description: '报告和博文生成会使用新的写作提示词。' })
    } catch (error) {
      const description =
        error instanceof HorizonApiError
          ? '本地服务没有接受当前提示词，请检查模板变量后重试。'
          : '暂时连接不上本地服务，请稍后重试。'
      setStatus({ tone: 'error', title: '保存失败', description })
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-xl font-semibold">提示词</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          自定义报告和博文的写作提示词。评分与富化提示词由系统维护。
        </p>
      </div>

      <Alert variant={status.tone === 'error' ? 'destructive' : 'default'}>
        <AlertTitle>{status.title}</AlertTitle>
        <AlertDescription>{status.description}</AlertDescription>
      </Alert>

      <Tabs defaultValue="report" className="gap-6">
        <TabsList>
          <TabsTrigger value="report">日/周报</TabsTrigger>
          <TabsTrigger value="blog">单篇博文</TabsTrigger>
          <TabsTrigger value="compile">汇编博文</TabsTrigger>
        </TabsList>

        {Object.entries(TAB_FIELDS).map(([tab, fields]) => (
          <TabsContent key={tab} value={tab} className="space-y-5">
            {fields.map((field) => (
              <PromptEditor
                key={field}
                field={field}
                value={draft[field]}
                defaultValue={defaults?.writing[field].default ?? ''}
                errors={errors[field] ?? []}
                onChange={(value) => updateField(field, value)}
                onRestore={() => restoreField(field)}
              />
            ))}
          </TabsContent>
        ))}
      </Tabs>

      <div className="flex justify-end">
        <Button onClick={() => void saveDraft()} disabled={status.tone === 'saving'}>
          {status.tone === 'saving' ? '保存中...' : '保存提示词'}
        </Button>
      </div>
    </div>
  )
}

function PromptEditor({
  field,
  value,
  defaultValue,
  errors,
  onChange,
  onRestore
}: {
  field: PromptFieldKey
  value: string
  defaultValue: string
  errors: string[]
  onChange: (value: string) => void
  onRestore: () => void
}): React.JSX.Element {
  const label = PROMPT_FIELD_LABELS[field]
  const textAreaId = `prompt-${field}`
  return (
    <section className="grid gap-3 rounded-lg border border-border px-4 py-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <label htmlFor={textAreaId} className="text-sm font-medium">
            {label}
          </label>
          <p className="mt-0.5 text-xs text-muted-foreground">
            留空使用默认提示词；填写内容会替换默认提示词。
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onRestore} aria-label={`还原${label}`}>
          还原默认
        </Button>
      </div>

      <Textarea
        id={textAreaId}
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={defaultValue}
        rows={field.includes('template') ? 10 : 5}
        className="font-mono text-xs leading-relaxed"
        aria-invalid={errors.length > 0}
      />

      {errors.length > 0 && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {errors.join('；')}
        </div>
      )}

      <details open className="rounded-md bg-muted/35 px-3 py-2">
        <summary className="cursor-default text-xs font-medium text-muted-foreground">默认提示词</summary>
        <pre className="mt-2 whitespace-pre-wrap break-words text-xs leading-relaxed text-foreground">
          {defaultValue}
        </pre>
      </details>
    </section>
  )
}

function validateDraft(
  draft: PromptSettingsDraft,
  defaults: PromptDefaultsResponse
): Record<string, string[]> {
  return {
    report_system: [],
    report_user_template: validatePromptTemplate(
      draft.report_user_template || defaults.writing.report_user_template.default,
      defaults.writing.report_user_template.allowed_variables,
      defaults.writing.report_user_template.required_variables
    ),
    blog_system: [],
    blog_user_template: validatePromptTemplate(
      draft.blog_user_template || defaults.writing.blog_user_template.default,
      defaults.writing.blog_user_template.allowed_variables,
      defaults.writing.blog_user_template.required_variables
    ),
    blog_compile_user_template: validatePromptTemplate(
      draft.blog_compile_user_template || defaults.writing.blog_compile_user_template.default,
      defaults.writing.blog_compile_user_template.allowed_variables,
      defaults.writing.blog_compile_user_template.required_variables
    )
  }
}
```

- [ ] **Step 7: Run focused tests and verify they pass**

Run from `horizon-trace`:

```bash
pnpm exec vitest run src/renderer/routes/paths.test.ts src/renderer/features/settings/PromptSettingsView.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit prompt settings page**

```bash
cd /Users/mac/Desktop/HorizonDesktop/horizon-trace
git add src/renderer/features/settings/PromptSettingsView.tsx src/renderer/features/settings/PromptSettingsView.test.tsx src/renderer/routes/paths.ts src/renderer/routes/router.tsx src/renderer/features/settings/SettingsLayout.tsx src/renderer/routes/paths.test.ts
git commit -m "feat(settings): add writing prompt editor"
```

---

## Task 5: Documentation and Full Verification

**Files:**
- Modify: `docs/configuration.md`
- Optional modify: `/Users/mac/Desktop/HorizonDesktop/horizon-trace/src/renderer/features/productCopy.test.ts` only if the product-copy guard rejects new visible text.

- [ ] **Step 1: Document writing prompt customization**

In `docs/configuration.md`, after the AI throttling section, add:

```markdown
### Writing prompt customization

Horizon Trace lets desktop users customize the prompts used for report and blog drafting. These settings live under `prompts.writing` in `~/.horizon/settings.json`.

`null` or a missing field means Horizon uses the built-in default prompt. A string replaces that specific built-in prompt.

```json
{
  "prompts": {
    "writing": {
      "report_system": "You are a concise technical editor.",
      "report_user_template": "Write a report from these items:\n{items_json}",
      "blog_system": null,
      "blog_user_template": null,
      "blog_compile_user_template": null
    }
  }
}
```

User templates are Python format strings. Report templates receive `length_label`, `style_label`, `time_range_label`, `language_label`, `item_count`, `custom_prompt_block`, and `items_json`. Blog templates receive `length_label`, `style_label`, `language_label`, `custom_prompt_block`, and `items_json`; compile blog templates also receive `item_count`.

The existing workbench custom prompt remains a per-generation requirement block inserted through `{custom_prompt_block}` when the active user template includes that variable.
```

- [ ] **Step 2: Run backend verification**

Run from `Horizon`:

```bash
uv run pytest tests/test_config_api.py tests/test_writer_service.py tests/test_writing_api.py -q
```

Expected: PASS.

Then run the broader backend suite if local time allows:

```bash
uv run pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend verification**

Run from `horizon-trace`:

```bash
pnpm run typecheck
pnpm exec vitest run src/renderer/lib/api/client.test.ts src/renderer/features/settings/promptSettingsModel.test.ts src/renderer/features/settings/PromptSettingsView.test.tsx src/renderer/routes/paths.test.ts
```

Expected: PASS.

Then run the broader renderer suite if local time allows:

```bash
pnpm run test:renderer
```

Expected: PASS.

- [ ] **Step 4: Build desktop app**

Run from `horizon-trace`:

```bash
pnpm exec electron-vite build --mode production
```

Expected: build completes and emits `out/main/index.js`, `out/preload/index.js`, and `out/renderer`.

- [ ] **Step 5: Commit docs and final verification changes**

```bash
cd /Users/mac/Desktop/HorizonDesktop/Horizon
git add docs/configuration.md
git commit -m "docs: describe writing prompt customization"
```

- [ ] **Step 6: Inspect final diffs**

Run:

```bash
cd /Users/mac/Desktop/HorizonDesktop/Horizon
git status --short
git log --oneline -5

cd /Users/mac/Desktop/HorizonDesktop/horizon-trace
git status --short
git log --oneline -5
```

Expected: only intentional changes remain. Note that `horizon-trace` may already contain unrelated local changes in `src/main/app-preferences.ts` and `src/main/app-preferences.test.ts`; do not revert them.

---

## Risk Notes

- Adding `Config.prompts` is broad because `Config` is imported widely. The field is optional and should be backward-compatible for existing `settings.json` files.
- User prompt templates can break runtime generation if variables are invalid. The backend helper validates unknown and missing required variables, while the frontend blocks invalid saves earlier.
- `custom_prompt_block` remains optional by design. Removing it from a user template disables the workbench one-off custom prompt for that template; this should be visible in UI copy or documentation.
- Scoring, concept extraction, and enrichment prompts remain hidden and unchanged.

## Self-Review

- Spec coverage: The plan covers editable report system/user prompt, blog system/user prompt, compile-blog user prompt, restore-default behavior, API defaults display, config persistence, and keeping scoring/enrichment hidden.
- Placeholder scan: No task contains TBD/TODO/later placeholders. Each implementation step includes concrete files, commands, and expected outcomes.
- Type consistency: Backend fields are `report_system`, `report_user_template`, `blog_system`, `blog_user_template`, and `blog_compile_user_template`; frontend uses the same snake_case keys throughout.
