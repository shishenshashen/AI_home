---
name: memory-v2
description: 从state.db提取有价值对话记忆到memory_v2.db，实现长期记忆积累
triggers:
  - 每小时cron自动提取新会话
  - 历史会话一次性精简回填
  - 新对话自动记录
---

# Memory V2 — 记忆提取系统

## 概述

从 Hermes Agent 的 state.db 中提取有价值对话记忆，存入 memory_v2.db。实现**长期记忆积累**，避免每次重复相同错误。

## 核心原则

1. **只记高价值**：reward + insight + error + constraint + preference
2. **不记闲聊**：确认语、重复语、礼貌废话全过滤
3. **历史精简**：476个历史会话一次性精简提取，之后增量

## 架构

```
state.db (476会话, 13K消息)
    │
    ├─ session_extractor.py   ← 核心引擎
    ├─ batch_extractor.py     ← 批量提取脚本
    └─ memory_v2.py          ← DB操作库
              │
              ▼
memory_v2.db (272KB, 309条)
    ├─ memory_index   (309条)
    ├─ session_topics (44条)
    └─ topics (49条)
```

## 两种提取模式

### mode='full' (新会话，每小时cron)
全量提取：reward / insight / error / constraint / preference

### mode='compact' (历史会话，一次性)
只提取：
- **reward**：✅完成/成功推送/配置完成/创建完成
- **insight**：找到问题/原因/关键/本质/搞清楚
- **error**：Traceback/报错/失败/异常
- **constraint**：禁止/红线/必须/原则
- **preference**：偏好/喜欢/讨厌/希望

## 关键文件

| 文件 | 作用 |
|------|------|
| `scripts/session_extractor.py` | 核心引擎，auto_memorize() |
| `scripts/batch_extractor.py` | 批量提取，支持--mode/--limit |
| `scripts/memory_v2.py` | memory_v2.db 操作库 |
| `memory_v2.db` | 精选记忆存储 |

## 用法

```bash
# 测试单会话提取
python3 session_extractor.py <session_id> [标题] --mode compact

# 批量提取历史会话
python3 batch_extractor.py --mode compact --limit 476

# 增量提取新会话
python3 batch_extractor.py --mode full --limit 10
```

## cron 配置

- **memory-v2增量提取** (job_id: acf6cfefbdf6)
- 每小时第5分钟执行 (`5 * * * *`)
- deliver: local

## 当前状态 (2026-04-29)

- **memory_v2.db**: 309条记忆, 49个话题, 272KB
- state.db: 476有效会话 → 历史精简完成，增量每小时提取

| 类型 | 数量 | 说明 |
|------|------|------|
| reward | 97 | 完成成果 |
| insight | 56 | 发现/教训 |
| preference | 40 | 偏好/习惯 |
| fact | 32 | 客观事实 |
| event | 32 | 事件记录 |
| constraint | 26 | 原则/禁止 |
| error | 24 | 错误/bug |

## 提取结果类型

| 类型 | 颜色 | 含义 |
|------|------|------|
| reward | 🟢 | 成功完成的成果 |
| insight | 🔍 | 发现的规律/原因/教训 |
| error | 🔴 | 错误/bug/失败 |
| constraint | 🔵 | 原则/禁止/必须 |
| preference | 🟡 | 用户偏好 |
