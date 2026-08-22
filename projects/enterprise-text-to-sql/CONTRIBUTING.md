# Contributing

感谢你对 Enterprise Text-to-SQL 的关注。这个项目优先接受能提升安全性、可测试性、可观测性和数据库兼容性的改动。

本文中的项目命令应从 `projects/enterprise-text-to-sql/` 目录执行。

## 开发环境

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
```

## 提交前检查

```bash
ruff check app tests
pytest -q
python -m compileall -q app tests
git diff --check
```

## 代码约定

- 保持 Python 3.8 兼容，除非先讨论升级支持范围。
- 安全策略必须有回归测试，尤其是租户隔离、只读限制和敏感字段处理。
- 不提交 `.env`、API Key、数据库文件、审计日志或真实企业数据。
- 对外部模型和数据库依赖使用适配层，避免在接口路由中耦合供应商实现。
- PR 描述应说明行为变化、测试方式和生产风险。

## Pull Request

1. 为行为变化添加或更新测试。
2. 说明是否影响 SQL 方言、权限模型或数据暴露边界。
3. 保持单个 PR 聚焦，避免混入无关格式化或重命名。