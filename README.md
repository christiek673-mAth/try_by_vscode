# Enterprise Text-to-SQL

[![CI](https://github.com/christiek673-mAth/try_by_vscode/actions/workflows/ci.yml/badge.svg)](https://github.com/christiek673-mAth/try_by_vscode/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/christiek673-mAth/try_by_vscode)](https://github.com/christiek673-mAth/try_by_vscode/releases/latest)

**让业务人员用自然语言查询数据库，但不给 DBA 制造麻烦。**

> 当前主项目位于仓库根目录。历史独立版本 `v0.3.0` 已整理到 [enterprise-text-to-sql-v0.3.0/](enterprise-text-to-sql-v0.3.0/)，其中的说明文档位于其 `docs/` 目录。

---

## 💡 这是什么？

想象一下：你的产品经理走过来问："上个月北京地区的客户订单量是多少？"

传统方式：
1. 找 DBA 或数据分析师
2. 等待他们有空
3. 解释你的需求
4. 等待 SQL 查询结果
5. 发现理解偏差，重新来一遍

**现在的方式**：
```bash
curl -X POST https://your-api/v1/query \
  -H "Authorization: Bearer your-token" \
  -d '{"question": "上个月北京地区的客户订单量是多少"}'
```

10 秒后得到答案，SQL 自动生成，权限自动检查，敏感数据自动脱敏，查询自动记录。

---

## 🎯 为什么这很重要？

### 问题 1：数据民主化 vs 数据安全

企业都想让更多人用数据驱动决策，但又担心：
- ❌ 误删数据（`DELETE FROM users`）
- ❌ 泄露敏感信息（查到 CEO 的手机号）
- ❌ 跨租户访问（A 公司看到 B 公司的数据）
- ❌ 慢查询拖垮数据库（`SELECT * FROM 1 亿行表`）

### 问题 2：LLM 生成的 SQL 不可信

大模型很聪明，但也会犯错：
- 可能生成 `DROP TABLE`
- 可能忘记加 `WHERE tenant_id = 'xxx'`
- 可能写出笛卡尔积导致 OOM
- 可能暴露不该看的列

### 我们的解决方案

**在执行前多加一道安全门**，像机场安检一样：

```
用户问题 → LLM 生成 SQL → 🚨 安全检查 → ✅ 执行 → 脱敏结果
                              ↓
                         - AST 解析
                         - 只读检查
                         - 表白名单
                         - 租户隔离
                         - 行数限制
                         - 敏感列过滤
```

---

## ✨ 解决的核心难点

### 1. 租户隔离自动化

**问题**：多租户系统最怕的就是数据泄露

```sql
-- LLM 生成的 SQL（危险！）
SELECT * FROM orders WHERE status = 'paid'

-- 自动改写后（安全）
SELECT * FROM orders WHERE status = 'paid' AND tenant_id = 'company_a' LIMIT 200
```

自动处理：
- ✅ 简单查询
- ✅ JOIN 多表
- ✅ 子查询
- ✅ CTE（WITH 语句）

### 2. 敏感数据零信任

**三层防护**：

```python
# 第 1 层：LLM 的上下文里就不包含敏感列
catalog = get_catalog(exclude_sensitive=True)

# 第 2 层：SQL 解析时检查访问权限
if "email" in query_columns and user.role != "admin":
    raise PermissionDenied

# 第 3 层：返回结果时自动脱敏
{"name": "张三", "email": "***MASKED***"}
```

### 3. 多数据源统一接入

一个 API，连接你所有的数据源：

```bash
# 查询生产 PostgreSQL
{"question": "今日订单量", "datasource": "prod_postgres"}

# 查询数据仓库 Snowflake
{"question": "本月GMV", "datasource": "snowflake_dw"}

# 查询 MySQL 副本
{"question": "用户增长趋势", "datasource": "mysql_replica"}
```

每个数据源：
- 独立连接池
- 独立健康检查
- 独立超时配置
- 故障隔离

### 4. 企业级权限体系

不是简单的"能访问"或"不能访问"，而是：

```python
# 财务分析师：能看收入数据，但看不到客户手机号
DataPermission(
    role="finance_analyst",
    table="revenue",
    denied_columns=["customer_phone", "customer_email"]
)

# HR：能看员工表，但看不到薪资
DataPermission(
    role="hr",
    table="employees",
    denied_columns=["salary", "bonus", "stock_options"]
)

# 普通用户：只能看自己部门的数据
DataPermission(
    role="viewer",
    row_filter="department = '{user.department}'"
)
```

---

## 🚀 5 分钟快速体验

### 1. 安装运行

```bash
# 克隆项目
git clone https://github.com/christiek673-mAth/try_by_vscode.git
cd try_by_vscode

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动服务（自动创建演示数据）
uvicorn app.main:app --reload
```

### 2. 第一次查询

打开浏览器访问 http://127.0.0.1:8000/docs，或直接用 curl：

```bash
curl -X POST http://127.0.0.1:8000/v1/query \
  -H 'Content-Type: application/json' \
  -d '{
    "question": "查询所有客户",
    "tenant_id": "demo",
    "user_id": "test-user"
  }'
```

**看到什么了？**

```json
{
  "sql": "SELECT * FROM customers WHERE tenant_id = 'demo' LIMIT 200",
  "rows": [
    {"id": 1, "name": "张三", "email": "***MASKED***", "tenant_id": "demo"},
    {"id": 2, "name": "李四", "email": "***MASKED***", "tenant_id": "demo"}
  ],
  "warnings": ["Sensitive columns are masked in returned rows."]
}
```

注意：
- ✅ 自动添加了 `tenant_id` 过滤
- ✅ 自动添加了 `LIMIT 200`
- ✅ 敏感列 `email` 被自动脱敏
- ✅ 其他租户的数据完全不可见

### 3. 试试危险操作

```bash
# 试图删除数据
curl -X POST http://127.0.0.1:8000/v1/query \
  -d '{"question": "删除所有客户"}'

# 返回错误
{"error": "Policy violation: Only SELECT statements allowed"}

# 试图访问其他租户数据
curl -X POST http://127.0.0.1:8000/v1/query \
  -d '{"question": "查询 tenant_id=other 的客户", "tenant_id": "demo"}'

# 返回空（自动改写保护）
{"rows": [], "sql": "... WHERE tenant_id = 'other' AND tenant_id = 'demo' ..."}
```

---

## 🎮 有趣的功能演示

### 演示 1：自动租户隔离

```bash
# 公司 A 的用户查询
curl -X POST http://127.0.0.1:8000/v1/query \
  -d '{"question": "统计订单数量", "tenant_id": "company_a"}'
# 结果：只看到 company_a 的订单

# 公司 B 的用户查询（同一个问题）
curl -X POST http://127.0.0.1:8000/v1/query \
  -d '{"question": "统计订单数量", "tenant_id": "company_b"}'
# 结果：只看到 company_b 的订单，完全隔离！
```

### 演示 2：复杂 SQL 也能自动处理

```bash
# 带 JOIN 的查询
curl -X POST http://127.0.0.1:8000/v1/query \
  -d '{"question": "查询客户及其订单", "tenant_id": "demo"}'

# 生成的 SQL（自动给两个表都加了租户过滤）
# SELECT c.*, o.* FROM customers c 
# JOIN orders o ON c.id = o.customer_id 
# WHERE c.tenant_id = 'demo' AND o.tenant_id = 'demo' LIMIT 200
```

### 演示 3：敏感数据自动脱敏

```bash
# 即使 LLM 生成了包含敏感列的 SQL
curl -X POST http://127.0.0.1:8000/v1/query \
  -d '{"question": "查询客户的邮箱和电话"}'

# 返回结果中敏感字段被自动掩码
{"rows": [{"name": "张三", "email": "***MASKED***", "phone": "***MASKED***"}]}
```

---

## 📚 配置与部署

### 基础配置

```bash
# 复制示例配置
cp .env.example .env

# 最小配置（使用演示数据库）
DATABASE_URL=sqlite:///./data/demo.db
SQL_DIALECT=sqlite
SENSITIVE_COLUMNS=email,phone,ssn
```

### 连接真实数据库

```bash
# PostgreSQL
DATABASE_URL=postgresql://user:password@host:5432/dbname

# MySQL
DATABASE_URL=mysql://user:password@host:3306/dbname

# 配置表白名单（推荐）
ALLOWED_TABLES=customers,orders,products
```

### 集成 LLM（可选）

```bash
# 不配置则使用 mock 模式（仅用于测试）
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-api-key-here
LLM_MODEL=gpt-4
```

### 启用企业认证

```bash
# 生成强密钥
openssl rand -hex 32

# 配置 JWT 认证
AUTH_ENABLED=true
JWT_SECRET=your-generated-secret
REQUIRE_TENANT_CLAIM=true

# 使用时携带 token
curl -H "Authorization: Bearer $TOKEN" ...
```

### Docker 一键部署

```bash
# 构建镜像
docker build -t text-to-sql:latest .

# 运行
docker run -d -p 8000:8000 \
  -v $(pwd)/.env:/app/.env:ro \
  --name text-to-sql \
  text-to-sql:latest
```

---

## 🔧 可优化的部分（欢迎贡献）

### 当前限制

1. **向量检索未集成**
   - 现状：使用简单的关键词匹配查找相关表
   - 改进方向：集成 Pinecone/Weaviate/Qdrant，语义搜索表和列
   - 影响：提升复杂问题的 SQL 生成准确率

2. **LLM 成本未追踪**
   - 现状：每次查询消耗的 token 数未统计
   - 改进方向：记录 prompt/completion tokens，计算成本，设置配额
   - 影响：控制 API 调用成本

3. **查询结果无缓存**
   - 现状：相同问题每次都重新生成 SQL 并执行
   - 改进方向：Redis 缓存查询结果，设置 TTL
   - 影响：减少 LLM 调用和数据库压力

4. **审计日志存储简单**
   - 现状：使用 JSONL 文件存储
   - 改进方向：集成 ELK/Splunk/DataDog，实时分析
   - 影响：更好的可观测性和合规审计

5. **权限配置需要代码**
   - 现状：需要修改 Python 代码定义权限规则
   - 改进方向：提供 Web UI 或 YAML 配置文件
   - 影响：降低使用门槛

6. **单点故障风险**
   - 现状：单实例部署
   - 改进方向：支持水平扩展，状态外置
   - 影响：提升可用性

### 技术债务

- 目录检索算法过于简单（TF-IDF）
- 连接池配置未按数据源独立定制
- SQL 生成没有 few-shot 示例
- 缺少查询性能分析工具
- 没有查询取消机制（长查询无法中断）

### 想贡献？

我们欢迎以下类型的 PR：

- 🐛 Bug 修复
- ✨ 新功能实现
- 📝 文档改进
- 🧪 测试用例补充
- 🎨 代码重构

查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

---

## 🧪 测试

```bash
# 运行所有测试（27 个测试用例）
pytest tests/ -v

# 运行特定模块测试
pytest tests/test_auth.py -v
pytest tests/test_permissions.py -v

# 代码检查
ruff check app tests
```

**测试覆盖**：
- ✅ 策略验证（10 个）
- ✅ API 端点（4 个）
- ✅ 认证授权（4 个）
- ✅ 数据源管理（3 个）
- ✅ 权限引擎（4 个）
- ✅ 配置与数据库（2 个）

---

## 📖 API 文档

### POST /v1/query

执行自然语言查询。

**请求示例**：
```json
{
  "question": "查询上个月订单总额",
  "tenant_id": "demo",
  "user_id": "analyst-01",
  "datasource": "primary",
  "execute": true,
  "max_rows": 100
}
```

**响应示例**：
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "question": "查询上个月订单总额",
  "sql": "SELECT SUM(amount) FROM orders WHERE tenant_id = 'demo' AND date >= '2024-07-01' LIMIT 100",
  "explanation": "聚合查询，自动添加租户过滤和时间范围",
  "rows": [{"sum": 125000.50}],
  "row_count": 1,
  "execution_ms": 15.23,
  "model": "gpt-4",
  "datasource": "primary",
  "warnings": []
}
```

### GET /v1/catalog

获取可查询的表目录（敏感列已隐藏）。

### GET /health

服务健康检查，返回认证状态和数据源健康状态。

### GET /v1/datasources

（需要 admin 权限）列出所有已配置的数据源。

完整 API 文档：http://127.0.0.1:8000/docs

---

## 🔒 安全威胁模型

| 威胁 | 防护措施 | 实现方式 |
|------|---------|---------|
| SQL 注入 | AST 解析 + 参数化 | SQLGlot 验证 |
| 数据泄露 | 租户隔离 + 脱敏 | 自动注入 WHERE + 结果过滤 |
| 权限提升 | JWT + RBAC | token 验证 + 角色检查 |
| 拒绝服务 | 速率限制 + 超时 | 按 IP 限流 + statement timeout |
| 跨租户访问 | 强制过滤 | JOIN/CTE 自动改写 |
| PII 泄露 | 三层防护 | 目录/SQL/结果多重过滤 |

---

## 🎯 适用场景

### ✅ 适合

- 内部数据分析平台（BI 替代）
- 客户自助查询门户（SaaS）
- 数据中台统一查询入口
- 低代码分析工具后端
- 临时数据探查工具

### ❌ 不适合

- 高频交易系统（延迟敏感）
- 大批量数据导出（有行数限制）
- 复杂 OLAP 分析（缺少优化器）
- 完全开放的公共 API（需要更严格的沙箱）

---

## 📄 License

本项目基于 [MIT License](LICENSE) 发布。

## 🙏 致谢

- [SQLGlot](https://github.com/tobymao/sqlglot) - SQL 解析与改写
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架
- [SQLAlchemy](https://www.sqlalchemy.org/) - 数据库适配

---

## 🔗 相关资源

- 📦 [发布说明](RELEASE_NOTES_v0.4.0.md)
- 🔐 [安全政策](SECURITY.md)
- 🤝 [贡献指南](CONTRIBUTING.md)
- 🐛 [问题反馈](https://github.com/christiek673-mAth/try_by_vscode/issues)

---

**Star ⭐ 本项目，关注更新！**


