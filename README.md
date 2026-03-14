# HR手册智能问答机器人

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

## Web Server 模式

除 CLI 外还支持 HTTP 服务，提供 **per-user 独立记忆** 和 **相同问题缓存**。

### 启动服务

```bash
python -m src.server
# 或
uvicorn src.server:app --host 0.0.0.0 --port 8000
```

服务启动后访问 `http://localhost:8000/docs` 查看交互式 API 文档。


### 配置

在 `.env` 中新增：

| 变量 | 说明 |
|------|------|
| `SERVER_HOST` | 监听地址，默认 `0.0.0.0` |
| `SERVER_PORT` | 监听端口，默认 `8000` |
| `ADMIN_API_KEY` | 管理员接口鉴权密钥（**必填**，否则管理接口返回 503） |

### API 接口

#### 1. 用户问答 — `POST /api/ask`

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_001", "question": "年假有多少天？"}'
```

**请求体**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_id` | string | 用户唯一标识（1-128 字符） |
| `question` | string | 用户问题（1-2000 字符） |
| `debug` | bool | 可选，是否返回调试信息，默认 false |

**响应**：

```json
{
  "answer": "根据手册规定，员工入职满一年后享有5天年假...",
  "source": "agent",
  "trace_id": "a1b2c3d4-...",
  "cached": false
}
```

- `source` 可能的值：`agent`（正常回答）、`cache`（命中缓存）、`intent_not_related`、`no_relevant_chunks`
- `cached: true` 表示该用户之前问过完全相同的问题，直接返回缓存结果

**用户记忆机制**：
- 每个 `user_id` 首次提问时自动创建一个独立的 Letta Agent
- Letta Agent 天然维护该用户的对话历史，实现连续对话上下文
- 相同问题（忽略大小写和首尾空格）直接返回缓存，不重复调用 RAG

#### 2. 查看活跃用户 — `GET /api/admin/users`

```bash
curl http://localhost:8000/api/admin/users \
  -H "X-Admin-Key: your-admin-key"
```

返回所有活跃用户的会话信息：

```json
[
  {
    "user_id": "user_001",
    "agent_id": "agent-xxxx",
    "created_at": 1710403200.0,
    "cached_questions": 5
  }
]
```

#### 3. 清空用户记忆 — `DELETE /api/admin/users/{user_id}/memory`

```bash
curl -X DELETE http://localhost:8000/api/admin/users/user_001/memory \
  -H "X-Admin-Key: your-admin-key"
```

该操作会：
- 删除该用户的 Letta Agent（清空对话历史）
- 清空该用户的问答缓存
- 用户下次提问时会自动创建全新的 Agent

返回：

```json
{"success": true, "message": "Memory cleared for user user_001"}
```

#### 4. 健康检查 — `GET /api/health`

```bash
curl http://localhost:8000/api/health
```

### 管理员后台管理

所有 `/api/admin/*` 接口需要在请求头中携带 `X-Admin-Key`，值必须与 `.env` 中的 `ADMIN_API_KEY` 一致，否则返回 403。若服务端未配置 `ADMIN_API_KEY`，管理接口返回 503。

#### 鉴权方式

每个管理请求都需要添加 Header：

```
X-Admin-Key: <你在 .env 中设置的 ADMIN_API_KEY>
```

#### 典型管理场景

**场景一：某用户反馈回答不对，需要重置其会话**

```bash
# 1. 先查看该用户的会话状态
curl http://localhost:8000/api/admin/users \
  -H "X-Admin-Key: your-admin-key"

# 2. 清空该用户的记忆（删除 Agent + 缓存）
curl -X DELETE http://localhost:8000/api/admin/users/user_001/memory \
  -H "X-Admin-Key: your-admin-key"

# 用户下次提问时会自动创建全新的 Agent，从零开始对话
```

**场景二：批量清理不活跃用户**

```bash
# 列出所有用户，根据 created_at 判断是否过期
curl http://localhost:8000/api/admin/users \
  -H "X-Admin-Key: your-admin-key"

# 逐个清理
curl -X DELETE http://localhost:8000/api/admin/users/old_user_123/memory \
  -H "X-Admin-Key: your-admin-key"
```

**场景三：知识库更新后，清空所有用户缓存**

当重新执行 `python ingest_hr_manual.py` 更新了知识库后，旧的缓存答案可能过时。此时应清空所有用户记忆：

```bash
# 获取所有 user_id
USERS=$(curl -s http://localhost:8000/api/admin/users \
  -H "X-Admin-Key: your-admin-key" | python -c "
import sys, json
for u in json.load(sys.stdin):
    print(u['user_id'])
")

# 逐个清空
for uid in $USERS; do
  curl -X DELETE "http://localhost:8000/api/admin/users/$uid/memory" \
    -H "X-Admin-Key: your-admin-key"
done
```

#### 管理接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/admin/users` | 列出所有活跃用户（user_id、agent_id、创建时间、缓存问题数） |
| `DELETE` | `/api/admin/users/{user_id}/memory` | 清空指定用户的 Letta Agent 和问答缓存 |
| `GET` | `/api/health` | 健康检查（含 `db_pool` 数据库连接状态，无需鉴权） |

#### 清空记忆的效果

执行 `DELETE /api/admin/users/{user_id}/memory` 后：

| 项目 | 效果 |
|------|------|
| Letta Agent | 删除，对话历史清零 |
| 问答缓存 | 清空，相同问题会重新走 RAG 流程 |
| 用户下次提问 | 自动创建全新 Agent，如同首次访问 |

## 项目结构

- `src/config.py` — 环境变量与可配置项（含 RAG_TOP_K、RAG_SIMILARITY_THRESHOLD）
- `src/chunking.py` — PDF 按章节分块
- `src/embedding.py` — OpenAI 向量化
- `src/vector_store.py` — asyncpg 连接池 + pgvector 建表/插入/检索
- `src/intent.py` — 显式意图：是否与 HR 手册相关
- `src/letta_agent.py` — Letta Agent 创建与调用（含 per-user Agent）
- `src/query.py` — 问答主流程（意图 → 检索 → Agent/「我不知道」）+ trace_id/DEBUG
- `src/user_manager.py` — 用户会话管理（Agent 映射 + 问答缓存）
- `src/server.py` — FastAPI Web Server（HTTP API + 管理员接口）
- `ingest_hr_manual.py` — 入库入口
- `create_agent.py` — 一次性创建 Agent

## 流程简述

1. **意图**：先判断问题是否与 HR 手册相关；不相关则直接回答「我不知道」，不检索。
2. **检索**：对问题做 embedding，在 pgvector 中按余弦相似度取 top_k，仅保留相似度 ≥ 阈值的 chunk。
3. **回答**：若有有效 chunk，将内容拼成上下文交给 Letta Agent 生成答案；否则回答「我不知道」。

### Web Server 模式流程

```
用户请求 (user_id + question)
    │
    ├─ 缓存命中？ ──是──▶ 直接返回缓存结果 (source=cache)
    │
    ├─ 该用户首次？──是──▶ 创建 per-user Letta Agent
    │
    ├─ 意图判断 ──不相关──▶ 返回「我不知道」
    │
    ├─ 向量检索 ──无结果──▶ 返回「我不知道」
    │
    └─ 调用该用户的 Letta Agent（带上下文）──▶ 返回答案 + 缓存
```
