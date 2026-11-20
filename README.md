# S3-SALES-016 · 分配规则与公海参数的配置管理接口

ClawHunt 工单 **#2372** 交付候选。本仓库实现会员空间平台「业务员工作台 v1」中的
**分配规则管理**与**公海参数管理**接口，包括：

- 分配规则 CRUD、启停、批量调整优先级；
- 公海参数表 `sales_pool_settings` 的模型、迁移与 GET/PUT；
- 每次配置变更的审计日志（旧值、新值、操作人、时间）与分页查询；
- 权限控制（会所负责人 / sys_admin 可写，主管只读，顾问不可读取规则详情）；
- 校验单元测试、接口测试、OpenAPI 描述与 README。

- 数据库：PostgreSQL 16（本次实测 **16.16**）
- 运行环境：Python 3.12.12（要求 3.11+）
- 测试结果：**81 passed**（真实 PostgreSQL，见 `evidence/test-results.txt`）
- 迁移证据：upgrade → downgrade → upgrade → `alembic check` 零漂移，见
  `evidence/migration-check.txt`
- OpenAPI：`docs/openapi.json`（6 个路径 / 8 个操作）

> **边界声明（先读）**
>
> 1. 本单只做**配置管理接口**。分配引擎、线索/会员数据接入、公海回收定时任务、
>    工作台前端均不在本单范围；规则只落库并通过接口暴露，引擎按 `strategy` /
>    `conditions` / `work_hours` / `priority` 消费。
> 2. S2-IAM（身份、角色、数据范围）按工单允许的方式用**接口桩**先行：
>    `app/iam.py` 从受信头解析 principal，并从 JSON 名册判断“是否本站招商顾问”。
>    生产替换为 IAM introspection，详见 §7。
> 3. `conditions` 的枚举词表在 S1-DD-005（线索字段字典）冻结前是**接口桩常量**
>    （`app/enums.py: CONDITION_ENUMS`），见 §6；替换词表只改一处。
> 4. 全部测试数据为虚构 UUID、虚构规则名与虚构会所，不含客户名称、真实会员企业
>    或个人信息。
> 5. 不引入任何向境外发送数据的第三方 SDK；配置与连接串只从环境变量读取。

---

## 1. 范围

| 做 | 不做 |
|---|---|
| 分配规则 5 个接口（列表 / 创建 / 更新 / 启停 / 排序） | 分配引擎（轮询、最少持有、指定人执行） |
| 公海参数表模型、迁移、GET / PUT | 公海自动回收定时任务、提醒任务 |
| 名称唯一、策略与成员、工作时段、条件枚举校验 | 线索/会员标签的计算与清洗 |
| 配置变更日志（全量前后快照）与分页查询 | 日志归档、报表、告警 |
| 角色权限与站点数据范围 | 真实 S2-IAM 联调、SSO、菜单权限 |
| OpenAPI、pytest、README | 前端页面、小程序、部署流水线 |

依赖 S2-IAM 与 S1-DD-005 的部分用接口桩/常量先行，并在下文写明对接点。

---

## 2. 快速开始

```bash
# 1) PostgreSQL 16 测试库（库名必须含 test，测试会重建 public schema）
createdb -h 127.0.0.1 -p 5432 clawhunt_2372_test

# 2) 安装依赖
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3) 建表
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/clawhunt_2372_test'
.venv/bin/alembic upgrade head

# 4) 全量测试（真实 PostgreSQL）
export TEST_DATABASE_URL="$DATABASE_URL"
EVIDENCE_OUT=evidence/test-results.txt ./scripts/test.sh

# 5) 迁移往返 + 漂移检查
./scripts/migration-check.sh | tee evidence/migration-check.txt

# 6) 导出 OpenAPI
.venv/bin/python scripts/export_openapi.py
```

可选 Docker 测试库：

```bash
docker compose -f docker-compose.test.yml up -d
export TEST_DATABASE_URL='postgresql+psycopg://clawhunt:clawhunt@127.0.0.1:55436/clawhunt_2372_test'
```

