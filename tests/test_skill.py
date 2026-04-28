#!/usr/bin/env python3
"""Memory V2 Skill 测试"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memory_v2 import get_conn, stats, remember, recall, create_topic, relate, get_connections

def test_basic():
    # 统计
    s = stats()
    assert s["memory"] >= 0
    print(f"✅ stats: {s}")

    # 记忆
    r = remember("测试记忆内容", category="test", importance=3)
    assert r["status"] == "stored"
    print(f"✅ remember: {r}")

    # 检索
    results = recall("测试")
    assert len(results) >= 1
    print(f"✅ recall: {len(results)} 条")

    # 话题
    topic_id = create_topic("test-session", "测试话题", ["测试", "记忆"])
    print(f"✅ create_topic: {topic_id}")

    # 关联
    relate("memory", r["id"], "topic", topic_id)
    conns = get_connections("topic", topic_id)
    assert len(conns) >= 1
    print(f"✅ relate: {len(conns)} 条关联")

    print("\n✅ 所有测试通过")

if __name__ == "__main__":
    test_basic()