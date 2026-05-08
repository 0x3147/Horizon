# Horizon Core FastAPI MVP 中文设计草案

> 状态：审阅草案
>
> 目标读者：后端二开实现者、未来 Electron 客户端实现者、项目维护者
>
> 当前阶段：先设计并审阅，不进入实现

## 1. 背景

当前 Horizon 已经具备完整的信息处理流水线：多源抓取、跨源 URL 去重、AI 打分、阈值过滤、语义去重、内容富化、日报生成、邮件/Webhook/MCP 输出。

但当前项目更像一次性 CLI 任务：

- 主 CLI 跑完后主要保存最终 Markdown 日报。
- 原始抓取内容、打分结果、过滤结果、富化结果没有统一持久化到本地数据库。
- 配置主要通过 `data/config.json` 手工维护。
- 没有面向未来客户端的本地 HTTP API。
- 没有本地内容库、运行历史、日志查询、定时运行管理。

我们的目标不是立刻做 Electron 客户端，而是先把 Horizon 改造成未来 Electron 可稳定调用的本地后端。

## 2. MVP 目标

本阶段构建一个本地个人客户端的后端基础，称为 Horizon Core FastAPI MVP。

MVP 需要做到：

- 引入 FastAPI 本地接口层。
- 引入 SQLite 本地数据库。
- 持久化每次 pipeline 运行记录。
- 持久化 raw、scored、filtered、enriched 等阶段内容。
- 支持按来源、分数、标签、阶段、关键词等条件查询内容。
- 通过接口读取、校验、更新 Horizon 配置。
- 支持 cron 表达式定时运行。
- 保留 Swagger UI 和 OpenAPI JSON，方便前端联调。
- 为未来 Electron 客户端预留“窗口关闭后后台继续运行”的进程模型。

MVP 不做：

- Electron 客户端。
- 账号体系。
- 云同步。
- 社区型 HorizonHub 功能。
- 远程多用户 API。
- OS 级后台服务。
- Electron 客户端和最终安装包。
- 复杂权限系统。
- 全文搜索引擎级能力。

## 3. 总体架构

推荐架构：

```text
FastAPI Local Server
├─ Config API
├─ Run API
├─ Item API
├─ Summary API
├─ Schedule API
├─ Log API
└─ Swagger / OpenAPI

Core Services
├─ PipelineService
├─ ConfigService
├─ QueryService
├─ ScheduleService
└─ StorageRepository

Storage
├─ data/config.json        # 开发默认
└─ data/horizon.db         # 开发默认

Existing Horizon Modules
├─ scrapers
├─ ContentAnalyzer
├─ ContentEnricher
├─ DailySummarizer
├─ HorizonOrchestrator
└─ MCP staged logic

Future Electron Client
└─ Calls FastAPI through localhost
```

设计原则：

- FastAPI 只作为薄接口层。
- 业务逻辑放在 service 层。
- 数据读写放在 repository/storage 层。
- 现有 Horizon 抓取、评分、富化、摘要逻辑尽量复用。
- SQLite 是本地个人客户端的主存储。
- `data/config.json` 继续作为兼容层，但不让未来 UI 直接改文件。
- 所有数据路径必须允许通过环境变量或启动参数覆盖，避免未来 Electron 打包时依赖源码目录。

## 4. 技术选型

### FastAPI

选择 FastAPI 的原因：

- 自带 Swagger UI 和 OpenAPI schema。
- 与 Pydantic 模型天然兼容。
- 适合未来 Electron 通过 HTTP 调用。
- 本地开发、调试、联调体验好。

默认暴露：

```text
GET /docs
GET /redoc
GET /openapi.json
```

### SQLite

选择 SQLite 的原因：

- 本地个人客户端足够使用。
- 无需额外服务。
- 便于 Electron 打包和迁移。
- 适合存储运行历史、内容库、摘要、调度计划。

### APScheduler

定时调度采用 APScheduler。

原因：

- 支持 cron trigger。
- 支持暂停、恢复、max instances、misfire 等任务语义。
- 比手写循环更可靠。

首版只支持标准 5 段 cron：

```text
minute hour day month weekday
```

