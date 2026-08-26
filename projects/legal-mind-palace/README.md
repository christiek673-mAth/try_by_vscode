# 法律知识殿堂（Legal Mind Palace）

一个面向中文法律法规的本地 RAG（检索增强生成）工具。它把法规按**条**解析并保留完整的“法律 → 编 → 章 → 节 → 条”路径，再使用 Chroma 向量库检索相关法条，最后交给 DeepSeek、Qwen 或其他 OpenAI 兼容模型生成分析结果。

> **重要提示**：本项目仅用于法条检索和研究辅助，不构成法律意见。法规文本、效力状态、版本和模型输出均须由具备资质的法律专业人士，依据权威来源独立核验。

## 特性

- **按法条索引**：默认不会用通用文本切分器将一条法规截断；超长条文才会在段落或句子边界切分。
- **保留层级上下文**：每个片段都会带上法律名称、编、章、节、条号，既写入向量文本，也传给模型。
- **兼容多种语料**：支持 `.md`、`.markdown`、`laws.json` 和 `laws.json.zip`。
- **识别常见法规结构**：支持 `第一编`、`第二章`、`第三节`、`第十八条`、`第十条之一`，以及 `总则`、`附则` 等无编号标题。
- **保存来源元数据**：可保存发布机关、文号、公布/施行/失效日期、效力状态、版本、权威 URL、来源文件哈希等。
- **增量建库**：未变更的来源自动跳过；变更来源会替换旧向量；从语料目录删除的来源会清理对应向量。
- **可追溯回答**：每次回答都返回由系统生成的 `[C1]` 等引用及原文片段、来源 URL、效力状态和完整层级路径。
- **本地网页对话**：内置单页 Web 对话界面，模型密钥只保存在服务端环境变量，浏览器不会接触密钥。
- **索引安全护栏**：清单绑定 collection、嵌入模型和切分参数；更换配置时拒绝增量混用并要求 `--reset`。

## 工作流程

```text
法规文件（Markdown / laws.json / laws.json.zip）
                 ↓
         按编、章、节、条解析
                 ↓
  带完整层级与来源元数据的 Document
                 ↓
      BGE 中文嵌入 → Chroma 向量库
                 ↓
       检索法条 → OpenAI 兼容模型回答
```

例如，`第十八条` 进入向量库时会包含完整语义归属：

```text
【法律层级】中华人民共和国民法典 > 第一编 总则 > 第二章 自然人 > 第一节 民事权利能力和民事行为能力 > 第十八条
【条文内容】
第十八条
成年人为完全民事行为能力人，可以独立实施民事法律行为。
```

这样即使不同法规中存在相同条号，检索与回答也不会丢失所属法律和目录上下文。

## 快速开始

### 1. 安装

需要 Python 3.10+，推荐 Python 3.11。

```bash
git clone https://github.com/christiek673-mAth/try_by_vscode.git
cd try_by_vscode/projects/legal-mind-palace

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

首次构建索引时，`sentence-transformers` 会下载默认嵌入模型 `BAAI/bge-small-zh-v1.5`。默认使用 CPU；如环境已正确安装相应 PyTorch 支持，可在命令中使用 `--device cuda` 或 `--device mps`。

### 2. 准备语料

将已获授权且已核验的法规文件放在一个目录中，例如：

```text
my-laws/
├── 法律/
│   └── 中华人民共和国民法典.md
└── 行政法规/
    └── 示例条例.markdown
```

### 2.1 准备首批中央法律 P0 导入目录

项目内置的是**法规目录和核验规则，不是法规全文**。这样不会把来源平台未明确授权再分发的文本提交到 Git，也不会把“公开可浏览”误当作批量使用授权。

P0 清单包含宪法、民法典、刑法、三大诉讼法、劳动/公司/数据/知识产权/消费者保护等 20 部中央法律，版本受控模板位于 `catalogs/central-laws-p0.json`；官方来源目录位于 `catalogs/official-sources.yaml`。运行：

```bash
python -m app.cli prepare-p0 \
  --source-dir data/authorized-laws \
  --metadata-file data/catalogs/central-laws-p0.json
```

该命令创建被 Git 忽略的法规目录，并把 P0 元数据模板复制到被 Git 忽略的位置。逐份在[国家法律法规数据库](https://flk.npc.gov.cn/)查找原文、核对标题/发布机关/公布和施行日期/效力状态后：

1. 将正文保存为清单指定的文件名（例如 `data/authorized-laws/中央法律/中华人民共和国民法典.md`）；
2. 将清单中对应记录的 `source_url` 替换为该法规的**官方详情页 URL**；
3. 填写或确认 `issuing_authority`、日期、文号和 `revision_version`；
4. 仅在官方详情页确认后，将 `legal_status` 改为 `现行有效`，同时更新 `verified_at`；
5. 运行严格校验：

```bash
python -m app.cli validate \
  --source-dir data/authorized-laws \
  --catalog-file data/catalogs/central-laws-p0.json
