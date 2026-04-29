---
name: memory-v2
description: 从state.db提取有价值对话记忆到memory_v2.db，实现长期记忆积累
triggers:
  - 每小时cron自动增量提取
  - 会话结束钩子
  - 手动批量回填历史会话
---

# Memory V2 — 记忆提取系统 Skill

## 概述

从 Hermes Agent 的 state.db 中提取有价值对话记忆，存入 memory_v2.db。
- **替代**：旧的固定 2.2K 字符槽位
- **优势**：无限存储、自动去重、关键词检索

## 核心原则

1. **只记高价值**：`reward` + `insight` + `error` + `constraint` + `preference`
2. **不记闲聊**：确认语、重复语、礼貌废话全过滤
3. **历史精简**：476个历史会话一次性精简，之后增量
4. **自动去重**：Jaccard 相似度 > 80% 跳过

## 数据源

- **state.db**: `~/.hermes/state.db`
- **memory_v2.db**: `~/.hermes/memory_v2.db`

## 用法

```bash
# 测试单会话提取
python3 session_extractor.py <session_id> --mode compact

# 批量提取历史会话（首次回填用）
python3 batch_extractor.py --mode compact --limit 476

# 每小时 cron 增量（自动调用）
python3 hourly_extractor.py

# 检索
python3 recall_v2.py 关键词

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
| `scripts/session_extractor.py` | 核心引擎：`auto_memorize()` |
| `scripts/batch_extractor.py` | 批量提取，支持 `--mode` / `--limit` |
| `scripts/hourly_extractor.py` | cron 专用入口 |
| `scripts/recall_v2.py` | 关键词检索工具 |
| `scripts/memory_v2.py` | DB 操作库 + CLI stats/cluster/cold |
| `scripts/memory_client.py` | MemoryClient 封装类 |
| `memory_v2.db` | 记忆数据库 |

## DB 表结构

```sql
memory_index    -- 记忆条目
topics          -- 话题
session_topics  -- 会话-话题关联
knowledge_graph -- 知识图谱关系
```

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

## Pitfalls

1. **batch_extractor.py 硬编码路径**：依赖 `memory-v2` 子目录，克隆到其他位置需修改 `sys.path.insert`
2. **state.db 路径**：生产环境为 `~/.hermes/state.db`，测试时注意路径
3. **去重阈值**：Jaccard > 80% 跳过，阈值可调 `memory_v2.py` 中 `_jaccard_similarity` 调用处
4. **会话来源过滤**：只处理 `source IN ('feishu','cli','weixin')` 的会话

## 当前状态 (2026-04-29)

| 指标 | 数值 |
|------|------|
| 记忆条目 | 309 |
| 话题数 | 49 |
| 图谱关系 | 0 |
| 会话关联 | 476 |
| 数据库大小 | 272KB |

| 类型 | 数量 |
|------|------|
| reward | 97 |
| insight | 56 |
| preference | 40 |
| fact | 32 |
| event | 32 |
| constraint | 26 |
| error | 24 |
