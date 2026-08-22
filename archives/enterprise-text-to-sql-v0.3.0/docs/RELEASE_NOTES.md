# Enterprise Text-to-SQL v0.3.0 发布说明

**发布日期**: 2026-08-20  
**版本**: v0.3.0  
**类型**: 主要功能更新

## 概述

本版本为企业级生产环境引入完整的多数据源接入、身份认证、权限控制和安全加固功能，使 Text-to-SQL 服务能够安全地连接多个企业数据源并提供细粒度的访问控制。

## 新增功能

### 1. 多数据源适配器

支持同时连接多个不同类型的数据源，每个数据源拥有独立的连接池和健康监控。

**支持的数据源类型：**
- PostgreSQL
- MySQL  
- Snowflake
- SQLite

**特性：**
- 独立连接池管理（pool_size、max_overflow、pool_recycle）
- SSL/TLS 加密连接
- 语句超时控制（statement_timeout_ms）
- 只读模式强制（read_only）
- 实时健康检查
- 故障隔离与自动重连

**配置示例：**
```bash
DATASOURCES='{"prod_postgres": {"type": "postgresql", "url": "postgresql://user:pass@host/db", "pool_size": 10, "read_only": true, "ssl_required": true}}'
```

### 2. JWT/OIDC 认证

标准的 JWT 令牌验证，支持与企业 SSO/OIDC 系统集成。

**特性：**
- JWT 令牌解析与验证
- 自定义声明提取（tenant_id、roles、permissions）
- 发行者（issuer）和受众（audience）验证
- 令牌过期检查
- 请求上下文追踪（IP、User-Agent）
- 匿名访问支持（认证禁用时）

**配置示例：**
```bash
AUTH_ENABLED=true
JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256
JWT_ISSUER=https://sso.company.com
REQUIRE_TENANT_CLAIM=true
```

### 3. RBAC 授权

基于角色的访问控制（Role-Based Access Control），支持多角色权限聚合。

**内置角色：**
- **admin**: 完全权限（查询执行、目录读取、数据源管理、系统管理）
- **analyst**: 分析师权限（查询执行、SQL 解释、目录读取）
- **viewer**: 查看者权限（仅目录读取）
- **anonymous**: 匿名用户（认证禁用时，具有基础查询和目录权限）

**特性：**
- 角色权限聚合（一个用户可拥有多个角色）
- 端点级权限检查
- 用户级权限覆盖
- 403 权限拒绝响应

### 4. 细粒度权限引擎

动态的表列级权限控制，支持运行时权限计算。

**特性：**
- 表级访问控制（允许/拒绝特定表）
- 列级白名单（allowed_columns）
- 列级黑名单（denied_columns）
- 行级过滤（row_filter）
- 通配符匹配（tenant_id="*"）
- 角色权限组合
- 数据域隔离

**配置示例：**
```python
DataPermission(
    tenant_id="*",
    datasource="primary",
    table="customers",
    denied_columns=["email", "phone", "ssn"]
)
```

### 5. 安全中间件

**IP 白名单：**
- CIDR 格式支持（如 192.168.1.0/24）
- 多段 IP 地址配置
- 403 拒绝响应

**速率限制：**
- 按 IP 地址计数
- 滑动窗口算法
- 429 Too Many Requests 响应
- 可配置限流阈值

**配置示例：**
```bash
IP_WHITELIST=192.168.1.0/24,10.0.0.0/8
RATE_LIMIT_PER_MINUTE=60
```

### 6. 增强审计日志

扩展的审计日志记录，包含完整的用户上下文和安全标记。

**新增字段：**
- `user_id`: 用户标识
- `tenant_id`: 租户标识
- `ip_address`: 客户端 IP 地址
- `user_agent`: 客户端 User-Agent
- `roles`: 用户角色列表
- `datasource`: 查询的数据源
- `contains_pii`: 是否包含 PII 敏感数据（自动检测）
- `execution_ms`: 查询执行耗时

**自动 PII 检测：**
基于 SQL 关键词自动标记可能包含个人身份信息的查询。

### 7. 新增 API 端点

**GET /v1/datasources**（需要 admin 权限）
- 列出所有已配置的数据源
- 返回数据源名称列表

**GET /health**（增强）
- 新增认证状态（auth_enabled）
- 新增数据源健康状态（datasources）
- 每个数据源的可用性检查

## 改进

### 测试覆盖

新增 11 个企业功能测试用例，总计 **27 个测试**：

- **认证授权测试**（4 个）
  - JWT 令牌验证
  - RBAC 权限计算
  - 权限拒绝场景
  - 管理员权限

- **权限引擎测试**（4 个）
  - 通配符匹配
  - 表级匹配
  - 列过滤
  - 表访问控制

- **数据源管理测试**（3 个）
  - 多数据源注册
  - 健康检查
  - 工厂模式

### 文档

- **企业部署指南**：完整的生产环境部署说明
- **使用指南**：包含实际场景和代码示例
- **迁移指南**：从 v0.2.0 升级说明
- **配置参考**：所有新增配置项的详细说明