```

严格校验会拒绝缺失法规、清单外法规、标题不一致、非 HTTPS 来源 URL，以及未明确核验为“现行有效”的记录。校验通过后以同一清单建库：

```bash
python -m app.cli index \
  --source-dir data/authorized-laws \
  --metadata-file data/catalogs/central-laws-p0.json \
  --db-dir data/chroma \
  --reset
```

在已取得本地内部研究授权的前提下，可运行 `python scripts/prepare_p0_official.py`，从国家法律法规数据库逐份检索现行有效记录、下载官方 DOCX、生成本地 Markdown 并写入被 Git 忽略的 `data/` 目录。脚本会记录官方详情页 URL、发布/施行日期和核验日期；法规正文、下载的 DOCX 和向量库均不会提交 Git。

也可以直接使用目录中的 `laws.json` 或 `laws.json.zip`。程序会递归扫描以下文件：

```text
*.md
*.markdown
laws.json
laws.json.zip
```

### 3. 首次构建索引

将 `/path/to/my-laws` 替换为你的法规根目录：

```bash
python -m app.cli index \
  --source-dir /path/to/my-laws \
  --db-dir data/chroma \
  --reset
```

成功后，索引保存在 `data/chroma/`。该目录已被 `.gitignore` 忽略，不会提交向量库或法规副本。

### 4. 启动网页对话

先设置模型服务环境变量，再启动本地服务：

```bash
export LEGAL_LLM_API_KEY='你的 API Key'
export LEGAL_LLM_BASE_URL='https://api.deepseek.com/v1'
export LEGAL_LLM_MODEL='deepseek-chat'

python -m app.cli serve --db-dir data/chroma
```

浏览器打开 <http://127.0.0.1:8000> 即可对话。默认只监听本机；不要在未配置登录、HTTPS、限流和审计日志的情况下将其暴露到公网。

### 5. 配置模型并使用 CLI 提问

项目使用 `langchain-openai`，支持 DeepSeek、Qwen 等 OpenAI API 兼容服务。

以 DeepSeek 为例：

```bash
export LEGAL_LLM_API_KEY='你的 API Key'
export LEGAL_LLM_BASE_URL='https://api.deepseek.com/v1'
export LEGAL_LLM_MODEL='deepseek-chat'

python -m app.cli query \
  --db-dir data/chroma \
  --question '17岁且以劳动收入为主要生活来源的人独立购买手机，合同效力应如何分析？'
```

如使用其他兼容服务，只需替换上述三个环境变量：

```bash
export LEGAL_LLM_API_KEY='你的 API Key'
export LEGAL_LLM_BASE_URL='服务商提供的 OpenAI 兼容地址'
export LEGAL_LLM_MODEL='服务商模型名'
```

## 常用命令

### 日常更新索引

日常更新**不要**加 `--reset`。程序会在 `data/chroma/manifests/<collection>.json` 中同时保存来源内容、元数据指纹和索引配置：

```bash
python -m app.cli index --source-dir /path/to/my-laws --db-dir data/chroma
```

| 来源情况 | 执行行为 |
| --- | --- |
| 文件未变更 | 跳过，不重复写入 |
| 文本或导入元数据变更 | 替换该来源的旧向量 |
| 文件已变更 | 删除该来源的旧向量，再写入新向量 |
| 文件已从语料目录删除 | 删除该来源遗留的向量 |
| 需要彻底重建 | 加 `--reset` |

更换 `--collection`、`--embedding-model` 或 `--max-article-chars` 后，必须加 `--reset` 重建，避免不同嵌入或切分方式混入同一索引。

### 索引前校验语料

```bash
python -m app.cli validate --source-dir /path/to/my-laws
```

该命令只解析语料并输出片段/来源数量，不下载嵌入模型也不写入 Chroma，适合在生产导入前发现缺文件、损坏 JSON/ZIP 或 Git LFS 指针。

### 指定检索数量和模型设备

```bash
# 返回前 8 条检索结果
python -m app.cli query --db-dir data/chroma --top-k 8 --question '你的问题'

# 使用 Apple Silicon MPS 或 CUDA 建库（需环境支持）
python -m app.cli --device mps index --source-dir /path/to/my-laws
python -m app.cli --device cuda index --source-dir /path/to/my-laws
```

### 使用 Makefile

```bash
# 安装开发依赖、运行检查
make install
make check

# 建库和提问
LAW_SOURCE_DIR=/path/to/my-laws make index
QUESTION='限制民事行为能力人的法律依据是什么？' make query
```

## Markdown 语料格式

支持标准 Markdown 标题和正文形式的法规目录。以下是推荐写法：

```markdown
# 示例法

## 第一编 总则

### 第一章 一般规定

#### 第一条
为了规范示例事项，制定本法。

#### 第二条
本法适用于示例活动。
```

无编号目录同样支持：

```markdown
# 示例条例

## 总则

