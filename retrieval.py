"""Transparent BM25 plus cosine retrieval with RRF fusion."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from collections import Counter

DIMENSION = 512
BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
EN_STOP = {"a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "did", "do", "does", "for", "from", "how", "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "should", "the", "this", "to", "was", "what", "when", "where", "which", "who", "why", "will", "with", "would", "you", "your"}
ZH_STOP = {"什么", "怎么", "如何", "哪些", "哪个", "多少", "为什么", "为何", "是否", "请问", "一下", "介绍", "概括", "总结", "关于", "有关"}
ZH_STOP_CHARS = set("我你他她它的是了吗呢啊吧呀和与及在于从把被将这那其可会能有请问什么怎哪为么下" )
_embedding_failed_until = 0.0
_embedding_status_cache = (0.0, None)


def terms(text: str) -> list[str]:
    text = text.lower()
    found = [word for word in re.findall(r"[a-z0-9_]+", text) if word not in EN_STOP]
    han = "".join(re.findall(r"[\u3400-\u9fff]", text))
    # Keep adjacent bigrams for word-level matching and unigrams for short questions.
    found.extend(token for token in (han[i:i + 2] for i in range(len(han) - 1)) if token not in ZH_STOP and not any(char in ZH_STOP_CHARS for char in token))
    if len(han) == 1:
        if han not in ZH_STOP_CHARS:
            found.append(han)
    return found


def _hash_vector(text: str) -> dict:
    counts = Counter(terms(text))
    vector = [0.0] * DIMENSION
    for token, count in counts.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "little")
        vector[value % DIMENSION] += (1.0 if value >> 63 else -1.0) * (1.0 + math.log(count))
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return {"signature": "feature-hash-512-v1", "values": [value / norm for value in vector]}


def embed_text(text: str, is_query: bool = False) -> dict:
    """Try the configured OpenAI-compatible embedding server; use a labeled lexical fallback."""
    global _embedding_failed_until
    endpoint = os.getenv("KBQA_EMBEDDING_URL", "http://127.0.0.1:8082/v1/embeddings").rstrip("/")
    model = os.getenv("KBQA_EMBEDDING_MODEL", "bge-small-zh")
    if os.getenv("KBQA_EMBEDDINGS_ENABLED", "1") != "0" and time.monotonic() >= _embedding_failed_until:
        body = {"model": model, "input": BGE_QUERY_PREFIX + text if is_query else text}
        headers = {"Content-Type": "application/json"}
        if os.getenv("OPENAI_API_KEY"):
            headers["Authorization"] = "Bearer " + os.environ["OPENAI_API_KEY"]
        try:
            request = urllib.request.Request(endpoint, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(request, timeout=float(os.getenv("KBQA_EMBEDDING_TIMEOUT", "2"))) as response:
                data = json.loads(response.read())
            vector = data["data"][0]["embedding"]
            if vector and all(isinstance(value, (int, float)) for value in vector):
                return {"signature": "bge:" + model, "values": [float(value) for value in vector]}
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            _embedding_failed_until = time.monotonic() + 10
    return _hash_vector(text)


def _unpack_vector(value) -> dict | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    # Migration path for the first prototype, which stored a bare numeric list.
    if isinstance(value, list):
        return {"signature": "feature-hash-512-v1", "values": value}
    return value if isinstance(value, dict) and isinstance(value.get("values"), list) else None


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def bm25_rank(question: str, rows: list[dict]) -> list[tuple[float, dict]]:
    query_counts = Counter(terms(question))
    if not query_counts or not rows:
        return []
    tokenized = [terms(row["content"]) for row in rows]
    doc_freq = Counter(token for doc in tokenized for token in set(doc))
    avg_len = sum(map(len, tokenized)) / max(1, len(tokenized))
    k1, b = 1.5, 0.75
    ranked = []
    for row, tokens in zip(rows, tokenized):
        counts = Counter(tokens)
        score = 0.0
        for token in query_counts:
            tf = counts[token]
            if not tf:
                continue
            idf = math.log(1 + (len(rows) - doc_freq[token] + 0.5) / (doc_freq[token] + 0.5))
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(tokens) / max(1, avg_len)))
        if score >= 0.15:
            ranked.append((score, row))
    return sorted(ranked, key=lambda item: item[0], reverse=True)


def embedding_status() -> dict:
    global _embedding_status_cache
    if os.getenv("KBQA_EMBEDDINGS_ENABLED", "1") == "0":
        return {"available": False, "signature": "feature-hash-512-v1", "mode": "local-lexical"}
    now = time.monotonic()
    if _embedding_status_cache[1] and now - _embedding_status_cache[0] < 10:
        return _embedding_status_cache[1]
    vector = embed_text("embedding health probe")
    status = {"available": vector["signature"].startswith("bge:"), "signature": vector["signature"], "mode": "pretrained-bge" if vector["signature"].startswith("bge:") else "local-lexical"}
    _embedding_status_cache = (time.monotonic(), status)
    return status


def hybrid_search(question: str, rows: list[dict], limit: int = 5, retrieval_mode: str = "hybrid", query_embedding: dict | None = None) -> list[dict]:
    if not rows:
        return []
    lexical = bm25_rank(question, rows)
    query_vector = query_embedding or embed_text(question, is_query=True)
    dense = []
    for row in rows:
        candidate = dict(row)
        candidate_vector = _unpack_vector(row.get("vector"))
        similarity = 0.0
        if candidate_vector and candidate_vector.get("signature") == query_vector["signature"]:
            similarity = _cosine(query_vector["values"], candidate_vector["values"])
        candidate["cosine"] = round(max(0.0, similarity), 6)
        # The feature-hash fallback is a lexical sketch, not semantic embeddings.
        # Only let it support a result already seen lexically; this prevents random
        # hash collisions from presenting unrelated text as evidence.
        lexical_support = any(row["chunk_id"] == candidate["chunk_id"] for _, row in lexical)
        threshold = 0.55 if query_vector["signature"].startswith("bge:") else 0.15
        if similarity >= threshold and (query_vector["signature"].startswith("bge:") or lexical_support):
            dense.append((similarity, candidate))
    dense.sort(key=lambda item: item[0], reverse=True)
    bm25_map = {row["chunk_id"]: score for score, row in lexical}
    vector_map = {row["chunk_id"]: score for score, row in dense}
    for row in rows:
        row["bm25"] = round(bm25_map.get(row["chunk_id"], 0.0), 6)
    lex_rank = {row["chunk_id"]: rank for rank, (_, row) in enumerate(lexical, 1)}
    vec_rank = {row["chunk_id"]: rank for rank, (_, row) in enumerate(dense, 1)}
    if retrieval_mode == "bm25":
        order = [row for _, row in lexical[:limit]]
    elif retrieval_mode == "vector":
        order = [row for _, row in dense[:limit]]
    else:
        fused = {}
        row_by_id = {row["chunk_id"]: row for row in rows}
        for chunk_id in set(lex_rank) | set(vec_rank):
            fused[chunk_id] = (1 / (60 + lex_rank[chunk_id]) if chunk_id in lex_rank else 0) + (1 / (60 + vec_rank[chunk_id]) if chunk_id in vec_rank else 0)
        order = [row_by_id[key] for key in sorted(fused, key=fused.get, reverse=True)[:limit]]
    for row in order:
        row["bm25"] = round(bm25_map.get(row["chunk_id"], 0.0), 6)
        row["cosine"] = round(vector_map.get(row["chunk_id"], 0.0), 6)
        row["score"] = round((row.get("bm25", 0.0) / (row.get("bm25", 0.0) + 1.0)) if retrieval_mode == "bm25" else row.get("cosine", 0.0) if retrieval_mode == "vector" else ((1 / (60 + lex_rank[row["chunk_id"]])) if row["chunk_id"] in lex_rank else 0) + ((1 / (60 + vec_rank[row["chunk_id"]])) if row["chunk_id"] in vec_rank else 0), 6)
        row["snippet"] = row["content"][:650]
        row.pop("vector", None)
    return order