启动服务（仅用于本地联调；生产由平台网关注入身份头）：

```bash
export DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DB_NAME'
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
# 交互文档：http://127.0.0.1:8000/docs
```

---

## 3. 目录

```
app/
  api/sales.py            # 8 个 HTTP 操作
  db.py                   # DATABASE_URL、engine/session、FastAPI 依赖
  enums.py                # 策略 / 角色 / 审计动作 / 条件词表（桩）
  iam.py                  # S2-IAM 接口桩：principal + 招商顾问名册
  main.py                 # FastAPI 工厂
  models/
    base.py               # 统一字段 mixin（UUID / 租户 / 时间戳 / 软删除）
    assignment_rule.py
    sales_pool_settings.py
    config_change_log.py
  schemas/sales.py        # Pydantic v2 请求/响应与纯校验
fixtures/iam_consultants.json  # 虚构 IAM 名册
migrations/versions/0001_sales_assignment_config.py
tests/                    # 81 项，真实 PostgreSQL
scripts/                  # test.sh / migration-check.sh / export_openapi.py
docs/openapi.json         # 导出的 OpenAPI 3.1 描述
docs/er.mmd               # Mermaid ER 图
evidence/                 # 测试与迁移真实输出
```

---

## 4. 数据模型

三张表都带项目统一字段：`id(UUID, gen_random_uuid())`、`org_id`、`site_id`、
`created_at`、`created_by`、`updated_at`、`deleted_at`（软删除）。金额不在本单范围。

### 4.1 `sales_assignment_rule`

| 列 | 类型 | 空 | 默认 | 说明 |
|---|---|---|---|---|
| `name` | VARCHAR(64) | 否 | — | 会所（org + site）内唯一 |
| `strategy` | VARCHAR(16) | 否 | — | `round_robin` / `least_holding` / `fixed_user` |
| `conditions` | JSONB | 否 | `{}` | 条件对象，键与字面量受词表约束 |
| `member_user_ids` | UUID[] | 否 | — | 至少 1 人；`fixed_user` 恰好 1 人 |
| `work_hours` | JSONB | 否 | — | `[{weekday, start, end}]`，weekday 0=周一 |
| `priority` | INTEGER | 否 | 100 | 越小越靠前，≥ 0 |
| `enabled` | BOOLEAN | 否 | true | 启停状态 |

约束与索引：

- `uq_sales_assignment_rule_site_name (org_id, site_id, name)`：会所内重名直接
  数据库报错，接口预检返回 409；
- `ck_*_strategy` / `ck_*_priority` / `ck_*_members` / `ck_*_conditions` /
  `ck_*_work_hours`：枚举、优先级、成员非空、JSON 形状兜底；
- `ix_sales_assignment_rule_site_order (org_id, site_id, enabled, priority)`：
  列表查询走索引。

### 4.2 `sales_pool_settings`（公海参数，每个 site 一行）

| 列 | 默认 | 约束 | 说明 |
|---|---|---|---|
| `recycle_days` | 7 | 3–30 | 公海回收天数 |
| `recycle_warn_days` | 5 | ≥1 且 **< recycle_days** | 回收预警天数 |
| `daily_claim_limit` | 10 | ≥1 | 每日领取上限 |
| `holding_limit` | 150 | ≥1 | 持有上限 |
| `reclaim_cooldown_days` | 15 | ≥0 | 召回冷却天数 |

`uq_sales_pool_settings_site (org_id, site_id)` 保证一站一行。GET 在站点尚无
记录时返回计算默认值（`is_default=true`、`id=null`），不写库；PUT 首次写入时
创建记录，并把“默认值 → 新值”写入审计日志。

### 4.3 `sales_config_change_log`

