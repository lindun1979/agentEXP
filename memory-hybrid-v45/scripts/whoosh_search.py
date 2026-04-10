#!/usr/bin/env python3
"""
Whoosh BM25 full-text search for OpenClaw memory-hybrid plugin.
Supports Chinese tokenization and score adjustments.
Ported from OpenClaw 3.7 memory-hybrid to work with 4.5.
"""

import argparse
import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple

from whoosh import index
from whoosh.analysis import Token, Tokenizer
from whoosh.fields import ID, TEXT, Schema
from whoosh.qparser import OrGroup, QueryParser


class ChineseTokenizer(Tokenizer):
    """Regex-based CJK + English tokenizer for Whoosh."""

    def __call__(
        self,
        value,
        positions=False,
        chars=False,
        keeporiginal=False,
        removestops=True,
        start_pos=0,
        start_char=0,
        mode="",
        **kwargs,
    ):
        text = (value or "").strip()
        if not text:
            return
        tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_.:-]+", text)
        t = Token()
        cursor = 0
        for pos, token in enumerate(tokens):
            idx = text.find(token, cursor)
            if idx < 0:
                idx = cursor
            t.text = token.lower()
            t.pos = start_pos + pos
            t.startchar = start_char + idx
            t.endchar = t.startchar + len(token)
            cursor = idx + len(token)
            yield t


@dataclass
class FileDoc:
    path: str
    content: str


def load_config(config_path: str) -> Dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_workspace(cfg: Dict, agent_id: str) -> str:
    defaults_ws = cfg.get("agents", {}).get("defaults", {}).get(
        "workspace", os.path.expanduser("~/.openclaw/workspace")
    )
    agents = cfg.get("agents", {}).get("list", [])
    want = (agent_id or "main").lower()
    for a in agents:
        aid = str(a.get("id", "")).lower()
        if aid == want:
            return a.get("workspace", defaults_ws)
    return defaults_ws


def collect_files(workspace: str, extra_paths: List[Dict] = None) -> List[FileDoc]:
    """Collect markdown files from workspace MEMORY.md + memory/**/*.md + extra paths."""
    import glob as globmod

    docs: List[FileDoc] = []
    seen = set()
    candidates = []

    root_memory = os.path.join(workspace, "MEMORY.md")
    if os.path.isfile(root_memory):
        candidates.append(root_memory)
    candidates.extend(globmod.glob(os.path.join(workspace, "memory", "**", "*.md"), recursive=True))

    # Extra paths (from qmd.paths or similar config)
    for p in (extra_paths or []):
        rel_path = p.get("path", ".")
        pattern = p.get("pattern", "**/*.md")
        base = rel_path if os.path.isabs(rel_path) else os.path.join(workspace, rel_path)
        if os.path.isfile(base):
            candidates.append(base)
        elif os.path.isdir(base):
            if "**" in pattern or "/" in pattern:
                candidates.extend(globmod.glob(os.path.join(base, pattern), recursive=True))
            else:
                for fn in os.listdir(base):
                    if fnmatch.fnmatch(fn, pattern):
                        candidates.append(os.path.join(base, fn))

    for fp in candidates:
        if not os.path.isfile(fp) or not fp.endswith(".md"):
            continue
        norm = os.path.normpath(fp)
        if norm in seen:
            continue
        seen.add(norm)
        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            if not content.strip():
                continue
            path_rel = os.path.relpath(fp, workspace)
            docs.append(FileDoc(path=path_rel, content=content[:120000]))
        except Exception:
            continue
    return docs


def build_index(config_path: str, index_dir: str, agent_id: str) -> Dict:
    """Build or rebuild Whoosh index from workspace files."""
    cfg = load_config(config_path)
    workspace = resolve_workspace(cfg, agent_id)
    extra_paths = cfg.get("memory", {}).get("qmd", {}).get("paths", [])
    docs = collect_files(workspace, extra_paths)

    if os.path.exists(index_dir):
        import shutil
        shutil.rmtree(index_dir)
    os.makedirs(index_dir, exist_ok=True)

    schema = Schema(
        path=ID(stored=True, unique=True),
        content=TEXT(stored=True, analyzer=ChineseTokenizer()),
    )
    ix = index.create_in(index_dir, schema)
    writer = ix.writer()
    for d in docs:
        writer.add_document(path=d.path, content=d.content)
    writer.commit()
    return {"indexed": len(docs), "indexDir": index_dir, "agent": agent_id, "workspace": workspace}


