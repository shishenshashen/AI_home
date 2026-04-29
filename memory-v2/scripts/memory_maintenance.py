#!/usr/bin/env python3
"""
memory_maintenance.py — 记忆维护脚本（建议每天执行一次）
功能：遗忘衰减 + 冷热迁移 + 聚类 + 统计报告
"""

import sys, os, sqlite3, json
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memory_v2 import stats, cold_migration, cluster_topics, get_conn, now_iso


def decay_forget(days: int = 30, threshold: float = 0.2):
    """遗忘衰减：超过指定天数没有访问的记忆，衰减到阈值以下后删除"""
    conn = get_conn()
    cur = conn.cursor()
    
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    
    # 更新所有记忆的衰减分数
    cur.execute("""
        UPDATE memory_index SET decay_score = decay_score - 0.01 * (
            CAST(julianday('now') - julianday(updated_at) AS INTEGER)
        )
    """)
    
    # 被检索过的记忆增加衰减抵抗
    cur.execute("""
        UPDATE memory_index SET decay_score = decay_score + hit_count * 0.05
        WHERE hit_count > 0
    """)
    
    # 删除衰减阈值以下的低质量记忆
    forgotten = cur.execute(
        "SELECT COUNT(*) FROM memory_index WHERE decay_score < ? AND hit_count = 0 AND importance < 4",
        (threshold,)
    ).fetchone()[0]
    
    cur.execute(
        "DELETE FROM memory_index WHERE decay_score < ? AND hit_count = 0 AND importance < 4",
        (threshold,)
    )
    
    conn.commit()
    conn.close()
    return forgotten


def archive_old_topics(days: int = 90):
    """归档90天以上未活跃的话题"""
    conn = get_conn()
    cur = conn.cursor()
    
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    
    archived = cur.execute("""
        SELECT COUNT(*) FROM topics
        WHERE last_active < ? AND status = 'active'
    """, (cutoff,)).fetchone()[0]
    
    cur.execute("""
        UPDATE topics SET status = 'archived'
        WHERE last_active < ? AND status = 'active'
    """, (cutoff,))
    
    conn.commit()
    conn.close()
    return archived


def generate_report() -> str:
    """生成记忆系统健康报告"""
    s = stats()
    
    conn = get_conn()
    cur = conn.cursor()
    
    # 高重要性记忆
    important = cur.execute(
        "SELECT COUNT(*) FROM memory_index WHERE importance >= 4 AND hit_count = 0"
    ).fetchone()[0]
    
    # 活跃场景
    scenes = cur.execute(
        "SELECT scene_id, COUNT(*) FROM memory_index WHERE scene_id IS NOT NULL GROUP BY scene_id"
    ).fetchall()
    
    # 今日新增
    today = datetime.now().strftime('%Y-%m-%d')
    today_new = cur.execute(
        "SELECT COUNT(*) FROM memory_index WHERE substr(created_at, 1, 10) = ?",
        (today,)
    ).fetchone()[0]
    
    conn.close()
    
    report = f"""📊 记忆系统健康报告 [{today}]
━━━━━━━━━━━━━━━━━━━
📌 总览
  记忆数: {s['memory']}
  话题数: {s['topics']}
  图谱关系: {s['graph']}
  今日新增: {today_new}

🏷️ 场景分布"""
    for sid, cnt in scenes:
        report += f"\n  {sid}: {cnt}条"

    report += f"""

⚡ 健康指标
  高重要性未检索记忆: {important}条
  分类: {json.dumps(s['categories'], ensure_ascii=False)}
"""
    return report


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'decay':
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            n = decay_forget(days)
            print(f"✅ 遗忘清理: 删除 {n} 条低质量记忆")
        elif cmd == 'archive':
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 90
            n = archive_old_topics(days)
            print(f"✅ 归档: {n} 个话题已归档")
        elif cmd == 'cluster':
            n = cluster_topics()
            print(f"✅ 聚类合并: {n} 个话题")
        elif cmd == 'report':
            print(generate_report())
        elif cmd == 'full':
            # 全量维护
            d = decay_forget(30)
            a = archive_old_topics(90)
            c = cluster_topics()
            print(f"✅ 完整维护完成")
            print(f"  遗忘清理: {d} 条 | 归档: {a} 个 | 聚类: {c} 个")
        return
    
    # 默认执行完整维护
    print("🔄 记忆维护...")
    d = decay_forget(30)
    a = archive_old_topics(90)
    c = cluster_topics()
    print(f"  遗忘清理: {d} 条 | 归档: {a} 个 | 聚类: {c} 个")
    print(generate_report())


if __name__ == '__main__':
    main()