不支持 6 段秒级 cron，也不支持 `@daily` 这类 shortcut。

## 5. 数据模型设计

数据库开发默认路径：

```text
data/horizon.db
```

未来 Electron 打包后不应写入源码目录，应由 Electron 主进程指定用户数据目录，例如：

```text
HORIZON_DATA_DIR=<electron userData>/horizon
HORIZON_DB_PATH=<electron userData>/horizon/horizon.db
HORIZON_CONFIG_PATH=<electron userData>/horizon/config.json
```

### runs

记录一次 pipeline 运行。

字段：

```text
id
status
hours
started_at
finished_at
config_snapshot_json
raw_count
scored_count
filtered_count
enriched_count
error_message
```

`status` 建议值：

```text
pending
running
fetching
scoring
filtering
deduplicating
enriching
summarizing
succeeded
failed
cancelled
```

### items

记录内容条目。

字段：

```text
id
run_id
source_type
source_name
native_id
title
url
content
author
published_at
fetched_at
metadata_json
stage
is_selected
duplicate_of_item_id
```

说明：

- `stage` 表示当前保存时所处阶段，如 `raw`、`scored`、`filtered`、`enriched`。
- `is_selected` 表示是否进入最终候选/日报。
- `metadata_json` 保存来源差异字段，避免 MVP 阶段过度拆表。

### item_analysis

记录 AI 分析结果。

字段：

```text
run_id
item_id
ai_score
ai_reason
ai_summary
ai_tags_json
detailed_summary_json
background_json
community_discussion_json
citations_json
```

说明：

- `ai_score` 需要结构化，便于筛选排序。
- `ai_tags_json` 可以先用 JSON 保存。
- 后续如果标签查询变复杂，再拆 `tags` 表。

### summaries

记录生成的日报。

字段：

```text
id
run_id
language
markdown
saved_path
created_at
```

### run_logs

记录运行日志。

字段：

```text
id
run_id
level
stage
message
created_at
```

### schedules

记录定时任务。

字段：

```text
id
name
enabled
cron_expr
cron_label
timezone
hours_window
source_filter_json
last_run_id
last_run_at
next_run_at
created_at
updated_at
```

说明：

- 后端只根据 `cron_expr` 执行。
- `cron_label` 只是 UI 展示，不参与业务逻辑。
- 前端未来可以把“每天早上 8 点”等 label 转换成 cron。
- 用户也可以自定义填写 cron。

## 6. API 设计

所有接口默认只监听本机：

```text
127.0.0.1
```

默认端口可先定为：

```text
8765
```

### Health

```text
GET /health
```

返回：

```json
{
  "code": 200,
  "success": true,
  "data": {
    "status": "ok"
  },
  "errorCode": null,
  "errorMessage": null
}
```

### Swagger / OpenAPI

```text
GET /docs
GET /redoc
GET /openapi.json
```

用途：

- `/docs` 给前端和后端手动联调。
- `/openapi.json` 给未来生成类型和 API client。

### 统一响应格式

所有业务 API 返回统一响应包络：

```ts
{
  code: number
  success: boolean
  data: T
  errorCode: number | null
  errorMessage: string | null
}
```

字段含义：

- `code`：HTTP 状态码或与 HTTP 状态一致的响应状态码，例如 `200`、`202`、`400`、`404`、`500`。
- `success`：业务是否成功。
- `data`：成功时的业务数据；失败时可为 `null`。
- `errorCode`：业务异常码；成功时为 `null`。
- `errorMessage`：业务异常信息；成功时为 `null`。

成功示例：

```json
{
  "code": 200,
  "success": true,
  "data": {
    "status": "ok"
  },
  "errorCode": null,
  "errorMessage": null
}
```

业务失败示例：

```json
{
  "code": 200,
  "success": false,
  "data": null,
  "errorCode": 3002,
  "errorMessage": "Cron expression must contain exactly 5 fields"
}
```

HTTP 异常示例：

```json
{
  "code": 404,
  "success": false,
  "data": null,
  "errorCode": 4001,
  "errorMessage": "Run not found"
}
```

职责区分：

