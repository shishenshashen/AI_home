---
name: memory-v2
description: 从state.db提取有价值对话记忆到memory_v2.db，实现长期记忆积累，支持语义向量检索
triggers:
  - 每小时cron自动增量提取
  - 会话结束钩子
  - 手动批量回填历史会话
  - 语义向量回填（新功能 2026-04-29）
---

# Memory V2 — 记忆提取系统 Skill

## 概述

从 Hermes Agent 的 state.db 中提取有价值对话记忆，存入 memory_v2.db。
- **替代**：旧的固定 2.2K 字符槽位
- **优势**：无限存储、自动去重、语义检索（Hybrid Search）

## 检索机制

```
query → FTS5 关键词粗筛 50 条（候选）
      → 生成 query_embedding（256维，ModelScope 模型）
      → Python 余弦相似度重排候选集
      → 综合分 = 0.5×语义 + 0.25×重要性 + 0.15×原子化 + 0.1×命中次数
      → top_k 返回
```
**降级**：模型加载失败时自动回退到 Jaccard 关键词排序。

## 核心原则

1. **只记高价值**：`reward` + `insight` + `error` + `constraint` + `preference`
2. **不记闲聊**：确认语、重复语、礼貌废话全过滤
3. **历史精简**：476个历史会话一次性精简，之后增量
4. **自动去重**：Jaccard 相似度 > 80% 跳过

## 数据源

- **state.db**: `~/.hermes/state.db`
- **memory_v2.db**: `~/.hermes/memory_v2.db`

## DB 表结构

```sql
memory_index(id, content, category, tags, importance, hit_count,
             embedding, ...)   -- embedding: TEXT (256维 JSON 数组)
topics(id, name, keywords, hot_score, ...)
session_topics(session_id, topic_id, relevance)
knowledge_graph(...)
```

## 用法

```bash
# 批量提取历史会话
python3 batch_extractor.py --mode compact --limit 476

# 回填历史记忆的语义向量（首次一次性）
python3 batch_extractor.py --backfill-embeddings

# 每小时 cron 增量
python3 hourly_extractor.py

# 检索
python3 recall_v2.py 模型配置

# 统计
python3 memory_v2.py stats
```

## 两种提取模式

### mode='compact'（历史一次性）

只提取 5 类高价值记忆，跳过确认噪音：
- `reward`：✅完成/成功推送/配置完成
- `insight`：找到问题/原因/搞清楚/关键
- `error`：Traceback/报错/失败
- `constraint`：禁止/红线/必须/原则
- `preference`：偏好/喜欢/讨厌/希望

### mode='full'（每小时增量）

同 compact，额外记录 `fact` + `event`。

## 关键文件

| 文件 | 作用 |
|------|------|
| `scripts/embed.py` | 语义向量生成（256维，ModelScope） |
| `scripts/session_extractor.py` | 核心引擎：`auto_memorize()` |
| `scripts/batch_extractor.py` | 批量提取 + `--backfill-embeddings` |
| `scripts/hourly_extractor.py` | cron 专用入口 |
| `scripts/recall_v2.py` | 语义检索工具 |
| `scripts/memory_v2.py` | DB 操作库 + CLI stats/cluster/cold |
| `scripts/memory_client.py` | MemoryClient 封装类 |
| `memory_v2.db` | 记忆数据库（含 embedding 字段） |

## 依赖

- `modelscope`（从魔搭下载 embedding 模型）
- `transformers` + `torch`（已有）
- `numpy`（已有）

**首次使用**：自动下载模型 33MB 到 `~/.hermes/embedding_model/`

## 常见用法示例

```python
from memory_v2 import remember, recall, create_topic, relate, stats

# 记忆一条
remember("飞书表格write是覆盖模式", category="insight", importance=4, tags=["飞书"])

# 检索
results = recall("飞书", category="insight", limit=5)
for r in results:
    print(f"[{r['category']}] {r['content']}")

# 统计
print(stats())
# {'memory': 309, 'topics': 49, 'graph': 0, 'links': 476, 'categories': {...}}

# 维护
cluster_topics()    # 合并相似话题
cold_migration()    # 冷数据归档
```

## 当前状态 (2026-04-29)

| 指标 | 数值 |
|------|------|
| 记忆条目 | 309（全部含语义向量） |
| 话题数 | 49 |
| 图谱关系 | 0 |
| 会话关联 | 476 |
| 数据库大小 | ~1MB |
| Embedding 向量 | 256维 / 条，约 0.9MB |

| 类型 | 数量 |
|------|------|
| reward | 97 |
| insight | 56 |
| preference | 40 |
| fact | 32 |
| event | 32 |
| constraint | 26 |
| error | 24 |

## Pitfalls

1. **HuggingFace 被墙**：embedding 模型必须从 `modelscope.cn` 下载（用 `pip install modelscope`）
2. **batch_extractor.py 硬编码路径**：依赖 `memory-v2` 子目录，克隆到其他位置需修改 `sys.path.insert`
3. **state.db 路径**：生产环境为 `~/.hermes/state.db`，测试时注意路径
4. **去重阈值**：Jaccard > 80% 跳过，阈值可调 `memory_v2.py` 中 `_jaccard_similarity` 调用处
5. **会话来源过滤**：只处理 `source IN ('feishu','cli','weixin')` 的会话
6. **模型首次加载慢**：第一次 `remember`/`recall` 需要 2-3 秒加载模型（已全局缓存），后续调用毫秒级
7. **魔搭下载速度**：~1.2MB/s，共 33MB，约 30 秒
