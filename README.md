# Letta HR 手册智能问答机器人

基于 Letta 的 HR 手册 RAG 问答：PDF 按章节分块、向量存 PostgreSQL（pgvector），显式意图判断后检索，由 Letta Agent 生成答案；无相关结果时回答「我不知道」。

## 环境要求

- Python 3.8+
- PostgreSQL（安装 [pgvector](https://github.com/pgvector/pgvector) 扩展）
- [Letta](https://www.letta.com/) 与 [OpenAI](https://platform.openai.com/) API Key

## 安装

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
```

复制环境变量示例并填写：

```bash
cp .env.example .env
# 编辑 .env：LETTA_API_KEY, OPENAI_API_KEY, DATABASE_URL
```

## 配置说明

| 变量 | 说明 |
|------|------|
| `LETTA_API_KEY` | Letta API 密钥 |
| `OPENAI_API_KEY` | OpenAI API 密钥（embedding + 可选意图） |
| `DATABASE_URL` | PostgreSQL 连接串，例如 `postgresql://user:pass@localhost:5432/hr_rag` |
| `LETTA_AGENT_ID` | 创建 Agent 后填入（见下） |
| `RAG_TOP_K` | 检索返回条数，默认 5 |
| `RAG_SIMILARITY_THRESHOLD` | 相似度阈值 0–1，默认 0.7 |
| `HR_PDF_PATH` | HR 手册 PDF 路径，默认 `HR.pdf` |
| `DEBUG_RAG` | 为 true 时输出检索/推理调试信息 |
| `LOG_LEVEL` | 日志级别，如 INFO、DEBUG |

## 使用步骤

### 1. 创建 PostgreSQL 与 pgvector

在目标库中执行：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 2. 创建 Letta Agent（一次性）

```bash
python create_agent.py
```

将输出的 `LETTA_AGENT_ID` 写入 `.env`。

### 3. 入库 HR 手册

将 `HR.pdf` 放在项目根目录（或设置 `HR_PDF_PATH`），执行：

```bash
python ingest_hr_manual.py
```

脚本会按章节分块、向量化并写入 PostgreSQL（会先删除同来源旧数据，可重复执行）。

### 4. 问答

交互式对话：

```bash
python -m src.query
```

单次提问并查看调试信息：

```bash
python -m src.query --single "年假怎么算" --debug
```

## 调试与 trace_id

每次问答调用都会生成一个唯一的 `trace_id`（UUID），贯穿意图判断、向量检索、Agent 调用的全过程。当回答不符合预期时，可通过 `trace_id` 追踪该请求的完整链路。

### 开启调试的两种方式

**方式一：命令行 `--debug` 参数**

适合单次排查，无需改环境变量：

```bash
python -m src.query --single "年假怎么算" --debug
```

返回结果中会附带 `debug` 字段，包含完整的调试信息。

**方式二：环境变量 `DEBUG_RAG=true`**

适合持续调试，在 `.env` 中设置：

```
DEBUG_RAG=true
LOG_LEVEL=DEBUG
```

此时所有请求都会在日志中输出 trace 信息，交互式模式下也会打印 `[DEBUG]` 块。

### debug 输出字段说明

```json
{
  "trace_id": "a1b2c3d4-...",
  "question": "年假怎么算",
  "intent_related": true,
  "retrieval": {
    "top_k": 5,
    "similarity_threshold": 0.7,
    "num_hits": 3,
    "hits": [
      {
        "chapter_title": "第五章 休假制度",
        "similarity": 0.8721,
        "content_preview": "员工入职满一年后享有..."
      }
    ]
  },
  "context_preview": "员工入职满一年后享有...",
  "agent_reply": "根据手册规定，年假天数..."
}
```

| 字段 | 含义 |
|------|------|
| `trace_id` | 本次请求的唯一标识，可用于在日志中搜索完整链路 |
| `intent_related` | 意图判断结果：`true` 表示与 HR 手册相关，会继续检索；`false` 则直接返回「我不知道」 |
| `retrieval.top_k` | 本次使用的检索条数上限 |
| `retrieval.similarity_threshold` | 本次使用的相似度阈值 |
| `retrieval.num_hits` | 通过阈值筛选后实际返回的 chunk 数量 |
| `retrieval.hits[].similarity` | 每个 chunk 与问题的余弦相似度（越接近 1 越相关） |
| `retrieval.hits[].content_preview` | chunk 内容预览（前 200 字符） |
| `context_preview` | 拼接后发送给 Agent 的上下文预览（前 500 字符） |
| `agent_reply` | Agent 原始回复文本 |
| `embed_error` / `agent_error` | 仅在出错时出现，记录异常信息 |

### 排查示例

**问题：用户提问后返回「我不知道」，但手册中确实有答案**

1. 用 `--debug` 重新提问，查看输出：

```bash
python -m src.query --single "试用期多久" --debug
```

2. 检查 `intent_related`：
   - 若为 `false` → 意图判断将问题误判为不相关，需在 `src/intent.py` 的 `HR_KEYWORDS` 中补充关键词。

3. 检查 `retrieval.num_hits`：
   - 若为 `0` → 没有 chunk 通过相似度阈值，可尝试降低 `RAG_SIMILARITY_THRESHOLD`（如 0.5）或增大 `RAG_TOP_K`。

4. 检查 `retrieval.hits[].similarity`：
   - 若分数偏低（< 0.6）→ 可能是 PDF 分块质量问题，检查 `ingest_hr_manual.py` 的分块结果。

5. 检查 `agent_reply`：
   - 若 Agent 有上下文但仍回答「我不知道」→ 可能是 Prompt 或 Agent 配置需要调优。

### 日志中搜索 trace_id

在 `DEBUG_RAG=true` + `LOG_LEVEL=DEBUG` 下，每个阶段的日志都带有 `trace_id`：

```
2026-03-14 10:30:01 [DEBUG] src.query: trace_id=a1b2c3d4-... stage=intent {"intent_related": true}
2026-03-14 10:30:02 [DEBUG] src.query: trace_id=a1b2c3d4-... stage=retrieval {"top_k": 5, "num_hits": 3, ...}
2026-03-14 10:30:03 [DEBUG] src.query: trace_id=a1b2c3d4-... stage=agent_reply {"agent_reply": "根据手册..."}
```

可直接用 `trace_id` 在日志中 grep 出完整链路：

```bash
grep "a1b2c3d4" app.log
```

## 项目结构

- `src/config.py` — 环境变量与可配置项（含 RAG_TOP_K、RAG_SIMILARITY_THRESHOLD）
- `src/chunking.py` — PDF 按章节分块
- `src/embedding.py` — OpenAI 向量化
- `src/vector_store.py` — asyncpg 连接池 + pgvector 建表/插入/检索
- `src/intent.py` — 显式意图：是否与 HR 手册相关
- `src/letta_agent.py` — Letta Agent 创建与调用
- `src/query.py` — 问答主流程（意图 → 检索 → Agent/「我不知道」）+ trace_id/DEBUG
- `ingest_hr_manual.py` — 入库入口
- `create_agent.py` — 一次性创建 Agent

## 流程简述

1. **意图**：先判断问题是否与 HR 手册相关；不相关则直接回答「我不知道」，不检索。
2. **检索**：对问题做 embedding，在 pgvector 中按余弦相似度取 top_k，仅保留相似度 ≥ 阈值的 chunk。
3. **回答**：若有有效 chunk，将内容拼成上下文交给 Letta Agent 生成答案；否则回答「我不知道」。
