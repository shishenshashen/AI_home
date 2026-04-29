#!/usr/bin/env python3
"""
embed.py — 语义向量模块（依赖魔搭 ModelScope）
模型: iic/nlp_corom_sentence-embedding_chinese-tiny (256维)
"""

import os
import sys
import json
import numpy as np

_MODEL_DIR = os.path.expanduser("~/.hermes/embedding_model/iic/nlp_corom_sentence-embedding_chinese-tiny")
_MODEL = None
_TOKENIZER = None


def _load_model():
    """延迟加载模型，全局缓存"""
    global _MODEL, _TOKENIZER
    if _MODEL is None:
        from modelscope import AutoModel, AutoTokenizer
        _TOKENIZER = AutoTokenizer.from_pretrained(_MODEL_DIR, trust_remote_code=True)
        _MODEL = AutoModel.from_pretrained(_MODEL_DIR, trust_remote_code=True)
        _MODEL.eval()
    return _MODEL, _TOKENIZER


def encode(texts) -> list:
    """
    生成语义向量。支持单条(str)或批量(list)。
    返回 list of list[float]，每个向量 256 维。
    """
    model, tokenizer = _load_model()
    if isinstance(texts, str):
        texts = [texts]
    inputs = tokenizer(texts, padding=True, truncation=True, max_length=256, return_tensors="pt")
    outputs = model(**inputs)
    # mean pooling
    vecs = outputs.last_hidden_state.mean(dim=1).detach().numpy()
    return [v.tolist() for v in vecs]


def cosine_sim(a: list, b: list) -> float:
    """余弦相似度，两个 256 维向量"""
    va = np.array(a)
    vb = np.array(b)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def encode_and_serialize(texts):
    """生成向量并序列化为 JSON 字符串，存入 SQLite"""
    vecs = encode(texts)
    return [json.dumps(v, separators=(',', ':')) for v in vecs]


if __name__ == "__main__":
    # CLI: python3 embed.py <text> [text2] ...
    texts = sys.argv[1:] or ["测试文本"]
    vecs = encode(texts)
    for t, v in zip(texts, vecs):
        print(f"Text: {t[:50]}")
        print(f"  dims={len(v)}, sample={v[:5]}")
