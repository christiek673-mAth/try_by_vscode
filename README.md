# try_by_vscode

这是一个使用 **Monorepo（多项目仓库）** 结构组织的实验与应用项目集合。每个独立项目都放在 `projects/` 下，拥有自己的源码、测试、依赖和运行文档。

## 项目索引

| 项目 | 状态 | 说明 |
| --- | --- | --- |
| [Enterprise Text-to-SQL](projects/enterprise-text-to-sql/) | Active | 面向企业数据分析的安全 Text-to-SQL 服务，当前版本为 v0.4.0 |
| [法律知识殿堂](projects/legal-mind-palace/) | Active | 面向法律工作者的个人 RAG 知识库：保留法规编、章、节、条层级上下文的法条检索与生成核心 |

## 历史归档

- [Enterprise Text-to-SQL v0.3.0](archives/enterprise-text-to-sql-v0.3.0/)：历史版本快照，仅用于版本对照和迁移参考。

## 仓库结构

```text
try_by_vscode/
├── projects/                         # 独立项目
│   └── enterprise-text-to-sql/       # 当前维护的 Enterprise Text-to-SQL
│   └── legal-mind-palace/             # 法律工作者 RAG 知识殿堂
├── archives/                         # 历史版本快照
│   └── enterprise-text-to-sql-v0.3.0/
├── .github/workflows/                # 仓库及项目 CI
├── .gitignore
├── LICENSE
└── README.md                         # 仓库级项目索引
```

## 快速开始

进入具体项目目录后，按照该项目 README 操作：

```bash
cd projects/enterprise-text-to-sql
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
make check
make run
```

更多功能、配置、API 和部署说明，请查看 [Enterprise Text-to-SQL 项目文档](projects/enterprise-text-to-sql/README.md)。
法律法规检索与生成说明，请查看[法律知识殿堂项目文档](projects/legal-mind-palace/README.md)。

## 版本管理约定

- 独立项目的源代码放在 `projects/<project-name>/`。
- 历史版本优先使用 Git tag 和 GitHub Release 管理；必须保留在仓库内的快照放在 `archives/`。
- 新项目应自包含依赖、测试、README 和 CI 配置，避免依赖仓库根目录的 Python 包路径。

## 许可证

本仓库及其项目基于 [MIT License](LICENSE) 发布。