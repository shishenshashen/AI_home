#!/usr/bin/env python3
"""
Memory V2 — 增强记忆系统 for Hermes Agent

取代旧的固定槽位 memory / user_profile。

详情见 SKILL.md
"""

import sqlite3
import json
import os
import sys
import uuid
import re
from datetime import datetime, timedelta
from collections import Counter, defaultdict

DB_PATH = os.path.expanduser("~/.hermes/memory_v2.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso():
    return datetime.now().isoformat()


# ─── 基础 CRUD ─────────────────────────────────────

def remember(content: str, category: str = "fact", importance: int = 3,
             tags: list = None, source_session: str = None) -> dict:
    conn = get_conn()
    cur = conn.cursor()

    # 去重检查
    existing = cur.execute(
        "SELECT id, content FROM memory_index WHERE category = ? AND hit_count > 0",
        (category,)
    ).fetchall()
    for row in existing:
        sim = _jaccard_similarity(content[:200], row["content"][:200])
        if sim > 0.8:
            cur.execute("UPDATE memory_index SET hit_count = hit_count + 1 WHERE id = ?",
                       (row["id"],))
            conn.commit()
            conn.close()
            return {"status": "skipped", "reason": "similar_content",
                    "existing_id": row["id"], "similarity": round(sim, 2)}

    mem_id = str(uuid.uuid4())[:12]
    now = now_iso()
    tags_json = json.dumps(tags or ["通用"])

    cur.execute("""
        INSERT INTO memory_index (id, content, category, tags, source_session_id,
                                  created_at, updated_at, importance, hit_count)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (mem_id, content[:500], category, tags_json, source_session, now, now, importance))

    conn.commit()
    conn.close()
    return {"status": "stored", "id": mem_id}


def recall(query: str, category: str = None, limit: int = 10) -> list:
    conn = get_conn()
    cur = conn.cursor()

    sql = """
        SELECT id, content, category, tags, importance, hit_count, created_at
        FROM memory_index WHERE content LIKE ?
    """
    params = [f"%{query}%"]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " ORDER BY importance DESC, hit_count DESC LIMIT ?"
    params.append(limit)

    rows = cur.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── 话题系统 ─────────────────────────────────────

def create_topic(session_id: str, title: str, keywords: list,
                 summary: str = "") -> str:
    conn = get_conn()
    cur = conn.cursor()

    existing = cur.execute(
        "SELECT id, keywords FROM topics WHERE parent_id IS NULL"
    ).fetchall()
    for row in existing:
        kw = set(json.loads(row["keywords"] or "[]"))
        overlap = len(set(keywords) & kw)
        if overlap >= max(2, len(keywords) // 2):
            _link_session_topic(conn, session_id, row["id"])
            conn.close()
            return row["id"]

    topic_id = str(uuid.uuid4())[:12]
    now = now_iso()
    cur.execute("""
        INSERT INTO topics (id, name, keywords, session_ids, created_at,
                           last_active, hot_score, summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (topic_id, title[:100], json.dumps(keywords),
          json.dumps([session_id]), now, now, 1.0, summary[:500]))
    _link_session_topic(conn, session_id, topic_id)
    conn.commit()
    conn.close()
    return topic_id


def _link_session_topic(conn, session_id: str, topic_id: str):
    row = conn.execute("SELECT session_ids FROM topics WHERE id = ?",
                       (topic_id,)).fetchone()
    if row:
        ids = set(json.loads(row["session_ids"] or "[]"))
        ids.add(session_id)
        conn.execute("UPDATE topics SET session_ids = ?, last_active = ? WHERE id = ?",
                    (json.dumps(list(ids)), now_iso(), topic_id))

    conn.execute("""
        INSERT OR REPLACE INTO session_topics (session_id, topic_id, relevance)
        VALUES (?, ?, COALESCE((SELECT relevance + 0.1 FROM session_topics
                                WHERE session_id = ? AND topic_id = ?), 1.0))
    """, (session_id, topic_id, session_id, topic_id))


def hot_topics(limit: int = 5) -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT id, name, keywords, hot_score, last_active, session_ids
        FROM topics ORDER BY hot_score DESC, last_active DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── 知识图谱 ─────────────────────────────────────

def relate(source_type: str, source_id: str,
           target_type: str, target_id: str,
           relation: str = "references", weight: float = 1.0):
    conn = get_conn()
    cur = conn.cursor()
    edge_id = str(uuid.uuid4())[:12]
    cur.execute("""
        INSERT OR REPLACE INTO knowledge_graph
        (id, source_type, source_id, target_type, target_id, relation, weight, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (edge_id, source_type, source_id, target_type, target_id,
          relation, weight, now_iso()))
    conn.commit()
    conn.close()


def get_connections(source_type: str, source_id: str) -> list:
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM knowledge_graph
        WHERE (source_type = ? AND source_id = ?)
           OR (target_type = ? AND target_id = ?)
        ORDER BY weight DESC
    """, (source_type, source_id, source_type, source_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── 聚类 ─────────────────────────────────────

def cluster_topics(threshold: float = 0.7):
    conn = get_conn()
    cur = conn.cursor()
    topics = cur.execute("SELECT id, name, keywords FROM topics").fetchall()
    merged = 0

    for i, ta in enumerate(topics):
        kw_a = set(json.loads(ta["keywords"] or "[]"))
        for tb in topics[i + 1:]:
            kw_b = set(json.loads(tb["keywords"] or "[]"))
            union = kw_a | kw_b
            if not union:
                continue
            sim = len(kw_a & kw_b) / len(union)
            if sim >= threshold:
                ids_a = set(json.loads(ta["session_ids"] or "[]"))
                ids_b = set(json.loads(tb["session_ids"] or "[]"))
                merged_ids = ids_a | ids_b
                merged_kw = list(kw_a | kw_b)
                cur.execute("""
                    UPDATE topics SET keywords=?, session_ids=?, parent_id=?,
                                      hot_score = hot_score + ?
                    WHERE id = ?
                """, (json.dumps(merged_kw), json.dumps(list(merged_ids)),
                      tb["id"], 0.5, ta["id"]))
                merged += 1

    conn.commit()
    conn.close()
    return merged


# ─── 冷热迁移 ─────────────────────────────────────

def cold_migration(days_hot: int = 7, days_cold: int = 90,
                   archive_dir: str = None):
    now = datetime.now()
    hot_cutoff = now - timedelta(days=days_hot)
    cold_cutoff = now - timedelta(days=days_cold)

    conn = get_conn()
    cur = conn.cursor()

    cold = cur.execute("""
        SELECT id, name, session_ids FROM topics
        WHERE last_active < ? AND last_active >= ?
    """, (hot_cutoff.isoformat(), cold_cutoff.isoformat())).fetchall()

    for topic in cold:
        cur.execute("UPDATE topics SET keywords = '[]' WHERE id = ?", (topic["id"],))

    if archive_dir:
        archive_dir = os.path.expanduser(archive_dir)
        os.makedirs(archive_dir, exist_ok=True)
        frozen = cur.execute("""
            SELECT id, name, keywords, summary, session_ids, created_at, last_active
            FROM topics WHERE last_active < ?
        """, (cold_cutoff.isoformat(),)).fetchall()

        if frozen:
            path = os.path.join(archive_dir, f"topics_{now.strftime('%Y%m%d')}.json")
            with open(path, 'w') as f:
                json.dump([dict(r) for r in frozen], f, ensure_ascii=False, default=str)
            ids = [r["id"] for r in frozen]
            cur.execute(f"DELETE FROM topics WHERE id IN ({','.join('?' * len(ids))})", ids)

    conn.commit()
    conn.close()


# ─── 统计 ─────────────────────────────────────

def stats() -> dict:
    conn = get_conn()
    cur = conn.cursor()
    s = {
        "memory": cur.execute("SELECT COUNT(*) FROM memory_index").fetchone()[0],
        "topics": cur.execute("SELECT COUNT(*) FROM topics").fetchone()[0],
        "graph": cur.execute("SELECT COUNT(*) FROM knowledge_graph").fetchone()[0],
        "links": cur.execute("SELECT COUNT(*) FROM session_topics").fetchone()[0],
        "categories": {},
    }
    for c, n in cur.execute("SELECT category, COUNT(*) FROM memory_index GROUP BY category"):
        s["categories"][c] = n
    conn.close()
    return s


# ─── 工具 ─────────────────────────────────────

def _jaccard_similarity(a: str, b: str) -> float:
    set_a = set(re.findall(r'\w+', a.lower()))
    set_b = set(re.findall(r'\w+', b.lower()))
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


# ─── CLI ─────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <command> [args]")
        print("  stats         查看统计")
        print("  cluster       执行聚类")
        print("  cold          冷热迁移")
        print("  recall <q>    检索")
        print("  remember <c>  记忆")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "stats":
        s = stats()
        print("📊 Memory V2 统计")
        print(f"  记忆条目: {s['memory']}")
        print(f"  话题: {s['topics']}")
        print(f"  图谱关系: {s['graph']}")
        print(f"  会话关联: {s['links']}")
        for cat, n in s["categories"].items():
            print(f"    {cat}: {n} 条")

    elif cmd == "cluster":
        n = cluster_topics()
        print(f"✅ 合并 {n} 个话题" if n else "ℹ️ 无需合并")

    elif cmd == "cold":
        days_hot = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        days_cold = int(sys.argv[3]) if len(sys.argv) > 3 else 90
        archive = sys.argv[4] if len(sys.argv) > 4 else "~/.hermes/memory_archive"
        cold_migration(days_hot, days_cold, archive)
        print(f"✅ 冷热迁移完成")

    elif cmd == "recall":
        q = sys.argv[2] if len(sys.argv) > 2 else ""
        for r in recall(q):
            print(f"  [{r['category']}] (重要:{r['importance']}) {r['content'][:80]}")

    elif cmd == "remember":
        c = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
        r = remember(c, "fact", 3)
        print(json.dumps(r, ensure_ascii=False))