- HTTP 状态码表达传输层、协议层、路由层结果。
- `errorCode` 和 `errorMessage` 表达业务异常。
- 业务可预期失败可以使用 HTTP 200 并设置 `success=false`。
- 路由不存在、请求体结构非法、服务内部崩溃等仍使用对应 HTTP 状态码。
- 前端业务判断优先看 `success` 和 `errorCode`，网络/协议判断看 HTTP 状态码。

实现建议：

- 定义统一响应模型 `ApiResponse[T]`。
- 定义业务异常类 `HorizonApiError`。
- 定义业务异常码枚举或常量表。
- 定义全局异常处理器，把业务异常转为统一响应。
- FastAPI 默认请求校验错误也应转为统一响应格式。
- 定义 service 层异常捕获装饰器，减少重复 try/except，并把未知异常转换为 `HorizonApiError`。

### 业务异常码

业务异常码按模块分段维护，避免随意新增难以追踪。

建议范围：

```text
1000-1999 通用错误
2000-2999 配置错误
3000-3999 调度错误
4000-4999 运行任务错误
5000-5999 内容查询错误
6000-6999 摘要错误
7000-7999 存储错误
```

MVP 初始异常码：

| errorCode | errorMessage | 场景 |
|---:|---|---|
| 1000 | Unknown error | 未分类内部错误 |
| 1001 | Invalid request | 请求参数语义非法 |
| 1002 | Resource not found | 通用资源不存在 |
| 2001 | Config file not found | 配置文件不存在 |
| 2002 | Config validation failed | 配置校验失败 |
| 2003 | Config save failed | 配置保存失败 |
| 3001 | Schedule not found | 定时任务不存在 |
| 3002 | Invalid cron expression | cron 表达式非法 |
| 3003 | Unsupported cron format | 不支持的 cron 格式，例如非 5 段 |
| 3004 | Invalid timezone | 时区非法 |
| 4001 | Run not found | 运行记录不存在 |
| 4002 | Run already in progress | 当前操作不允许，因为任务正在运行 |
| 4003 | Run cancellation failed | 取消任务失败 |
| 4004 | Pipeline execution failed | pipeline 执行失败 |
| 5001 | Item not found | 内容条目不存在 |
| 5002 | Invalid item query | 内容查询条件非法 |
| 6001 | Summary not found | 摘要不存在 |
| 6002 | Summary generation failed | 摘要生成失败 |
| 7001 | Database unavailable | 数据库不可用 |
| 7002 | Database write failed | 数据库写入失败 |

维护规则：

- 新增业务异常点必须先在异常码表中登记。
- 不同错误不要复用同一个业务码，除非前端处理方式完全一致。
- `errorMessage` 面向用户或前端调试，应清晰但不泄露密钥、token、完整堆栈。
- 详细异常堆栈只进入日志，不进入 API 响应。

### 异常捕获装饰器

为了减少 service/repository 中重复的异常捕获代码，MVP 需要设计一个异常捕获装饰器，例如：

```python
@capture_service_errors(module="schedule", default_error_code=3000)
def validate_cron(...):
    ...
```

或异步场景：

```python
@capture_service_errors(module="pipeline", default_error_code=4004)
async def run_pipeline(...):
    ...
```

职责：

- 捕获 service/repository 层未处理异常。
- 将已知异常映射为业务异常码。
- 将未知异常转换为 `HorizonApiError`。
- 记录原始异常和堆栈到日志。
- 保留原始异常 cause，方便排查。

不负责：

- 不直接返回 `ApiResponse`。
- 不直接决定 HTTP 状态码。
- 不在 route 层包装响应。
- 不吞掉任务取消类异常。

分层关系：

```text
Service / Repository
  ↓
capture_service_errors
  ↓
raise HorizonApiError
  ↓
FastAPI exception handler
  ↓
ApiResponse
```

异常处理规则：

1. 如果代码主动抛出 `HorizonApiError`，装饰器直接透传。
2. 如果捕获到已知异常，按映射转换为对应业务异常码。
3. 如果捕获到未知异常，转换为 `1000 Unknown error`。
4. 如果捕获到 `asyncio.CancelledError`，继续抛出，避免取消语义被吞掉。

建议的已知异常映射：

