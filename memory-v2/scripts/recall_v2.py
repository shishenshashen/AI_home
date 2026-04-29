#!/usr/bin/env python3
"""
recall_v2 — 增强检索：支持场景隔离 + 时序过滤 + 原子记忆优先
用法: python3 recall_v2.py <query> [--scene <scene_id>] [--period <period>] [--limit 10]
"""

import sys, os, sqlite3, json, re
from datetime import datetime, timedelta

DB = os.path.expanduser('~/.hermes/memory_v2.db')


def jaccard(a, b):
    s_a = set(re.findall(r'\w+', a.lower()))
    s_b = set(re.findall(r'\w+', b.lower()))
    if not s_a or not s_b:
        return 0.0
    return len(s_a & s_b) / len(s_a | s_b)


def atomic_score(content: str) -> float:
    """评分：越接近原子记忆（无代词/相对时间）分数越高"""
    score = 1.0
    bad = ['他', '她', '它', '我', '我们', '这个', '那个', '这里', '那里', 
           '刚才', '上次', '之前', '后来', '后来', '最近']
    for b in bad:
        if b in content:
            score -= 0.15
    if len(content) > 200:
        score -= 0.1  # 简短更可能是原子
    return max(0.3, score)


def recall(query, scene_id=None, period=None, temporal_layer=None, limit=10):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    conditions = []
    params = []
    
    # 支持多个关键词 OR 查询
    keywords = [k for k in re.findall(r'[\u4e00-\u9fff\w]{2,}', query) if len(k) >= 2]
    if keywords:
        like_clauses = ["content LIKE ?" for _ in keywords]
        conditions.append(f"({(' OR '.join(like_clauses))})")
        params.extend([f"%{k}%" for k in keywords])
    
    if scene_id:
        conditions.append("scene_id = ?")
        params.append(scene_id)
    
    if period:
        conditions.append("period = ?")
        params.append(period)
    
    if temporal_layer:
        conditions.append("temporal_layer = ?")
        params.append(temporal_layer)
    
    where = " AND ".join(conditions) if conditions else "1=1"
    
    rows = cur.execute(f"""
        SELECT id, content, category, memory_type, tags, importance, 
               hit_count, scene_id, temporal_layer, period, confidence, decay_score, created_at
        FROM memory_index
        WHERE {where}
        ORDER BY importance DESC, hit_count DESC, created_at DESC
        LIMIT 100
    """, params).fetchall()
    
    conn.close()
    
    if not rows:
        return []
    
    # 语义+原子评分混合排序
    results = []
    for r in rows:
        row_dict = dict(r)
        sim = jaccard(query, row_dict['content'])
        atom = atomic_score(row_dict['content'])
        # 综合分 = 0.4*相似度 + 0.3*重要性 + 0.2*命中次数(归一化) + 0.1*原子化程度
        hit_norm = min(row_dict['hit_count'] / 10.0, 1.0)
        row_dict['score'] = round(0.4*sim + 0.3*(row_dict['importance']/5.0) + 0.2*hit_norm + 0.1*atom, 3)
        row_dict['sim'] = round(sim, 2)
        row_dict['atomic'] = round(atom, 2)
        results.append(row_dict)
    
    # 按综合分排序
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:limit]


def list_scenes():
    """列出所有可用场景"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    
    rows = cur.execute("""
        SELECT scene_id, COUNT(*) as cnt 
        FROM memory_index 
        WHERE scene_id IS NOT NULL 
        GROUP BY scene_id
        ORDER BY cnt DESC
    """).fetchall()
    
    conn.close()
    
    print("🏷️ 可用场景:")
    for r in rows:
        print(f"    {r[0]}: {r[1]}条记忆")
    
    # 可用时间层
    print("\n📅 可用时间:")
    conn = sqlite3.connect(DB)
    rows2 = conn.execute("""
        SELECT temporal_layer, period, COUNT(*) 
        FROM memory_index 
        WHERE period IS NOT NULL 
        GROUP BY temporal_layer, period
        ORDER BY period DESC
    """).fetchall()
    conn.close()
    for r in rows2:
        print(f"    [{r[0]}] {r[1]}: {r[2]}条")


def main():
    if len(sys.argv) < 2:
        print("用法: recall_v2.py <query> [--scene <scene_id>] [--period <period>] [--limit N]")
        print("      recall_v2.py --scenes  # 列出场景")
        list_scenes()
        sys.exit(1)
    
    if sys.argv[1] == '--scenes':
        list_scenes()
        sys.exit(0)
    
    query = sys.argv[1]
    scene_id = None
    period = None
    temporal_layer = None
    limit = 10
    
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == '--scene' and i+1 < len(args):
            scene_id = args[i+1]; i += 2
        elif a == '--period' and i+1 < len(args):
            period = args[i+1]; i += 2
        elif a == '--layer' and i+1 < len(args):
            temporal_layer = args[i+1]; i += 2
        elif a == '--limit' and i+1 < len(args):
            limit = int(args[i+1]); i += 2
        else:
            i += 1
    
    results = recall(query, scene_id, period, temporal_layer, limit)
    
    print(f"🔍 检索 '{query}'" + 
          (f" [场景:{scene_id}]" if scene_id else "") +
          (f" [时间:{period}]" if period else "") +
          f" → {len(results)} 条结果\n")
    
    for r in results:
        tags = json.loads(r['tags']) if r['tags'] else []
        print(f"  【{r['category']}】score={r['score']} sim={r['sim']} atomic={r['atomic']} imp={r['importance']} hit={r['hit_count']}")
        print(f"    {r['content'][:100]}")
        if r['scene_id']:
            print(f"    🏷️ {r['scene_id']} | 📅 {r['period'] or 'today'}")
        print()


if __name__ == '__main__':
    main()
