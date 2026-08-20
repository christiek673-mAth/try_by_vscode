# Enterprise Text-to-SQL

[![CI](https://github.com/christiek673-mAth/try_by_vscode/actions/workflows/ci.yml/badge.svg)](https://github.com/christiek673-mAth/try_by_vscode/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

一个面向企业分析场景的 Text-to-SQL 服务骨架：把自然语言问题转换为只读 SQL，并在执行前经过 SQL AST 策略检查、表访问控制、租户隔离和行数限制。返回结果会对配置的敏感列做脱敏，同时记录结构化审计事件。

> **状态：可运行的安全基础骨架。** 项目适合学习、内部原型和二次开发；它不是开箱即用的生产数据网关。生产部署必须配合身份认证、数据库原生权限、Row-Level Security、网络隔离和经过审核的元数据服务。

## 为什么做这个项目

企业 Text-to-SQL 的难点不只是 SQL 生成，而是让生成结果在真实数据边界内可控、可解释、可审计。本项目把关键控制点放在模型输出之后：

```text
Question
   |
   v
Metadata catalog -> relevant schema context -> LLM adapter
                                               |
                                               v
                         SQL AST policy: read-only / allowlist / tenant / LIMIT
                                               |
                                               v
                         Read-only execution -> masking -> audit event -> response
```

当前版本包含：

- 自动读取数据库表和列元数据，并进行轻量词法检索
- OpenAI-compatible `/chat/completions` 模型适配器
- 无外部模型时可运行的确定性 `mock-local` 演示模型
- SQLGlot AST 校验：单条语句、只读 `SELECT`、已知表、正整数 `LIMIT`
- 对每个 `SELECT` 的本地租户表注入 `tenant_id` 条件，覆盖 JOIN、CTE 和嵌套查询的基础场景
- 结果列脱敏，包括敏感列别名；目录和模型上下文默认隐藏敏感列
- SQLite 演示数据库、JSONL 审计日志、Docker 镜像和 GitHub Actions CI
- 16 项回归测试，覆盖策略、API、配置和结果处理

## 快速开始

需要 Python 3.8+。

```bash
git clone https://github.com/christiek673-mAth/try_by_vscode.git
cd try_by_vscode
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

打开 <http://127.0.0.1:8000/docs> 查看交互式 API 文档。

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"查询客户","tenant_id":"demo","user_id":"local-user"}'
```

默认配置会在 `development` 环境下创建 SQLite 演示数据库，并使用 `mock-local`。示例返回的客户邮箱会显示为 `***MASKED***`，而 `other` 租户的数据不会出现在 `demo` 查询中。

## Docker

```bash
docker build -t enterprise-text-to-sql .
docker run --rm -p 8000:8000 \
  -e APP_ENV=development \
  -e DATABASE_URL=sqlite:///./data/demo.db \
  enterprise-text-to-sql
```

容器使用非 root 用户运行。生产环境请挂载受控的数据目录，并使用真正的只读数据库连接；不要把 `.env` 或 API Key 放入镜像。

## 配置

复制 `.env.example` 为 `.env` 后按需修改：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `development` | `development`、`test`、`demo` 才会自动创建演示表 |
| `DATABASE_URL` | `sqlite:///./data/demo.db` | SQLAlchemy 数据库 URL |
| `SQL_DIALECT` | `sqlite` | SQLGlot 读取和输出方言 |
| `LLM_BASE_URL` | empty | OpenAI-compatible API 根地址 |
| `LLM_API_KEY` | empty | 模型服务密钥，必须通过密钥管理系统提供 |
| `LLM_MODEL` | empty | 模型名称；三项都配置才启用远程模型 |
| `LLM_TIMEOUT_SECONDS` | `30` | 模型请求超时，范围 0 到 120 秒 |
| `MAX_ROWS` | `200` | 服务端最大返回行数 |
| `CATALOG_TOP_K` | `8` | 注入模型上下文的候选表数量 |
| `SENSITIVE_COLUMNS` | `email,phone,id_card` | 逗号分隔的敏感列名 |
| `ALLOWED_TABLES` | empty | 可选的表白名单；为空表示使用数据库发现到的所有表 |
| `AUDIT_LOG_PATH` | `./data/audit.jsonl` | JSONL 审计日志路径 |

远程模型请求只接收过滤后的 schema 上下文，不会把敏感列放入默认上下文。策略层仍然是最终控制点，不能把模型提示词当作权限边界。

## API

### `GET /health`

返回服务状态、当前模型名和可用表数量。适合容器 liveness 检查；它不代表下游数据库和模型一定可用。

### `GET /v1/catalog`

返回当前允许访问的公开表结构。配置的敏感列不会出现在响应中。

### `POST /v1/query`

请求：

```json
{
  "question": "查询最近的订单",
  "tenant_id": "demo",
  "user_id": "analyst-1",
  "execute": true,
  "max_rows": 50
}
```

设置 `execute: false` 可以只生成和校验 SQL，不执行数据库查询。响应包含 `request_id`、策略改写后的 SQL、解释、相关表、结果和告警。生产系统应把 `user_id` 替换为经过认证的身份，不应信任客户端任意传入的用户或租户字段。

## 安全模型与限制

当前策略提供多层防线，但不能替代数据库权限：

1. 使用 SQLGlot 解析单条语句，只接受 `SELECT`。
2. 只允许目录中的表，且可通过 `ALLOWED_TABLES` 收紧范围。
3. 对包含 `tenant_id` 的表注入租户条件，并避免重复注入已有相同条件。
4. 对无界查询添加 `LIMIT`，并把超过服务上限的整数 LIMIT 收紧。
5. 对结果中的敏感列和敏感列别名进行脱敏。
6. 记录问题、策略后 SQL、行数、耗时和失败原因到 JSONL 审计日志。

已知边界：

- 租户 AST 改写是额外防线；正式环境必须使用 PostgreSQL RLS、数据仓库授权视图或等价的数据库原生隔离。
- `ALLOWED_TABLES` 不是列级权限系统，生产环境需要按用户、角色和数据域动态计算表列授权。
- 当前 catalog 是轻量词法检索，没有业务指标定义、同义词、示例 SQL、BM25/向量检索或 rerank。
- 当前执行器没有成本估算、查询取消、数据库级 statement timeout、分页和导出审计。
- 生产环境应把审计日志发送到受控日志系统，并设置访问控制、保留期和脱敏规则。

## 测试与开发

```bash
make check
# 或者
ruff check app tests
pytest -q
```

项目通过 GitHub Actions 在 Python 3.8 和 3.11 上运行 lint 与测试。贡献规范见 [CONTRIBUTING.md](CONTRIBUTING.md)，安全问题请参阅 [SECURITY.md](SECURITY.md)。

## Roadmap

- [ ] 接入 OIDC/SSO、RBAC 和策略服务
- [ ] 支持 PostgreSQL / MySQL / DuckDB 的方言级集成测试
- [ ] 接入审核后的指标语义层和混合检索
- [ ] 增加 SQL dry-run、成本预算、超时和取消
- [ ] 建立执行正确率、结果正确率、拒答率和越权率评测集
- [ ] 增加 OpenTelemetry traces、metrics 和结构化日志适配器

## License

本项目基于 [MIT License](LICENSE) 发布。