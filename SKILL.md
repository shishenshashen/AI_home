# Memory V2 Skill

## 概述

增强型记忆系统，解决 Hermes Agent 原有 memory 的局限：

- ❌ 固定 2.2K/1.3K 字符槽位 → ✅ 无限存储
- ❌ 无话题聚类 → ✅ 自动话题聚合
- ❌ 无跨会话关联 → ✅ 知识图谱
- ❌ 无冷热分层 → ✅ 自动归档
- ❌ 无去重 → ✅ 相似度去重

基于 SQLite 的多层存储架构：

```
L1 热 (内存)      : 当前会话上下文
L2 温 (SQLite)    : 7天内全文 + 话题索引
L3 冷 (SQLite)    : 7-90天摘要化 + 话题树
L4 归档 (GZIP)    : 90天+仅摘要
```

核心表：
- `memory_index` — 记忆条目（分类、标签、引用计数）
- `topics` — 话题节点（关键词、活跃度、摘要）
- `knowledge_graph` — 跨类型关联关系
- `session_topics` — 会话-话题多对多

---

## 安装

```bash
# 1. 初始化数据库（自动）
python3 ~/.hermes/skills/memory-v2/scripts/memory_v2.py stats

# 2. 迁移旧记忆（可选）
python3 ~/.hermes/skills/memory-v2/scripts/memory_v2.py migrate
```

---

## 用法

### 基础操作

```python
from memory_client import MemoryClient
mc = MemoryClient()

# 记忆（自动去重）
mc.remember("大哥要求所有飞书操作必须用lark-cli", 
            category="workflow", importance=5, tags=["飞书"])

# 检索
results = mc.recall("lark-cli", category="workflow", limit=5)

# 话题管理（会话结束后调用）
topic_id = mc.create_topic_from_session(
    session_id=session_id,
    title="飞书操作规范",
    keywords=["飞书", "lark-cli", "表格"],
    summary="所有飞书操作必须用lark-cli替代REST API"
)

# 建立关联
mc.connect("memory", mem_id, "topic", topic_id, "belongs_to")

# 热点话题
hot = mc.hot(limit=5)

# 统计
s = mc.stats()
print(f"记忆: {s['memory_count']}, 话题: {s['topic_count']}")
```

### 维护命令

```bash
# 查看统计
python3 scripts/memory_v2.py stats

# 执行话题聚类（合并相似话题）
python3 scripts/memory_v2.py cluster

# 冷热迁移（7天热→90天冷→归档）
python3 scripts/memory_v2.py cold --days-hot 7 --days-cold 90 --archive ~/.hermes/memory_archive
```

---

## 集成到 Hermes Agent

### 1. 初始化

在 `run_agent.py` 或 agent 初始化时：

```python
from memory_client import MemoryClient
memory_v2 = MemoryClient()
agent.memory_v2 = memory_v2  # 挂载到 agent 实例
```

### 2. 会话生命周期钩子

```python
# 会话开始
def on_session_start(self, message):
    keywords = self.memory_v2.on_session_start(message)
    # 可选：预加载相关记忆
    related = self.memory_v2.recall(" ".join(keywords[:3]))

# 会话结束
def on_session_end(self, session_id, messages):
    # 提取会话主题
    summary = self._summarize(messages)
    keywords = self._extract_keywords(summary)
    topic_id = create_topic_from_session(session_id, summary[:100], keywords, summary)
    
    # 关联本会话产生的记忆
    # ...
    
    # 执行聚类（异步）
    self.memory_v2.auto_cluster()
```

### 3. 替换 `memory` 工具

修改 `tools/memory_tool.py`：

```python
def memory_tool(action, target="memory", content=None, old_text=None):
    # 双写：旧文件 + 新数据库
    old_result = old_memory_tool(action, target, content, old_text)
    
    # V2 写入
    if action == "add" and content:
        agent.memory_v2.remember(content, category=target, importance=3)
    # ...
    
    return old_result
```

后期可完全切换：

```python
# Phase 2: 只写 V2
if config.memory_v2_enabled:
    result = agent.memory_v2.remember(...)
else:
    result = old_memory_tool(...)
```

---

## 配置

在 `config.yaml` 中添加：

```yaml
memory_v2:
  enabled: true
  db_path: "~/.hermes/memory_v2.db"
  auto_cluster: true        # 会话结束后自动聚类
  cold_migration: true      # 启用冷热迁移
  days_hot: 7
  days_cold: 90
  archive_dir: "~/.hermes/memory_archive"
```

---

## API 参考

### MemoryClient

| 方法 | 说明 |
|------|------|
| `remember(content, category, importance, tags)` | 记忆一条信息 |
| `recall(query, category, limit)` | 关键词检索 |
| `on_session_start(message)` | 会话开始，提取话题关键词 |
| `get_current_topic()` | 获取当前会话话题 |
| `hot(limit)` | 热话题排行 |
| `connect(source_type, source_id, target_type, target_id, relation)` | 建立关联 |
| `related_to(source_type, source_id)` | 查询关联 |
| `auto_cluster()` | 执行聚类 |
| `stats()` | 统计信息 |

### 命令行脚本

| 命令 | 说明 |
|------|------|
| `stats` | 查看统计 |
| `cluster` | 合并相似话题 |
| `cold` | 冷热迁移 |
| `migrate` | 从旧记忆文件迁移 |

---

## 注意事项

1. **双写期间**：旧 `MEMORY.md`/`USER.md` 仍作为系统 prompt 注入源
2. **去重阈值**：当前 Jaccard 相似度 >0.8 视为重复，可调整
3. **话题聚类**：关键词重叠度 ≥50% 自动合并，阈值可调
4. **冷热迁移**：建议每天凌晨 cron 执行
5. **归档文件**：定期备份或清理 `~/.hermes/memory_archive/`

---

## 未来增强

- [ ] Embedding 向量化语义检索
- [ ] 自动摘要生成（LLM）
- [ ] 话题层级树（parent_id 递归）
- [ ] 记忆重要性动态调整（基于 hit_count）
- [ ] 会话内容自动标签化
- [ ] 磁盘空间监控 + 自动清理