| 列 | 类型 | 说明 |
|---|---|---|
| `entity_type` | VARCHAR(32) | `assignment_rule` / `pool_settings` |
| `entity_id` | UUID | 规则 id 或参数行 id |
| `action` | VARCHAR(32) | `create` / `update` / `toggle` / `reorder` / `pool_settings_update` |
| `old_value` | JSONB | 修改前全量快照；创建时为 `null` |
| `new_value` | JSONB | 修改后全量快照 |
| `operator_id` | UUID | 操作人 |
| `created_at` | TIMESTAMPTZ | 操作时间 |

审计行与业务修改在**同一事务**内提交：修改回滚则审计行也不存在。`reorder` 对
每条优先级真正变化的规则各写一条；`toggle` 记录 `enabled` 前后值；规则
`create/update` 记录完整规则快照（含成员、条件、工作时段、优先级、启停）。

Mermaid ER 图见 [`docs/er.mmd`](docs/er.mmd)。

---

## 5. 接口

统一前缀 `/api/sales`。成功返回 JSON 对象；错误返回 `{"detail": ...}`（
Pydantic 校验为 422 列表，业务错误为字符串或带 `code` 的对象）。

| 方法 | 路径 | 说明 | 成功码 |
|---|---|---|---|
| GET | `/assignment-rules` | 列表，按 priority 升序；`include_disabled`、`limit`、`offset` | 200 |
| POST | `/assignment-rules` | 创建规则 | 201 |
| PUT | `/assignment-rules/{id}` | 局部更新；合并后重跑全部创建校验 | 200 |
| POST | `/assignment-rules/{id}/toggle` | 启停；无 body 则翻转，`{"enabled": false}` 可强制 | 200 |
| POST | `/assignment-rules/reorder` | 批量设置 priority，单事务 | 200 |
| GET | `/pool-settings` | 读取本站参数（无记录返回默认） | 200 |
| PUT | `/pool-settings` | 局部 upsert；省略字段保留原值/默认 | 200 |
| GET | `/config-logs` | 审计分页：`page`、`page_size`、`entity_type`、`entity_id`、`action` | 200 |

### 5.1 创建示例

```bash
curl -sS -X POST http://127.0.0.1:8000/api/sales/assignment-rules \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: aaaaaaaa-0000-4000-8000-000000000001' \
  -H 'X-Org-Id: 11111111-1111-4111-8111-111111111111' \
  -H 'X-Site-Id: 22222222-2222-4222-8222-222222222222' \
  -H 'X-Role: club_owner' \
  -d '{
    "name": "华东制造业轮询",
    "strategy": "round_robin",
    "conditions": {"region": ["east"], "industry": ["manufacturing"]},
    "member_user_ids": [
      "aaaaaaaa-0000-4000-8000-000000000003",
      "aaaaaaaa-0000-4000-8000-000000000004"
    ],
    "work_hours": [
      {"weekday": 0, "start": "09:00", "end": "12:00"},
      {"weekday": 0, "start": "13:00", "end": "18:00"}
    ],
    "priority": 10,
    "enabled": true
  }'
```

### 5.2 公海参数示例

```bash
curl -sS -X PUT http://127.0.0.1:8000/api/sales/pool-settings \
  -H 'Content-Type: application/json' \
  -H 'X-User-Id: aaaaaaaa-0000-4000-8000-000000000001' \
  -H 'X-Org-Id: 11111111-1111-4111-8111-111111111111' \
  -H 'X-Site-Id: 22222222-2222-4222-8222-222222222222' \
  -H 'X-Role: club_owner' \
  -d '{"recycle_days": 10, "recycle_warn_days": 6}'
```

`recycle_warn_days: 10`（等于 `recycle_days`）或 `11` 会返回 **422**。

### 5.3 常见状态码

| 码 | 场景 |
|---|---|
| 401 | 缺少/非法身份头、未知角色 |
| 403 | 角色无权写、主管/顾问越权、顾问读取规则或审计 |
| 404 | 规则不存在（含跨站点访问） |
| 409 | 会所内规则重名 |
| 422 | 字段/枚举/成员/工作时段/公海交叉校验失败 |

---

## 6. 校验规则与条件词表

