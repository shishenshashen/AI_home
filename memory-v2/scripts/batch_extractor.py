#!/usr/bin/env python3
"""
全量记忆提取 — 从state.db提取所有会话到memory_v2.db
- 首次运行: mode='compact' 历史精简
- 每小时运行: mode='full' 新会话全量
"""

import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STATE_DB = os.path.expanduser('~/.hermes/state.db')
MEMORY_DB = os.path.expanduser('~/.hermes/memory_v2.db')


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


def _backfill_embeddings():
    """为无 embedding 的历史记忆批量生成向量"""
    from memory_v2 import _get_embed_model, _embed, get_conn
    import json

    # 确保 schema 有 embedding 列
    conn = get_conn()
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT id, content FROM memory_index
        WHERE embedding IS NULL
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()

    total = len(rows)
    if total == 0:
        print("✅ 所有记忆已有 embedding")
        return

    print(f"📊 需要回填: {total} 条记忆")
    updated = 0
    errors = 0

    for i, (mem_id, content) in enumerate(rows):
        try:
            vec = _embed(content)
            if vec:
                conn2 = get_conn()
                conn2.execute("UPDATE memory_index SET embedding=? WHERE id=?",
                             (json.dumps(vec), mem_id))
                conn2.commit()
                conn2.close()
                updated += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1

        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{total} (已更新:{updated} 失败:{errors})")

    print(f"\n✅ 回填完成: {updated}/{total} 条 (失败:{errors})")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', '-m', default='full', choices=['full', 'compact'])
    parser.add_argument('--limit', '-l', type=int, default=20)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--backfill-embeddings', action='store_true',
                        help='为历史记忆批量生成语义向量')
    args = parser.parse_args()

    from session_extractor import auto_memorize

    # 回填历史 embedding
    if args.backfill_embeddings:
        _backfill_embeddings()
        return

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
