#!/usr/bin/env python3
"""
会话结束钩子 — 自动从会话中提取记忆写入 memory_v2.db
用法: python3 session_extractor.py <session_id> [session_title]
自动从 state.db 读取会话消息，提取原子记忆，存入 memory_v2.db
"""

import sys, os, sqlite3, json, re, uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memory_v2 import remember, create_topic, relate, _jaccard_similarity, get_conn, now_iso

STATE_DB = os.path.expanduser('~/.hermes/state.db')


def extract_keywords(text: str) -> list:
    """从文本中提取有意义的关键词"""
    stop = {'的','了','是','在','我','你','他','她','它','们','这','那',
            '不','也','和','就','都','而','有','没','把','被','让','给',
            '为','对','从','就','要','会','能','一','上','下','来','去',
            '到','说','看','想','做','用','把','跟','让','请','可以'}
    words = re.findall(r'[\u4e00-\u9fff\w]{2,}', text.lower())
    return [w for w in set(words) if w not in stop and len(w) >= 2][:10]


def extract_atomic(content: str, date: str = None) -> str:
    """将对话内容原子化：去除代词和相对时间"""
    date = date or datetime.now().strftime('%Y-%m-%d')
    result = content
    
    # 去除代词
    pronouns = [('他', ''), ('她', ''), ('它', ''), ('他们', ''),
                ('我', ''), ('你', ''), ('我', ''), ('我们', ''),
                ('这个', ''), ('那个', ''), ('这', ''), ('那', ''),
                ('这里', ''), ('那里', ''), ('刚才', ''), ('上次', '')]
    for p, r in pronouns:
        result = result.replace(p, r)
    
    # 相对时间转绝对时间
    time_map = {
        '今天': date,
        '现在': date,
        '最近': date,
        '刚刚': date,
    }
    for rel, ab in time_map.items():
        result = result.replace(rel, ab)
    
    # 去除多余空格
    result = re.sub(r'\s+', ' ', result).strip()
    return result


def extract_session_messages(session_id: str) -> list:
    """从state.db读取会话消息"""
    if not os.path.exists(STATE_DB):
        print(f"⚠️ state.db不存在，跳过")
        return []
    conn = sqlite3.connect(STATE_DB)
    rows = conn.execute("""
        SELECT role, content FROM messages 
        WHERE session_id = ? AND role IN ('user', 'assistant')
        ORDER BY timestamp ASC
    """, (session_id,)).fetchall()
    conn.close()
    return [(r[0], r[1]) for r in rows if r[1]]


# ── 记忆类型识别 ────────────────────────────────────────────────
# ── 历史会话：精简提取（仅奖励+洞察+教训+原则+偏好）───────────
def extract_historical(messages: list) -> list:
    """历史会话只提取高价值记忆，避免重复'搞定了'噪音"""
    result = []
    seen_lines = set()  # 去除重复首行
    
    for role, content in messages:
        if role != 'assistant' or len(content) < 20:
            continue
        
        first_line = content.strip().split('\n')[0].strip()[:120]
        raw = content
        
        # 跳过无意义的确认语
        noise = ['搞定了！✅', '搞定', '测试完成', '抱歉', '不好意思', 
                 '好的', '明白', '没问题', '稍等', '让我看看']
        if any(first_line.startswith(n) or first_line == n for n in noise):
            continue
        if first_line in seen_lines:
            continue
        
        combined = first_line + raw
        
        # 🔍 INSIGHT: 发现/定位/理解
        if any(k in combined for k in [
            '找到问题', '定位到', '原因', '原来如此', '本质是',
            '搞清楚', '关键在于', '核心是', 'root cause', 'root_cause'
        ]):
            seen_lines.add(first_line)
            result.append({'type': 'insight', 'content': first_line})
            continue
        
        # 🔴 ERROR: 真实错误/失败
        if any(k in combined for k in [
            'Traceback', 'Error:', 'Exception', '报错', '失败:',
            'status: fail', 'status: error'
        ]):
            seen_lines.add(first_line)
            result.append({'type': 'error', 'content': first_line})
            continue
        
        # 🟢 REWARD: 重要成果（去重复）
        if any(k in combined for k in [
            '✅', '写入成功', '配置完成', '创建完成', '修复完成',
            '生成完成', '执行成功', '成功推送', '搞定'
        ]) and len(first_line) > 15:
            seen_lines.add(first_line)
            result.append({'type': 'reward', 'content': first_line})
            continue
        
        # 🔵 CONSTRAINT: 原则/禁止
        if any(k in combined for k in ['禁止', '红线', '必须', '原则']):
            seen_lines.add(first_line)
            result.append({'type': 'constraint', 'content': first_line})
            continue
        
        # 🟡 PREFERENCE: 偏好
        if any(k in combined for k in ['偏好', '喜欢', '讨厌', '希望', '风格', '要求']):
            seen_lines.add(first_line)
            result.append({'type': 'preference', 'content': first_line})
    
    return result


