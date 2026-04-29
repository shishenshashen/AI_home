# Memory V2 — Hermes Agent 长期记忆系统

从对话历史中自动提取有价值记忆，存入 SQLite，实现跨会话知识积累。

## 一句话原理

```
state.db (476会话, 1.8万条消息)
    │
    ▼ 每小时 cron + 会话结束钩子
memory_v2.db (精选记忆, 无限存储)
```

## 架构

```
┌─────────────────────────┐
│       state.db          │  ← Hermes Agent 原始对话
│  (476会话, 13K消息)      │
└───────────┬─────────────┘
            │
            ├─ batch_extractor.py   ← 批量提取 + 回填 (cron/手动)
            ├─ session_extractor.py ← 会话结束钩子 (自动)
            ├─ hourly_extractor.py  ← cron 专用入口
            └─ recall_v2.py         ← 检索工具
            │
            ▼
┌─────────────────────────┐
│     memory_v2.db        │  ← 精选记忆 (无限)
│  memory_index  (300+条) │  ← 含 256维语义向量
│  topics        (50+个)  │
│  knowledge_graph        │
└─────────────────────────┘
```

## 检索机制（Hybrid Search）

```
query → FTS5 关键词粗筛 50 条
      → 语义向量余弦相似度重排
      → 综合分 = 0.5×语义 + 0.25×重要性 + 0.15×原子化 + 0.1×命中次数
      → top_k 返回
```

### Embedding 模型

- **模型**: `iic/nlp_corom_sentence-embedding_chinese-tiny`（魔搭 ModelScope）
- **维度**: 256维，中英文双语
- **大小**: 33MB（含 tokenizer）
- **下载源**: `modelscope.cn`（HuggingFace 在国内不可达）
- **缓存路径**: `~/.hermes/embedding_model/`

## 记忆分类

| 类型 | 含义 | 颜色 |
|------|------|------|
| `reward` | 完成成果、配置成功 | 🟢 |
| `insight` | 发现教训、定位原因 | 🔍 |
| `error` | 错误/bug/失败 | 🔴 |
| `constraint` | 原则/禁止/必须 | 🔵 |
| `preference` | 用户偏好/习惯 | 🟡 |

## 快速开始

### 安装

```bash
# 克隆仓库（依赖 scripts/ 下的脚本）
git clone https://github.com/shishensbashen/AI_home.git
cd AI_home/memory-v2
```

### 历史会话一次性回填（已完成，跳过）

```bash
# 精简模式：只提取 reward/insight/error/constraint/preference
python3 scripts/batch_extractor.py --mode compact --limit 476
# 约 5-7条/会话，476个会话约 300条记忆
```

### 每小时增量（cron 自动运行，无需手动）

```bash
# cron 自动调用 hourly_extractor.py
python3 scripts/hourly_extractor.py
```

### 手动检索

```bash
# 关键词检索
python3 scripts/recall_v2.py 飞书

# 指定类型
python3 scripts/recall_v2.py github --category error

# 查看统计
python3 scripts/memory_v2.py stats
```

## 脚本说明

| 脚本 | 作用 | 调用方式 |
|------|------|----------|
| `embed.py` | 语义向量生成（256维） | 内部调用 |
| `session_extractor.py` | 核心引擎：会话→记忆 | 内部调用 |
| `batch_extractor.py` | 批量提取 + `--backfill-embeddings` | 手动 |
| `hourly_extractor.py` | cron 专用：增量提取新会话 | cron |
| `recall_v2.py` | 检索：语义+关键词混合排序 | 手动 |
| `memory_v2.py` | DB 操作库 + CLI 工具 | 手动 |

## 数据规模

```
历史会话:  476个会话 → 309条精选记忆
向量存储:  ~3KB/条 × 309 ≈ 0.9MB
Embedding 模型: 33MB（首次下载后缓存）
数据库:   1MB（可持续增长）
```

## cron 配置

| 项目 | 值 |
|------|-----|
| 任务 ID | `acf6cfefbdf6` |
| 执行时间 | 每小时第 5 分钟 |
| 命令 | `python3 scripts/hourly_extractor.py` |
| 输出 | 本地文件，不打扰 |

## 项目状态

- ✅ 历史会话回填完成（2026-04-29）
- ✅ 语义向量回填完成（2026-04-29）
- ✅ 每小时增量 cron 运行中
- ✅ 自动去重（相似度 > 80% 跳过）
- ✅ Hybrid Search（语义 + 关键词）
- 🔧 持续调优提取规则

---

**仓库**: https://github.com/shishensbashen/AI_home  
**子目录**: `memory-v2/`
