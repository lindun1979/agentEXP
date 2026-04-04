#!/usr/bin/env python3
import argparse
import json
import os
import re
from pathlib import Path

from whoosh import index
from whoosh.analysis import Token, Tokenizer
from whoosh.fields import ID, TEXT, Schema
from whoosh.qparser import QueryParser


class ZhTokenizer(Tokenizer):
    def __call__(self, value, **kwargs):
        text = (value or "").strip()
        if not text:
            return
        tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_.:-]+", text)
        t = Token()
        for i, token in enumerate(tokens):
            t.text = token.lower()
            t.pos = i
            yield t


def workspace_root():
    return Path(os.environ.get("OPENCLAW_WORKSPACE", Path.cwd()))


def memory_files(root: Path):
    files = []
    p = root / "MEMORY.md"
    if p.exists():
        files.append(p)
    files.extend((root / "memory").glob("**/*.md"))
    return [f for f in files if f.exists() and f.is_file()]


def build(index_dir: Path):
    root = workspace_root()
    files = memory_files(root)

    if index_dir.exists():
        import shutil

        shutil.rmtree(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)

    schema = Schema(path=ID(stored=True, unique=True), content=TEXT(stored=True, analyzer=ZhTokenizer()))
    ix = index.create_in(str(index_dir), schema)
    w = ix.writer()
    for fp in files:
        txt = fp.read_text(encoding="utf-8", errors="ignore")[:120000]
        w.add_document(path=str(fp.relative_to(root)), content=txt)
    w.commit()

    return {"indexed": len(files), "indexDir": str(index_dir)}


def search(index_dir: Path, query: str, limit: int):
    if not index.exists_in(str(index_dir)):
        return {"results": [], "provider": "whoosh", "error": "index_missing"}

    ix = index.open_dir(str(index_dir))
    out = []
    with ix.searcher() as s:
        qp = QueryParser("content", schema=ix.schema)
        q = qp.parse(query or "")
        rs = s.search(q, limit=limit)
        for r in rs:
            text = r.get("content", "")
            snip = text[:280].replace("\n", " ")
            out.append(
                {
                    "path": r["path"],
                    "startLine": 1,
                    "endLine": 1,
                    "score": float(r.score),
                    "snippet": snip,
                    "source": "whoosh",
                }
            )
    return {"results": out, "provider": "whoosh", "model": "whoosh"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["build", "search"])
    ap.add_argument("--index", default=str(Path.home() / ".openclaw" / "memory" / "whoosh_index" / "sample"))
    ap.add_argument("--query", default="")
    ap.add_argument("--limit", type=int, default=8)
    args = ap.parse_args()

    idx = Path(args.index)
    if args.action == "build":
        print(json.dumps(build(idx), ensure_ascii=False))
    else:
        print(json.dumps(search(idx, args.query, args.limit), ensure_ascii=False))


if __name__ == "__main__":
    main()