# ── 新会话：全量提取 ──────────────────────────────────────────────
def extract_full(messages: list) -> list:
    """新会话全量提取所有有价值内容"""
    return extract_historical(messages)  # 目前共用逻辑，之后可扩展


# ── 统一入口 ────────────────────────────────────────────────────
def extract_memories(messages: list, mode: str = 'full') -> list:
    if mode == 'compact':
        return extract_historical(messages)
    return extract_full(messages)


def summarize_session(messages: list) -> dict:
    """从会话消息中提取摘要、关键词、关键事实"""
    if not messages:
        return {'summary': '', 'keywords': [], 'facts': []}
    
    all_text = '\n'.join([m[1] for m in messages if len(m[1]) > 10])
    
    keywords = extract_keywords(all_text)
    
    # 提取关键事实（包含技术名词、配置、路径的命令输出）
    facts = []
    for role, content in messages:
        if role == 'assistant' and any(k in content for k in [
            '✅', '已', '完成', '成功', '修复', '创建', '配置', 
            '写入', '更新', '新增', '迁移', '实现', '解决'
        ]):
            if len(content) > 20 and len(content) < 300:
                facts.append(content.strip().split('\n')[0][:200])
    
    # 生成摘要
    summary = f"会话包含{len(messages)}条消息，关键词: {','.join(keywords[:5])}"
    
    return {
        'summary': summary,
        'keywords': keywords,
        'facts': facts[:5]  # 最多5条关键事实
    }


def auto_memorize(session_id: str = None, session_title: str = None, mode: str = 'full'):
    """
    主函数：从会话中自动提取记忆写入 memory_v2.db
    
    mode='full'    : 新会话全量提取
    mode='compact' : 历史会话精简提取（reward/insight/error/constraint/preference）
    """
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    
    print(f"🔍 会话结束钩子启动: {session_id or 'current'} [{mode}]")
    
    # 读取会话消息
    messages = extract_session_messages(session_id) if session_id else []
    
    session_info = {'keywords': [], 'summary': ''}
    saved_count = 0
    
    if messages:
        print(f"  读取到 {len(messages)} 条消息")
        session_info = summarize_session(messages)
        
        # 提取记忆
        memories = extract_memories(messages, mode=mode)
        
        if memories:
            # 创建话题
            topic_name = session_title or session_info['summary'][:50] or f"会话 {session_id[:12]}"
            topic_id = create_topic(
                session_id=session_id or 'unknown',
                title=topic_name[:80],
                keywords=session_info['keywords'][:5],
                summary=session_info['summary'][:200]
            )
            print(f"  话题: {topic_name[:50]} (id={topic_id})")
            
            # 入库
            for m in memories:
                atomic = extract_atomic(m['content'], today)
                if len(atomic) < 5:
                    continue
                result = remember(
                    content=atomic[:300],
                    category=m['type'],
                    importance=3,
                    tags=session_info['keywords'][:3] if session_info['keywords'] else [],
                    source_session=session_id
                )
                if result.get('status') == 'stored':
                    relate('memory', result.get('id', ''), 'topic', topic_id, 'belongs_to')
                    print(f"    ✅ [{m['type']:>10}] {atomic[:60]}")
                    saved_count += 1
        else:
            print("  无有价值记忆，跳过保存")
    else:
        print("  无会话消息")
    
    print(f"✅ 会话结束钩子完成 ({saved_count}条记忆)")
    return saved_count


def main():
    session_id = sys.argv[1] if len(sys.argv) > 1 else None
    session_title = sys.argv[2] if len(sys.argv) > 2 else None
    auto_memorize(session_id, session_title)


if __name__ == '__main__':
    main()