| Python 异常 | 业务异常码 | 说明 |
|---|---:|---|
| `FileNotFoundError` | 2001 | 配置或资源文件不存在 |
| `pydantic.ValidationError` | 2002 | 配置或请求数据校验失败 |
| `ValueError` in cron parsing | 3002 | cron 表达式非法 |
| `zoneinfo.ZoneInfoNotFoundError` | 3004 | 时区非法 |
| `sqlite3.OperationalError` | 7001 | 数据库不可用或 SQL 执行失败 |
| `sqlite3.DatabaseError` | 7002 | 数据库读写失败 |

实现约束：

- 装饰器需要同时支持同步函数和异步函数。
- 装饰器参数应允许指定默认错误码、模块名、阶段名。
- 装饰器只用于 service/repository 边界，不用于 FastAPI route 的正常响应包装。
- 业务上能明确判断的错误，应优先主动抛出 `HorizonApiError`，不要依赖未知异常兜底。

### Config API

```text
GET  /config
PUT  /config
POST /config/validate
```

设计原则：

- 配置仍保存到 `data/config.json`。
- 所有写入都经过 Pydantic 校验。
- 未来 UI 不直接修改 JSON 文件。
- MVP 不做配置备份文件、配置历史列表或配置恢复接口，行为接近常见客户端设置页：校验通过后保存当前配置。

MVP 实现：

```text
GET  /config
PUT  /config
POST /config/validate
```

### Run API

```text
POST /runs
GET  /runs
GET  /runs/{run_id}
POST /runs/{run_id}/cancel
GET  /runs/{run_id}/logs
```

`POST /runs` 不阻塞等待完整 pipeline 完成，而是：

1. 创建 run。
2. 写入 `pending/running` 状态。
3. 启动后台任务。
4. 立即返回 `run_id`。

前端通过轮询查询：

```text
GET /runs/{run_id}
GET /runs/{run_id}/logs
GET /items?run_id=...
```

取消运行采用协作式取消：

- 设置 cancel flag。
- 当前阶段完成后检查。
- 对已经发出的网络请求/AI 请求不强杀。

### Item API

```text
GET /items
GET /items/{item_id}
```

`GET /items` 支持查询参数：

```text
run_id
source_type
min_score
max_score
selected_only
stage
tag
q
published_after
published_before
limit
offset
```

`q` 首版使用 SQLite `LIKE` 搜索：

- title
- content
- ai_summary

后续如需要再引入 SQLite FTS5。

### Summary API

```text
GET  /summaries
GET  /runs/{run_id}/summaries
POST /runs/{run_id}/summaries
```

说明：

- `GET` 用于读取已生成日报。
- `POST` 可用于基于某个 run 重新生成指定语言的日报。

### Schedule API

```text
GET    /schedules
POST   /schedules
GET    /schedules/{schedule_id}
PUT    /schedules/{schedule_id}
DELETE /schedules/{schedule_id}
POST   /schedules/{schedule_id}/enable
POST   /schedules/{schedule_id}/disable
POST   /schedules/{schedule_id}/run-now
POST   /schedules/validate-cron
```

MVP 可先实现：

```text
GET    /schedules
POST   /schedules
DELETE /schedules/{schedule_id}
POST   /schedules/validate-cron
```

创建 schedule 示例：

```json
{
  "name": "每天早上日报",
  "cron_expr": "0 8 * * *",
  "cron_label": "daily_8am",
  "timezone": "Asia/Shanghai",
  "hours_window": 24,
  "enabled": true
}
```

自定义 cron 示例：

```json
{
  "name": "工作日下午检查",
  "cron_expr": "30 14 * * 1-5",
  "cron_label": "custom",
  "timezone": "Asia/Shanghai",
  "hours_window": 12,
  "enabled": true
}
```

## 7. Pipeline 改造设计

当前可以参考 MCP 中的 staged run 思路，但把中间结果写入 SQLite。

目标 pipeline：

```text
create run
  ↓
fetch all sources
  ↓
merge URL duplicates
  ↓
save raw items
  ↓
AI scoring
  ↓
save scored items
  ↓
score threshold filtering
  ↓
topic dedup
  ↓
save filtered items
  ↓
enrichment
  ↓
save enriched items
  ↓
summary generation
  ↓
save summaries
  ↓
mark run succeeded
```

