# Memory V2

> Hermes Agent 增强记忆系统 — 无限存储、自动聚类、知识图谱、冷热分层

## 功能特性

| 特性 | 原Memory | Memory V2 |
|------|---------|-----------|
| 存储上限 | 2.2K 字符 | 无限 |
| 话题聚类 | ❌ | ✅ 自动 |
| 跨会话关联 | ❌ | ✅ 知识图谱 |
| 冷热分层 | ❌ | ✅ 自动迁移 |
| 去重 | ❌ | ✅ 相似度检测 |

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/xiarichang/memory-v2.git
cd memory-v2

# 2. 初始化
python3 scripts/memory_v2.py stats

# 3. 使用
python3 scripts/memory_v2.py recall "关键词"
python3 scripts/memory_v2.py stats
```

## Python API

```python
from memory_client import MemoryClient

mc = MemoryClient()

# 记忆
mc.remember("知识内容", category="workflow", importance=4)

# 检索
results = mc.recall("关键词")

# 热点话题
for t in mc.hot():
    print(t['name'], t['hot_score'])
```

## 架构

```
memory_index  ← 记忆条目（分类/标签/引用计数）
topics        ← 话题节点（关键词/活跃度/摘要）
knowledge_graph ← 跨类型关联关系
session_topics ← 会话-话题多对多
```

## 维护

```bash
# 聚类
python3 scripts/memory_v2.py cluster

# 冷热迁移
python3 scripts/memory_v2.py cold 7 90 ~/.hermes/memory_archive
```

## License

MIT