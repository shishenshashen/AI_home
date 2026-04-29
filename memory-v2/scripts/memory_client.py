#!/usr/bin/env python3
"""MemoryClient — 供 AI agent 在会话中直接调用"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memory_v2 import *

class MemoryClient:
    def __init__(self):
        self._topic_keywords = []

    def remember(self, content, category="fact", importance=3, tags=None):
        r = _remember(content, category, importance, tags)
        if r.get("status") == "stored":
            return {"ok": True, "id": r["id"]}
        if r.get("status") == "skipped":
            return {"ok": True, "note": f"已存在（相似度{r.get('similarity', 0.8)}）"}
        return {"ok": False, "error": str(r)}

    def recall(self, query, category=None, limit=5):
        return _recall(query, category, limit)

    def on_session_start(self, message):
        stop = {"的","了","是","在","我","你","他","她","它","们","这","那",
                "不","也","和","就","都","而","有","没","把","被","让","给","为","对","从"}
        words = re.findall(r'[\u4e00-\u9fff\w]{2,}', message.lower())
        self._topic_keywords = [w for w in words[:8] if w not in stop]
        return self._topic_keywords

    def get_current_topic(self):
        return ", ".join(self._topic_keywords) if self._topic_keywords else "未识别"

    def hot(self, limit=5):
        return hot_topics(limit)

    def connect(self, st, sid, tt, tid, rel="references"):
        relate(st, sid, tt, tid, rel)

    def related_to(self, st, sid):
        return get_connections(st, sid)

    def auto_cluster(self):
        n = cluster_topics()
        return {"ok": True, "merged": n} if n else {"ok": True, "note": "无合并"}

    def stats(self):
        return stats()