### 6.1 分配规则

1. `name`：去首尾空白后 1–64 字符，同一 `org_id + site_id` 内唯一（409）。
2. `strategy`：只接受 `round_robin` / `least_holding` / `fixed_user`。
3. `member_user_ids`：至少 1 人、不可重复；`fixed_user` 必须**恰好 1 人**；
   所有成员必须出现在本站招商顾问名册（422，`code=member_not_consultant`）。
4. `work_hours`：非空数组；`weekday` 0–6；`start`/`end` 为 `HH:MM` 24 小时制；
   `start < end`；同一 weekday 的时段不可重叠（相邻允许）。
5. `conditions`：键必须在词表中，值必须是非空、无重复的合法字面量数组；
   未知键/非法值均 422。
6. `priority`：整数 ≥ 0，默认 100；`reorder` 中重复 id 直接 422。

### 6.2 条件词表（v1 接口桩，待 S1-DD-005 替换）

| 键 | 合法字面量 |
|---|---|
| `member_level` | `A` / `B` / `C` |
| `member_status` | `active` / `renewing` / `churned` |
| `industry` | `manufacturing` / `trade` / `service` / `tech` / `other` |
| `region` | `north` / `east` / `south` / `west` / `central` / `overseas` |
| `source` | `referral` / `event` / `website` / `mini_program` / `manual` |
| `intent` | `high` / `medium` / `low` |

空对象 `{}` 表示不限制。词表集中定义在 `app/enums.py: CONDITION_ENUMS`，替换时
同步更新 README 与测试即可，路由/模型无需改动。

### 6.3 公海参数

- `recycle_days` 3–30，默认 7；
- `recycle_warn_days` ≥1 且 **严格小于** `recycle_days`，默认 5；
- `daily_claim_limit` ≥1，默认 10；
- `holding_limit` ≥1，默认 150；
- `reclaim_cooldown_days` ≥0，默认 15；
- PUT 为局部更新：省略字段沿用已存值（无记录时用默认值），合并后再做交叉校验。

---

## 7. 权限与 S2-IAM 接口桩

### 7.1 权限矩阵

| 角色（`X-Role`） | GET 规则 | 写规则/启停/排序 | GET 公海 | PUT 公海 | GET 审计 |
|---|---|---|---|---|---|
| `sys_admin` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `club_owner`（会所负责人） | ✅ | ✅ | ✅ | ✅ | ✅ |
| `supervisor`（主管） | ✅ | ❌ 403 | ✅ | ❌ 403 | ✅ |
| `consultant`（顾问） | ❌ 403 | ❌ 403 | ✅ | ❌ 403 | ❌ 403 |

- 站点数据范围由 principal 的 `org_id + site_id` 决定，接口不接受站点参数，
  跨站数据不可见；
- 顾问被禁止读取规则详情与审计快照（规则成员、条件属于敏感配置）。

### 7.2 身份头（仅限网关后使用）

```
X-User-Id: <uuid>
X-Org-Id:  <uuid>
X-Site-Id: <uuid>
X-Role:    sys_admin | club_owner | supervisor | consultant
```

`app/iam.py: get_principal` 是唯一替换点：生产改为调用 S2-IAM 的 token
introspection / 网关断言，路由代码不变。**不要把本服务直接暴露到公网**，
否则任何人都能伪造身份头。

### 7.3 招商顾问名册桩

`app/iam.py: JsonConsultantDirectory` 读取：

```json
{"sites": {"<org_uuid>:<site_uuid>": ["<user_uuid>", "..."]}}
```

- 默认文件：`fixtures/iam_consultants.json`（全部为虚构 UUID）；
- 可用 `IAM_CONSULTANTS_FILE` 指向其他文件；
- 生产替换为 `GET /internal/iam/sites/{site_id}/sales-consultants`；
- 名册缺失时启动请求会报错，不会静默放行任意成员。

---

## 8. 验收标准对照