### 第一条
本条例适用于示例事项。

## 附则

### 第二条
本条例自公布之日起施行。
```

程序还可以识别没有 `#` 的 `第一章`、`第一条` 等正文行，以及 `第十条之一` 形式的条文编号。

## 法规元数据（可选）

对于 Markdown 语料，可通过 `--metadata-file` 提供来源级元数据。创建一个 JSON 文件，键必须是相对于 `--source-dir` 的路径：

```json
{
  "法律/中华人民共和国民法典.md": {
    "issuing_authority": "全国人民代表大会",
    "document_number": "中华人民共和国主席令第四十五号",
    "promulgation_date": "2020-05-28",
    "effective_date": "2021-01-01",
    "expiration_date": "",
    "legal_status": "现行有效",
    "revision_version": "2020年制定",
    "last_updated_at": "2026-08-23",
    "source_url": "https://权威来源.example/",
    "jurisdiction": "中华人民共和国"
  }
}
```

建库时传入该文件：

```bash
python -m app.cli index \
  --source-dir /path/to/my-laws \
  --metadata-file /path/to/law-metadata.json \
  --db-dir data/chroma
```

支持的字段如下：

| 字段 | 含义 |
| --- | --- |
| `issuing_authority` | 发布机关 |
| `legal_level` | 法规层级，例如“法律” |
| `document_number` | 文号 |
| `promulgation_date` | 公布日期 |
| `effective_date` / `expiration_date` | 施行 / 失效日期 |
| `legal_status` | 效力状态 |
| `revision_version` / `last_updated_at` | 修订版本 / 上游更新时间 |
| `verified_at` | 导入者最后人工核验日期 |
| `source_url` | 权威来源 URL |
| `source_name` | 来源名称，例如“国家法律法规数据库” |
| `jurisdiction` | 管辖区域 |
| `license_note` | 本地保存、内部使用或再分发的授权/限制说明 |

空字段表示来源未提供。项目只保存这些值，**不会自动判断法规是否现行有效**；请由语料导入者负责核验。

## `laws.json` / `laws.json.zip` 语料

程序兼容包含法规数组的 JSON 快照，并会读取常见字段：

| JSON 字段 | 保存为的元数据 |
| --- | --- |
| `title` | 法律名称 |
| `office` | `issuing_authority` |
| `publish` | `promulgation_date` |
| `expiry` | `expiration_date` |
| `status` | `legal_status`（保留原始值） |
| `url` | `source_url` |
| `id` | `source_record_id` |
| `content` | Markdown 形式的法规正文 |

如果使用 Git LFS 管理的 ZIP 文件，必须先安装并执行 `git lfs pull`。未拉取 LFS 对象时，本地只有一个文本指针，无法建立索引。

## 关于 `twang2218/law-datasets` 快照

已确认可访问的候选仓库为 https://github.com/twang2218/law-datasets ，其 `law-and-regulations/laws.json.zip` 为 Git LFS 文件，仓库采集脚本指向 [全国人大法律法规库](https://flk.npc.gov.cn/)。可在已完成合规确认后按以下方式获取：

```bash
git lfs install
git clone https://github.com/twang2218/law-datasets.git /path/to/law-datasets
cd /path/to/law-datasets && git lfs pull
```

**请在使用前注意以下限制：**

1. 该候选仓库在确认时未声明许可证，且未发现 `LICENSE`、`COPYING` 或 `NOTICE` 文件；使用、再分发或商用前必须自行获得明确授权并核验来源平台规则。
2. 已记录的候选快照提交为 `d8df38c4578f0b5627b51da29ede0f8cfeb98302`，时间为 `2023-09-02T20:09:13Z`，不能代表当前有效法规或权威发布版本。
3. 项目不提交第三方法规原文、LFS 数据或生成的向量库。生产场景应接入已获授权、可持续更新的权威数据源，并逐条复核法律状态。

## 项目结构

```text
legal-mind-palace/
├── app/
│   ├── cli.py                 # index / query 命令行入口
│   ├── markdown_processor.py  # 法规解析、层级和元数据处理
│   └── rag.py                 # 嵌入、Chroma 索引和问答链
├── tests/                     # 单元测试
├── requirements.txt           # 运行依赖
├── requirements-dev.txt       # 开发与测试依赖
└── Makefile                   # 常用命令
```

## 开发与验证

```bash
make check
```

该命令会执行 Ruff、Pytest、Python 编译检查和 Git whitespace 检查。

## 当前验证范围

已通过单元测试验证：Markdown/JSON 快照解析、无编号目录、法规元数据、增量索引清单、变更/删除来源的处理和 CLI 元数据加载。

当前开发环境尚未安装 Git LFS、Chroma、HuggingFace 嵌入模型或 `sentence-transformers`，因此尚未对真实 LFS 全量语料完成 BGE/Chroma 端到端建库，也未执行真实模型 API 调用。使用前请在目标环境中完成依赖安装和端到端验收。