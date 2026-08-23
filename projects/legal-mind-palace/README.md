# 法律知识殿堂（Legal Mind Palace）

面向法律工作者的个人知识殿堂第一期：以中国法律法规 Markdown 为知识源，构建**不丢失法条层级上下文**的检索增强生成（RAG）核心。

项目针对 `twang2218/chinese-law-and-regulations` 风格的法规 Markdown 设计，但不会假定该仓库的固定目录或标题级别：解析器会同时识别 Markdown 标题和正文中的 `第一编`、`第二章`、`第三节`、`第十八条`、`第十条之一` 等结构。

> 法律提示：本项目是法条检索与研究辅助工具，不构成法律意见。输出必须由具备资质的法律专业人士独立复核。

## 设计目标

```text
法规 Markdown
  ↓  解析编 / 章 / 节 / 条（不按固定字符数直接腰斩法条）
完整法条 Document + 层级路径注入
  ↓  BGE 中文向量化
ChromaDB 持久化索引
  ↓  Top-K 检索、来源与完整层级保留
LCEL Prompt → DeepSeek / Qwen 等 OpenAI 兼容模型
```

每个进入向量库的片段都具有以下形态：

```text
【法律层级】中华人民共和国民法典 > 第一编 总则 > 第二章 自然人 > 第一节 民事权利能力和民事行为能力 > 第十八条
【条文内容】
第十八条
成年人为完全民事行为能力人，可以独立实施民事法律行为。
```

层级路径不仅保存在 metadata，也强制写入 embedding 文本和 LLM 上下文。因此单条“第十八条”不会脱离其所属法律、编、章、节而被误解。

## 核心保障

1. **条级切分优先**：一条法条及其段落默认是一个完整检索单元，不使用通用 CharacterSplitter 截断。
2. **父级上下文继承**：处理 `编 → 章 → 节 → 条` 时，下级目录切换会自动清空失效的后代节点，避免把上一章的节错误带入下一章。
3. **超长条文保护**：只有超出 `max_article_chars` 的单条法规才会在段落边界切分；所有子片段都会重复包含完整层级和条号。极端长的单段落才按中文句末标点切分。
4. **幂等索引 ID**：文档 ID 基于来源、层级、分片序号和内容的 SHA-256，重复执行增量索引不会随机生成重复条目。全量重建使用 `--reset`。
5. **可审计回答**：模型上下文包含每条依据的原始来源相对路径、层级路径和增强后的条文；系统提示禁止捏造法条。

## 安装

本项目需要 Python 3.10+（推荐 Python 3.11）。在项目目录中执行：

```bash
cd /Users/chengjing/Documents/RAG/try_by_vscode/projects/legal-mind-palace
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

`sentence-transformers` 首次构建索引时会下载 `BAAI/bge-small-zh-v1.5`。默认使用 CPU；有可用 GPU/MPS 时通过 `--device cuda` 或 `--device mps` 指定。

## 准备法规语料

将已获得的法规 Markdown 仓库放在任意本地目录。例如：

```bash
git clone <你有权限访问的法规 Markdown 仓库地址> /path/to/chinese-law-and-regulations
```

截至本项目创建时，`https://github.com/twang2218/chinese-law-and-regulations` 返回仓库不存在/不可访问，因此没有把网络克隆命令写死为可执行依赖，也没有在本仓库提交第三方法规原文。待确认实际可访问的上游地址和许可后，将其目录传给索引命令即可。

## 构建向量索引

```bash
cd /Users/chengjing/Documents/RAG/try_by_vscode/projects/legal-mind-palace

python -m app.cli index \
  --source-dir /path/to/chinese-law-and-regulations \
  --db-dir data/chroma \
  --reset
```

也可通过 Makefile：

```bash
LAW_SOURCE_DIR=/path/to/chinese-law-and-regulations make index
```

索引默认持久化到 `data/chroma/`，该目录已被项目级 `.gitignore` 排除，不应提交 BGE 缓存、向量库或法规数据副本。

## 法律问答

本程序使用 `langchain-openai`，因而兼容 DeepSeek、Qwen 等 OpenAI API 格式服务。

### DeepSeek 示例

```bash
export LEGAL_LLM_API_KEY='你的 DeepSeek API Key'
export LEGAL_LLM_BASE_URL='https://api.deepseek.com/v1'
export LEGAL_LLM_MODEL='deepseek-chat'

python -m app.cli query \
  --db-dir data/chroma \
  --question '17岁的小明以劳动收入为主要生活来源，独立购买手机的合同效力应如何分析？'
```

### Qwen/OpenAI 兼容服务示例

```bash
export LEGAL_LLM_API_KEY='你的 API Key'
export LEGAL_LLM_BASE_URL='服务商提供的 OpenAI 兼容地址'
export LEGAL_LLM_MODEL='服务商模型名'

python -m app.cli query --question '请说明限制民事行为能力人的法律依据。'
```

可通过 `--top-k 5` 调整召回数。回答会要求模型使用“规则（大前提）—事实适用（小前提）—暂定结论”结构；没有检索依据时，模型必须说明证据不足而不是补造法条。

## 项目结构

```text
projects/legal-mind-palace/
├── app/
│   ├── markdown_processor.py  # 法规目录树、条文级解析、层级注入
│   ├── rag.py                 # Chroma、BGE、LCEL RAG 链
│   └── cli.py                 # index / query 命令行入口
├── tests/
├── Makefile
├── requirements.txt
└── README.md
```

## 开发验证

```bash
make check
```

该命令执行 Ruff、Pytest、Python 编译检查以及 Git whitespace 检查。