| # | 平台验收标准 | 实现 | 测试 |
|---|---|---|---|
| 1 | `recycle_warn_days` 不小于 `recycle_days` 时 PUT 返回 422 | `PoolSettingsValues` 交叉校验 + 路由 422 | `test_api_pool_settings.py::test_warn_days_equal_recycle_days_returns_422`、`test_warn_days_greater_than_recycle_days_returns_422`、`test_validation_unit.py::test_pool_warn_days_must_be_smaller_than_recycle_days` |
| 2 | `fixed_user` 策略传 2 个成员返回 422 | `AssignmentRuleCreate._strategy_member_count`；PUT 合并后复验 | `test_api_assignment_rules.py::test_fixed_user_two_members_returns_422`、`test_update_rule_revalidates_strategy_and_members`、`test_validation_unit.py::test_fixed_user_requires_exactly_one_member` |
| 3 | 主管调用写接口 403，调用 GET 返回 200 | `require_write` / `require_rule_read` 依赖 | `test_permissions.py::test_supervisor_reads_rules_but_cannot_write` |
| 4 | 每次修改都生成一条含旧值与新值的变更日志 | 同事务写 `sales_config_change_log`，全量快照 | `test_config_logs.py` 全部 10 项（创建/更新/启停/排序/公海/分页/过滤） |

补充覆盖（非验收项但属本单范围）：

- 重名 409、跨站隔离、非法枚举/工作时段/成员、401/403/404/422 状态；
- 数据库级约束（非法策略、非法公海交叉、JSON 形状、UUID 默认值、站点唯一）；
- OpenAPI 路径/状态码/组件导出。

---

## 9. 测试与证据

```bash
export TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/clawhunt_2372_test'
EVIDENCE_OUT=evidence/test-results.txt ./scripts/test.sh
DATABASE_URL="$TEST_DATABASE_URL" ./scripts/migration-check.sh | tee evidence/migration-check.txt
```

- `evidence/test-results.txt`：81 项通过（真实 PG 16.16，约 3 秒）；
- `evidence/migration-check.txt`：`upgrade → downgrade → upgrade → alembic check`
  输出 `No new upgrade operations detected`，`alembic current` 为
  `0001_sales_assignment_config (head)`。

测试库保护：`TEST_DATABASE_URL` 的库名必须包含 `test`，否则 pytest 直接退出；
session 级 fixture 会 `DROP SCHEMA public CASCADE` 后重新迁移，**不要指向共享库**。

---

## 10. 配置项

| 变量 | 必填 | 用途 |
|---|---|---|
| `DATABASE_URL` | 是 | PostgreSQL 连接串（`postgresql+psycopg://...`） |
| `IAM_CONSULTANTS_FILE` | 否 | 覆盖 IAM 名册桩文件路径 |
| `TEST_DATABASE_URL` | 测试时 | 测试库连接串，库名须含 `test` |

无密钥、无第三方 SDK 配置；连接串只从环境变量读取，仓库不含 `.env`。

---

## 11. 已知边界与后续对接

1. **分配引擎不在本单**：本服务只保证规则/参数可配置、可审计；轮询、最少持有、
   指定人、公海回收、每日领取上限的执行由引擎工单实现。
2. **S2-IAM 为桩**：身份头与 JSON 名册只用于本单联调；上线前必须替换
   `get_principal` 与 `ConsultantDirectory`，并移除“信任头”模式。
3. **S1-DD-005 未冻结**：条件词表为 v1 桩，字段字典合并后需同步词表、README
   与测试；接口形状不变。
4. **分页口径**：规则列表用 `limit/offset`，审计用 `page/page_size`，均按工单
   要求提供；如核心团队统一为游标分页，可在路由层替换而不影响表结构。
5. **软删除**：三张表保留 `deleted_at` 以符合统一约定；本单未提供删除接口，
   唯一约束按 `(org_id, site_id, name)` 生效。
6. **时区**：所有时间列 `TIMESTAMPTZ`，审计 `created_at` 由应用写入 UTC。
