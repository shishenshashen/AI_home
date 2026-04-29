#!/usr/bin/env python3
"""
每小时记忆提取 - 从state.db提取新会话记忆到memory_v2.db
跳过已处理的会话，支持增量运行
"""

import sys, os, sqlite3
sys.path.insert(0, '/root/.hermes/skills/memory-v2/scripts')

STATE_DB = '/root/.hermes/state.db'
MEMORY_DB = '/root/.hermes/memory_v2.db'


def get_processed_session_ids():
    """获取已处理的会话ID"""
    conn = sqlite3.connect(MEMORY_DB)
    ids = set()
    # 从 memory_index 的 source_session_id 获取
    for row in conn.execute("SELECT DISTINCT source_session_id FROM memory_index WHERE source_session_id IS NOT NULL AND source_session_id != ''"):
        ids.add(row[0])
    # 从 session_topics 获取
    for row in conn.execute("SELECT DISTINCT session_id FROM session_topics"):
        ids.add(row[0])
    conn.close()
    return ids


def get_pending_sessions(limit=20):
    """获取待处理的有效会话（排除cron自动任务）"""
    conn = sqlite3.connect(STATE_DB)
    cur = conn.cursor()
    
    rows = cur.execute("""
        SELECT id, source, title, message_count
        FROM sessions
        WHERE source IN ('feishu', 'cli', 'weixin', 'telegram', 'tui')
        AND message_count >= 3
        ORDER BY started_at DESC
        LIMIT ?
    """, (limit,)).fetchall()
    
    conn.close()
    return rows


def main():
    processed = get_processed_session_ids()
    pending = get_pending_sessions(20)
    
    new_pending = [(sid, src, title, msgs) for sid, src, title, msgs in pending if sid not in processed]
    
    if not new_pending:
        print(f"✅ 无新会话需要提取 (已处理: {len(processed)}个)")
        return
    
    print(f"📦 待提取: {len(new_pending)}个新会话 (已处理: {len(processed)}个)\n")
    
    # 导入提取器
    sys.path.insert(0, '/root/.hermes/skills/memory-v2/scripts')
    from session_extractor import auto_memorize
    
    total_new = 0
    for sid, src, title, msgs in new_pending:
        t = (title or '无标题')[:50]
        print(f"  📝 {sid[:20]}... [{src}] {t} ({msgs}条消息)")
        try:
            auto_memorize(sid, t)
            total_new += 1
        except Exception as e:
            print(f"    ❌ {e}")
    
    print(f"\n✅ 本轮提取完成: {total_new}个会话")


if __name__ == '__main__':
    main()
