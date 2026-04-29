#!/usr/bin/env python3
"""
全量记忆提取 — 从state.db提取所有会话到memory_v2.db
- 首次运行: mode='compact' 历史精简
- 每小时运行: mode='full' 新会话全量
"""

import sys, os, sqlite3
sys.path.insert(0, '/root/.hermes/skills/memory-v2/scripts')

STATE_DB = os.path.expanduser('/root/.hermes/state.db')
MEMORY_DB = os.path.expanduser('/root/.hermes/memory_v2.db')


def get_processed():
    """已处理的会话ID集合"""
    conn = sqlite3.connect(MEMORY_DB)
    ids = set()
    for row in conn.execute("SELECT DISTINCT session_id FROM session_topics WHERE session_id IS NOT NULL AND session_id != ''"):
        ids.add(row[0])
    for row in conn.execute("SELECT DISTINCT source_session_id FROM memory_index WHERE source_session_id IS NOT NULL AND source_session_id != ''"):
        ids.add(row[0])
    conn.close()
    return ids


def get_pending_sessions(mode='full', limit=20):
    """获取待处理会话"""
    conn = sqlite3.connect(STATE_DB)
    where = "started_at < datetime('now', '-1 days')" if mode == 'compact' else "1=1"
    rows = conn.execute(f"""
        SELECT id, source, title, message_count
        FROM sessions 
        WHERE source IN ('feishu','cli','weixin') 
          AND message_count >= 3
          AND {where}
        ORDER BY message_count DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', '-m', default='full', choices=['full', 'compact'])
    parser.add_argument('--limit', '-l', type=int, default=20)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    from session_extractor import auto_memorize

    processed = get_processed()
    pending = get_pending_sessions(mode=args.mode, limit=args.limit)
    new_pending = [r for r in pending if r[0] not in processed]

    if not new_pending:
        print(f"✅ 无新会话需要提取 (已处理: {len(processed)}个)")
        return

    print(f"📦 待提取: {len(new_pending)}个会话 (mode={args.mode})")
    print(f"   已处理: {len(processed)}个\n")

    total = 0
    for sid, src, title, msgs in new_pending:
        t = (title or '无标题')[:50]
        print(f"  📝 {sid[:22]}... [{src}] {msgs}条")
        if not args.dry_run:
            n = auto_memorize(sid, title, mode=args.mode)
            total += n
        else:
            total += 1
            print(f"    (dry-run) 跳过保存")

    print(f"\n✅ 完成: {total}条记忆 / {len(new_pending)}个会话")


if __name__ == '__main__':
    main()