每个阶段需要：

- 更新 run 状态。
- 写 run_logs。
- 写阶段产物。
- 记录 count。
- 捕获异常并标记 failed。

设计约束：

- 不重写 scraper。
- 不重写 analyzer。
- 不重写 summarizer。
- 优先在 `PipelineService` 中编排现有能力。
- 尽量避免 API 层知道 pipeline 内部细节。

## 8. 定时运行设计

我们不做 OS 级后台服务。

MVP 目标是：

- 后端进程活着时，scheduler 可以定时触发 run。
- 未来 Electron 窗口关闭后隐藏到托盘，FastAPI/Python 后端继续运行。
- 用户点击“退出应用”时再停止后端和调度器。

调度策略：

- APScheduler 管理任务。
- 每个 schedule 对应一个 scheduler job。
- `max_instances = 1`，同一个 schedule 不并发执行多个 run。
- 如果上一次还在跑，本次触发跳过并记录日志。
- `next_run_at` 在创建/更新后计算并保存。

cron 职责边界：

- 后端只接受和校验 `cron_expr`。
- 前端未来负责常用 label 到 cron 的映射。
- 数据库只依赖 `cron_expr` 执行。
- `cron_label` 只用于 UI 展示。

## 9. 未来 Electron 对接方式

未来 Electron 客户端可以这样集成：

```text
Electron Main Process
├─ 启动 Python FastAPI 子进程
├─ 监听后端端口和健康状态
├─ 窗口关闭时隐藏到托盘
├─ 退出应用时停止后端
└─ Renderer 通过 HTTP 调用 API
```

预期用户体验：

- 关闭窗口后继续后台运行。
- 托盘菜单支持打开窗口、立即运行、暂停调度、退出。
- 前端通过 Swagger/OpenAPI 对接接口。
- Electron 不直接读写 SQLite，也不直接修改 `data/config.json`。

## 10. 安全边界

MVP 安全策略：

- 默认只监听 `127.0.0.1`。
- 不开放远程访问。
- 不设计账号。
- 不设计多用户权限。
- 不把 API key 明文写入数据库。

后续可增强：

- 本地一次性 token。
- Electron 主进程注入 token。
- OS keychain 管理密钥。
- API 端口随机化。

## 11. 后端可嵌入与打包约束

MVP 阶段不实现 Electron 客户端，也不产出最终安装包。但新增后端能力必须满足未来被 Electron 作为本地子进程启动的要求，避免后续需要大规模返工。

### 稳定启动入口

后端需要提供稳定命令入口：

```text
horizon-api
```

开发阶段可通过：

```text
uv run horizon-api
```

未来打包阶段可替换为：

```text
horizon-api.exe
```

Electron 只依赖这个启动入口，不直接调用 Python 内部模块。

### 路径可配置

后端不能假设当前工作目录就是项目源码目录。以下路径需要支持环境变量或启动参数覆盖：

```text
HORIZON_DATA_DIR
HORIZON_DB_PATH
HORIZON_CONFIG_PATH
HORIZON_HOST
HORIZON_PORT
```

开发默认值可以是：

```text
HORIZON_DATA_DIR=data
HORIZON_DB_PATH=data/horizon.db
HORIZON_CONFIG_PATH=data/config.json
HORIZON_HOST=127.0.0.1
HORIZON_PORT=8765
```

未来 Electron 中应使用用户数据目录，而不是源码目录。例如：

```text
app.getPath("userData")/horizon/
```

### 资源定位

如果后端需要读取配置模板、预设源、静态资源或默认文件，不应通过相对当前工作目录硬编码查找。需要集中封装资源路径解析。

需要特别注意：

- `data/config.example.json`
- `data/presets.json`
- 默认 `.env` 或用户配置文件
- 未来数据库迁移文件

### 启动可观测

后端启动成功后，需要有稳定方式让 Electron 判断服务已经可用。

MVP 至少提供：

```text
GET /health
```

未来可在标准输出中打印可解析 ready 信号：

