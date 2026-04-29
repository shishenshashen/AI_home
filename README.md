# Memory V2 — Hermes Agent 长期记忆系统

从 Hermes Agent 的对话历史中自动提取有价值记忆，存入 SQLite 数据库，实现长期积累。

## 核心设计

```
state.db (原始对话)  →  session_extractor  →  memory_v2.db (精选记忆)
     476会话/13K消息         ↓                       309条记忆
                    提取引擎 + 去重                  272KB
                           ↓
                    每小时增量cron
```

## 记忆分类

| 类型 | 说明 | 典型关键词 |
|------|------|-----------|
| reward | 完成成果 | ✅ / 搞定 / 成功 / 配置完成 |
| insight | 发现/教训 | 找到问题 / 原因 / 关键 / 本质 |
| error | 错误/bug | Traceback / 报错 / 失败 |
| constraint | 原则/禁止 | 禁止 / 红线 / 必须 |
| preference | 用户偏好 | 偏好 / 喜欢 / 讨厌 / 希望 |

## 快速开始

### 安装
```bash
git clone https://github.com/shishenshashen/memory-v2.git
cd memory-v2
```

### 提取历史会话
```bash
# 精简模式：只提取 reward + insight + error（推荐，历史一次性）
python3 scripts/session_extractor.py <session_id> --mode compact

# 批量提取所有历史会话
python3 scripts/batch_extractor.py --mode compact --limit 476
```

### 增量提取（新会话每小时自动）
```bash
python3 scripts/batch_extractor.py --mode full --limit 10
```

## 脚本说明

| 脚本 | 作用 |
|------|------|
| `session_extractor.py` | 核心引擎：读取会话 → 提取记忆 → 写入DB |
| `batch_extractor.py` | 批量提取：配合cron自动运行 |
| `memory_v2.py` | DB操作库：remember/recall/relate |
| `recall_v2.py` | 检索工具：关键词+场景+时序查询 |
| `memory_maintenance.py` | 维护工具：衰减/聚类/统计 |

## 两种提取模式

**compact 模式**（历史一次性）:
- 只提取 `reward` + `insight` + `error` + `constraint` + `preference`
- 跳过确认语、重复语、闲聊噪音
- 去重：完全相同首行的只保留一条
- 结果：约 7条/会话

**full 模式**（每小时增量）:
- 同 compact，增加 `fact` + `event`
- 适合新会话全量积累

## 数据规模

- 476个历史会话 → 309条精选记忆
- 每小时增量：预计新增 5-10条/天
- DB大小：272KB（可持续增长）

## 项目状态

✅ 历史全量回填完成  
✅ 每小时增量cron运行中  
🔧 持续观察 & 调优

## License

MIT