### 配置

- 新增 20+ 个配置项
- 完整的 `.env.example` 模板
- 支持 JSON 格式的复杂配置

## Breaking Changes

### API 变更

**QueryRequest 模型：**
- 新增 `datasource` 字段（可选，默认值 `"primary"`）

**QueryResponse 模型：**
- 新增 `datasource` 字段（返回实际使用的数据源）

### 审计日志

- 日志格式扩展（新增多个字段）
- 向后兼容：现有字段保持不变，仅新增字段

### 行为变更

- 认证启用时，所有端点默认需要有效的 JWT 令牌
- 匿名访问仅在 `AUTH_ENABLED=false` 时可用
- 查询请求自动从 JWT 提取 `tenant_id` 和 `user_id`

## 安全威胁防护

| 威胁类型 | 防护措施 |
|---------|---------|
| SQL 注入 | AST 解析 + 参数化查询 + SQLGlot 验证 |
| 数据泄露 | 租户隔离 + 敏感列脱敏 + 行级过滤 |
| 权限提升 | JWT 验证 + RBAC 强制 + 租户声明检查 |
| 拒绝服务 | 速率限制 + 查询超时 + 行数限制 + 连接池 |
| 跨租户访问 | 自动租户过滤 + JOIN/CTE 隔离 |
| 未授权访问 | JWT 认证 + IP 白名单 + 角色权限 |
| PII 泄露 | 敏感列配置 + 结果脱敏 + 审计标记 |

## 安装与部署

### 依赖变更

新增依赖：
```
python-jose[cryptography]>=3.3.0
```

### 安装步骤

```bash
# 克隆仓库并进入本发布包
git clone https://github.com/christiek673-mAth/try_by_vscode.git
cd try_by_vscode/archives/enterprise-text-to-sql-v0.3.0

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp config/.env.example .env
# 编辑 .env 文件，配置数据源和认证信息

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Docker 部署

```bash
docker build -t enterprise-text-to-sql:v0.3.0 .
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/.env:/app/.env:ro \
  -v /var/log/text-to-sql:/app/data \
  --name text-to-sql \
  enterprise-text-to-sql:v0.3.0
```

## 升级指南

### 从 v0.2.0 升级

1. **更新依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **更新配置文件**
   - 参考 `config/.env.example` 添加新配置项
   - 至少需要配置：`DATASOURCES`、`DEFAULT_DATASOURCE`

3. **测试兼容性**
   ```bash
   pytest tests/
   ```

4. **可选：启用认证**
   - 生产环境建议设置 `AUTH_ENABLED=true`
   - 配置 JWT 密钥和签名算法

5. **更新客户端代码**
   - 如果使用认证，添加 `Authorization: Bearer <token>` 请求头
   - 可选指定 `datasource` 字段选择数据源

### 数据迁移

本版本无数据库 schema 变更，审计日志格式向后兼容。

## 已知限制

- 向量检索未集成，当前使用简单关键词匹配
- 连接池配置为全局共享，未按数据源独立定制
- 审计日志使用 JSONL 文件，生产环境建议集成日志收集系统
- 未实现查询成本追踪和配额管理

## 技术栈

- **Python**: 3.8+
- **框架**: FastAPI、SQLAlchemy
- **认证**: python-jose (JWT)
- **数据库**: PostgreSQL、MySQL、Snowflake、SQLite
- **测试**: pytest
- **容器**: Docker

## 文件清单

```
archives/enterprise-text-to-sql-v0.3.0/
├── app/                      # 应用核心代码
│   ├── auth.py              # JWT 认证与 RBAC 授权
│   ├── datasource.py        # 多数据源适配器
│   ├── permissions.py       # 权限引擎
│   ├── security.py          # 安全中间件
│   ├── audit.py             # 审计日志（增强）
│   ├── main.py              # FastAPI 应用入口
│   ├── service.py           # 查询服务层
│   └── ...                  # 其他模块
├── tests/                    # 测试用例
│   ├── test_auth.py         # 认证测试
│   ├── test_permissions.py  # 权限测试
│   ├── test_datasource.py   # 数据源测试
│   └── ...                  # 其他测试
├── config/                   # 配置模板
│   └── .env.example
├── docs/                     # 项目文档
│   ├── CONTRIBUTING.md
│   ├── RELEASE_NOTES.md      # 本文件
│   └── SECURITY.md
├── README.md                # 项目文档
├── requirements.txt         # Python 依赖
├── Dockerfile               # Docker 镜像
└── ...                      # 其他配置文件
```

## 支持与反馈

- **GitHub 仓库**: https://github.com/christiek673-mAth/try_by_vscode
- **问题反馈**: https://github.com/christiek673-mAth/try_by_vscode/issues
- **版本标签**: https://github.com/christiek673-mAth/try_by_vscode/releases/tag/v0.3.0

## 贡献者

感谢所有贡献者的辛勤付出！

## License

本项目基于 [MIT License](../LICENSE) 发布。

---

**祝您部署顺利！如有问题，请查阅 README.md 或提交 Issue。**