```text
HORIZON_API_READY http://127.0.0.1:8765
```

Electron 主进程可以等待该信号或轮询 `/health`。

### 不打包整个源码目录

未来 Electron 不应简单把整个 Horizon Python 源码目录作为资源塞进去。后端应能逐步演进为独立可执行产物。

候选方式包括：

- PyInstaller
- Nuitka
- uv + embedded Python
- 随 Electron 携带 Python runtime 和 wheel 包

MVP 不需要选定最终方案，但代码结构必须支持被这些方案打包。

### 日志与退出

后端需要适合被 Electron 管理：

- 日志输出既写入数据库 `run_logs`，也保留进程级 stdout/stderr。
- 收到退出信号时优雅关闭 scheduler。
- 退出应用时由 Electron 停止后端进程。
- 关闭窗口不退出应用时，Electron 保持后端进程存活。

## 12. 测试策略

测试优先级：

1. SQLite schema 初始化。
2. Repository 写入和查询。
3. Config API 校验和保存。
4. Run API 创建、查询、日志。
5. Item API 筛选。
6. Summary API 读取。
7. Schedule cron 校验和创建。
8. Swagger/OpenAPI 可访问。
9. 统一响应格式和业务异常码映射。
10. 异常捕获装饰器对同步函数、异步函数、已知异常、未知异常和取消异常的处理。

测试原则：

- 尽量使用临时目录和临时 SQLite。
- FastAPI 使用 TestClient。
- Pipeline 测试使用 fake orchestrator/fake analyzer，避免真实网络和真实 AI。
- 真正端到端网络抓取作为后续 smoke test，不放入默认单测。

## 13. 风险与取舍

### 风险：Pipeline 与持久化耦合变重

缓解：

- 持久化逻辑放在 `PipelineService` 和 repository。
- 现有 scraper/analyzer/summarizer 保持纯业务能力。

### 风险：SQLite schema 过早复杂化

缓解：

- 只结构化高频查询字段。
- 来源差异字段继续 JSON 保存。
- 标签、引用、背景信息后续按需要拆表。

### 风险：定时任务和手动任务并发

缓解：

- MVP 可允许不同 run 并发，但同一个 schedule 不并发。
- 后续加入全局运行锁或队列。

### 风险：未来 Electron 后台运行语义不清晰

缓解：

- 设计上明确“关闭窗口不退出，退出应用才停止”。
- 后续 UI 需要提供状态提示和托盘控制。

### 风险：未来打包时发现路径依赖源码目录

缓解：

- MVP 阶段就引入路径配置约束。
- 开发默认 `data/`，但运行时允许环境变量覆盖。
- 所有资源路径集中解析。

## 14. 建议的落地顺序

审阅通过后，再进入实现计划。

推荐顺序：

1. FastAPI skeleton 和 Swagger/OpenAPI。
2. SQLite schema。
3. Config API。
4. Repository 写入查询。
5. PipelineService 阶段持久化。
6. Run API。
7. Item/Summary API。
8. ScheduleService 和 cron 校验。
9. Schedule API。
10. APScheduler runtime。
11. 文档和 smoke test。

## 15. 已确认决策

1. FastAPI 默认端口使用 `8765`。
2. cron 只支持标准 5 段表达式。
3. SQLite 默认路径使用 `data/horizon.db`。
4. 手动 run 与定时 run 在 MVP 阶段允许并发。
5. 不保留之前生成的英文实现计划草案，设计审阅通过后重新生成实现计划。
6. 配置页面保存配置时不做备份文件，也不做配置历史 API；只进行校验后保存当前配置。
7. MVP 阶段不实现 Electron 或最终安装包，但后端入口、路径、资源和日志必须满足未来被 Electron 作为本地子进程启动和打包的要求。
8. API 返回统一响应包络，业务异常通过 `errorCode` 和 `errorMessage` 表达，并与 HTTP 异常区分。
9. 设计 service 层异常捕获装饰器，用于减少重复 try/except，并将异常统一转换为业务异常；API 响应仍由全局异常处理器生成。

## 16. 待确认问题

暂无。设计审阅通过后，可以进入实现计划编写。
