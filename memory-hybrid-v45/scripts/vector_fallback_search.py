#!/usr/bin/env python3
"""
Vector fallback search for memory-hybrid plugin.
Used when Whoosh BM25 returns no results or low-confidence results.
Embeds all memory chunks and performs cosine similarity search.
Ported from OpenClaw 3.7 with configurable paths.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Tuple

import numpy as np
import requests

# Defaults (overridable via args/env)
DEFAULT_HF_HOME = "/Volumes/data/workspace/hf_cache"
DEFAULT_CACHE_DIR = "/Volumes/data/workspace/openclaw-memory/vector_cache"
DEFAULT_CONFIG = os.path.expanduser("~/.openclaw/openclaw.json")
DEFAULT_EMBEDDING_URL = "http://localhost:8090/v1/embeddings"
DEFAULT_EMBEDDING_MODEL = "bge-small-zh"


def resolve_workspace(config_path: str, agent: str = "main") -> Path:
    cfg = json.loads(Path(config_path).read_text())
    d = cfg.get("agents", {}).get("defaults", {}).get(
        "workspace", str(Path.home() / ".openclaw" / "workspace")
    )
    for a in cfg.get("agents", {}).get("list", []):
        if str(a.get("id", "")).lower() == agent.lower():
            return Path(a.get("workspace", d))
    return Path(d)


def collect_chunks(ws: Path) -> List[Dict]:
    """Collect and chunk markdown files from workspace."""
    files = []
    for pat in ["MEMORY.md", "memory/**/*.md"]:
        files.extend(ws.glob(pat))

    chunks = []
    for p in sorted(set(files)):
        if not p.exists() or p.is_dir():
            continue
        txt = p.read_text(errors="ignore")
        paras = [x.strip() for x in re.split(r"\n\s*\n+", txt) if x.strip()]
        for para in paras:
            step = 280
            size = 360
            if len(para) <= size:
                segs = [para]
            else:
                segs = [para[i : i + size].strip() for i in range(0, len(para), step)]
            for s in segs:
                if len(s) < 80:
                    continue
                chunks.append({"path": str(p.relative_to(ws)), "text": s})

    uniq = []
    seen = set()
    for c in chunks:
        h = hashlib.md5(c["text"].encode("utf-8", "ignore")).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        uniq.append(c)
    return uniq


def get_embeddings_batch(texts: List[str], service_url: str, model: str) -> np.ndarray:
    """Get embeddings for a batch of texts via the embedding service."""
    results = []
    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            response = requests.post(
                service_url,
                json={"input": batch, "model": model},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            for item in data["data"]:
                results.append(item["embedding"])
        except Exception as e:
            print(f"[error] Embedding batch {i} failed: {e}", file=sys.stderr)
            # Fill with zeros for failed batch
            for _ in batch:
                results.append([0.0] * 512)
    return np.array(results, dtype=np.float32)


def load_or_build(agent: str, config_path: str, cache_dir: str,
                  embedding_url: str, embedding_model: str) -> Tuple[np.ndarray, List[Dict]]:
    """Load cached embeddings or build new ones."""
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    ws = resolve_workspace(config_path, agent)
    chunks = collect_chunks(ws)

    if not chunks:
        return np.array([]), []

    key = hashlib.md5(
        (agent + "|" + embedding_model + "|" + str(len(chunks))).encode()
    ).hexdigest()[:16]
    f_emb = cache_path / f"{agent}-{key}.npy"
    f_meta = cache_path / f"{agent}-{key}.json"

    if f_emb.exists() and f_meta.exists():
        print(f"[perf] loading cached embeddings: {f_emb.name}", file=sys.stderr)
        emb = np.load(f_emb)
        meta = json.loads(f_meta.read_text())
        return emb, meta

    print(f"[perf] building embeddings for {len(chunks)} chunks...", file=sys.stderr)
    texts = [c["text"] for c in chunks]
    emb = get_embeddings_batch(texts, embedding_url, embedding_model)

    np.save(f_emb, emb)
    f_meta.write_text(json.dumps(chunks, ensure_ascii=False))
    return emb, chunks


def main():
    total_start = time.time()

    ap = argparse.ArgumentParser(description="Vector fallback memory search")
    ap.add_argument("--agent", default="main")
    ap.add_argument("--query", required=True)
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    ap.add_argument("--embedding-url", default=DEFAULT_EMBEDDING_URL)
    ap.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    args = ap.parse_args()

    emb, meta = load_or_build(
        args.agent, args.config, args.cache_dir,
        args.embedding_url, args.embedding_model,
    )

    if len(emb) == 0:
        print(json.dumps({"results": [], "provider": "vector-fallback", "model": args.embedding_model}))
        return

    # Embed query via embedding service
    try:
        response = requests.post(
            args.embedding_url,
            json={"input": args.query, "model": args.embedding_model},
            timeout=5.0,
        )
        response.raise_for_status()
        q = np.array(response.json()["data"][0]["embedding"], dtype=np.float32)
    except Exception as e:
        print(f"[error] Query embedding failed: {e}", file=sys.stderr)
        print(json.dumps({"results": [], "provider": "vector-fallback", "model": args.embedding_model}))
        return

    # Cosine similarity
    sims = np.dot(emb, q)
    idx = np.argsort(-sims)[: args.limit]

    out = []
    for i in idx:
        c = meta[int(i)]
        out.append({
            "path": c["path"],
            "startLine": 1,
            "endLine": 1,
            "score": float(sims[int(i)]),
            "baseScore": float(sims[int(i)]),
            "snippet": c["text"][:280].replace("\n", " "),
            "source": "vector-fallback",
        })

    total_end = time.time()
    print(f"[perf] total: {total_end - total_start:.3f}s", file=sys.stderr)
    print(json.dumps({"results": out, "provider": "vector-fallback", "model": args.embedding_model},
                      ensure_ascii=False))


if __name__ == "__main__":
    main()