def snippet_and_lines(content: str, query: str, max_len: int = 320) -> Tuple[str, int, int]:
    """Extract a snippet around the first match of query tokens."""
    token = None
    for t in re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_.:-]+", query or ""):
        if len(t) >= 2:
            token = t
            break
    if not token:
        token = (query or "").strip()

    idx = content.lower().find(token.lower()) if token else -1
    if idx < 0:
        idx = 0

    start = max(0, idx - max_len // 3)
    end = min(len(content), start + max_len)
    snippet = content[start:end].replace("\n", " ").strip()

    before = content[:idx]
    start_line = before.count("\n") + 1
    line_span = max(1, snippet.count("\n") + 3)
    end_line = start_line + line_span
    return snippet, start_line, end_line


def adjusted_score(path_val: str, content_val: str, base_score: float, q: str) -> float:
    """Apply score adjustments based on file path and content relevance."""
    p = (path_val or "").lower()
    text = (content_val or "").lower()
    qq = (q or "").lower()
    score = float(base_score)

    # Source weighting: structured memory topics prioritized, noise logs penalized
    if "memory/topics/" in p or p.startswith("memory/topics/"):
        score *= 1.38
    if "raw-log" in p or "99-raw" in p or "memory-flush" in p:
        score *= 0.68
    if re.search(r"memory/\d{4}-\d{2}-\d{2}-\d{4}\.md$", p):
        score *= 0.78

    # High-value documents boosted
    if p == "memory.md":
        score *= 1.22
    if p == "state.md":
        score *= 1.18

    # Exact phrase match bonus
    if qq and qq in text:
        score += 3.2

    # Technical phrase bonus
    phrases = [
        "plugins.slots.memory",
        "memory.qmd.paths",
        "openclaw.json",
        "searchmode",
        "includedefaultmemory",
        "vsearch",
        "memory-core",
        "qmd",
    ]
    bonus = 0.0
    for ph in phrases:
        if ph in qq and ph in text:
            bonus += 0.9
    return score + min(bonus, 2.7)


def search_index(index_dir: str, query: str, limit: int = 8) -> Dict:
    """Search Whoosh index with BM25 + score adjustments."""
    if not index.exists_in(index_dir):
        return {"results": [], "provider": "whoosh", "model": "whoosh", "error": "index_missing"}

    ix = index.open_dir(index_dir)
    out = []
    with ix.searcher() as s:
        qp = QueryParser("content", ix.schema, group=OrGroup.factory(0.9))
        q = qp.parse(query or "")
        rs = s.search(q, limit=max(limit * 3, 12))
        for r in rs:
            content = r.get("content", "")
            snippet, start_line, end_line = snippet_and_lines(content, query)
            base = float(r.score)
            adj = adjusted_score(r["path"], content, base, query)
            out.append(
                {
                    "path": r["path"],
                    "startLine": start_line,
                    "endLine": end_line,
                    "score": adj,
                    "baseScore": base,
                    "snippet": snippet,
                    "source": "whoosh",
                }
            )
    out.sort(key=lambda x: x.get("score", 0.0), reverse=True)
    return {"results": out[:limit], "provider": "whoosh", "model": "whoosh"}


def stats(index_dir: str) -> Dict:
    if not index.exists_in(index_dir):
        return {"exists": False, "indexed": 0}
    ix = index.open_dir(index_dir)
    with ix.searcher() as s:
        return {"exists": True, "indexed": int(s.doc_count())}


def main():
    parser = argparse.ArgumentParser(description="Whoosh BM25 memory search")
    parser.add_argument("action", choices=["build", "search", "stats"])
    parser.add_argument("--config", default=os.path.expanduser("~/.openclaw/openclaw.json"))
    parser.add_argument("--index", dest="index_dir",
                        default=os.path.expanduser("/Volumes/data/workspace/openclaw-memory/whoosh_index"))
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--agent", default="main")
    args = parser.parse_args()

    if args.action == "build":
        result = build_index(args.config, args.index_dir, args.agent)
    elif args.action == "search":
        result = search_index(args.index_dir, args.query, args.limit)
    else:
        result = stats(args.index_dir)

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
