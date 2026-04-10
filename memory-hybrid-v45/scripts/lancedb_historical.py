#!/usr/bin/env python3
"""
LanceDB historical solutions/decisions search for OpenClaw memory-hybrid plugin.
Provides semantic search over long-term memory (solutions + decisions).
Ported from OpenClaw 3.7 with configurable paths for 4.5.
"""

import os
import sys
import json
import argparse
import time
import logging
from typing import Dict, List, Any, Optional

import requests
import numpy as np

try:
    import lancedb
    import pyarrow as pa
except ImportError as e:
    print(f"Import error: {e}", file=sys.stderr)
    print("Please install dependencies: pip install lancedb pyarrow", file=sys.stderr)
    sys.exit(1)

# Defaults (overridable via args/env)
DEFAULT_DB_PATH = "/Volumes/data/workspace/openclaw-memory/lancedb"
DEFAULT_EMBEDDING_URL = "http://localhost:8090/v1/embeddings"
DEFAULT_EMBEDDING_MODEL = "bge-small-zh"
DEFAULT_EMBEDDING_DIM = 512
TABLE_NAME = "historical_memory_v2"
SIMILARITY_THRESHOLD = 0.1
MAX_RESULTS = 3

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_embedding(text: str, service_url: str = DEFAULT_EMBEDDING_URL,
                  model: str = DEFAULT_EMBEDDING_MODEL) -> Optional[np.ndarray]:
    try:
        response = requests.post(
            service_url,
            json={"input": text, "model": model},
            timeout=2.0,
        )
        response.raise_for_status()
        data = response.json()
        if "data" in data and len(data["data"]) > 0:
            return np.array(data["data"][0]["embedding"], dtype=np.float32)
        else:
            logger.error(f"Embedding service returned no data: {data}")
            return None
    except Exception as e:
        logger.error(f"Failed to get embedding: {e}")
        return None


def connect_db(db_path: str = DEFAULT_DB_PATH):
    os.makedirs(db_path, exist_ok=True)
    return lancedb.connect(db_path)


def table_exists(db, table_name: str) -> bool:
    try:
        tables_obj = db.list_tables()
        if hasattr(tables_obj, "tables"):
            return table_name in tables_obj.tables
        tables_list = list(tables_obj) if hasattr(tables_obj, "__iter__") else []
        return table_name in tables_list
    except Exception as e:
        logger.debug(f"Error checking table existence: {e}")
        return False


def ensure_table_schema(db, dim: int = DEFAULT_EMBEDDING_DIM):
    try:
        if table_exists(db, TABLE_NAME):
            return db.open_table(TABLE_NAME)
        else:
            schema = pa.schema([
                pa.field("id", pa.string()),
                pa.field("type", pa.string()),
                pa.field("title", pa.string()),
                pa.field("content", pa.string()),
                pa.field("context", pa.string()),
                pa.field("references", pa.string()),
                pa.field("timestamp", pa.float64()),
                pa.field("embedding", pa.list_(pa.float32(), dim)),
            ])
            table = db.create_table(TABLE_NAME, schema=schema)
            logger.info(f"Created empty table '{TABLE_NAME}'")
            return table
    except Exception as e:
        logger.error(f"Failed to ensure table schema: {e}")
        try:
            return db.open_table(TABLE_NAME)
        except Exception:
            raise


def search_similar(table, query_embedding: np.ndarray, agent: str = "main",
                   max_results: int = MAX_RESULTS):
    try:
        AGENT_PERMISSIONS = {
            "opcoder": ["ops", "shared"],
            "main": ["work", "shared"],
        }
        allowed_categories = AGENT_PERMISSIONS.get(agent.lower(), ["shared"])

        results = table.search(query_embedding).limit(max_results * 3).to_list()
        logger.debug(f"Raw search returned {len(results)} results")

        filtered = []
        for r in results:
            distance = r.get("_distance", 1.0)
            similarity = 1.0 - distance

            if similarity < SIMILARITY_THRESHOLD:
                continue

            category = r.get("category", "ops")
            agent_scope = r.get("agent_scope", ["opcoder"])

            if category not in allowed_categories:
                continue

            if agent.lower() not in [a.lower() for a in agent_scope]:
                continue

            r["similarity"] = similarity
            filtered.append(r)

            if len(filtered) >= max_results:
                break

        return filtered
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []


def format_result(record: Dict[str, Any]) -> Dict[str, Any]:
    rec_id = record.get("id", "")
    rec_type = record.get("type", "unknown")
    title = record.get("title", "")
    content = record.get("content", "")
    context = record.get("context", "")
    references = record.get("references", "")
    timestamp = record.get("timestamp", 0)
    similarity = record.get("similarity", 0.0)

    snippet_parts = []
    if rec_type == "solution":
        snippet_parts.append("solution")
    elif rec_type == "decision":
        snippet_parts.append("decision")
    snippet_parts.append(title)
    snippet = " | ".join(snippet_parts)
    if content:
        content_preview = content[:120] + ("..." if len(content) > 120 else "")
        snippet += f" | {content_preview}"

    return {
        "path": f"lancedb://{rec_id}",
        "snippet": snippet,
        "content": content,
        "metadata": {
            "type": rec_type,
            "title": title,
            "context": context,
            "references": references,
            "timestamp": timestamp,
            "similarity": similarity,
        },
    }


def main():
    parser = argparse.ArgumentParser(description="LanceDB historical memory search")
    parser.add_argument("--query", type=str, required=True)
    parser.add_argument("--limit", type=int, default=MAX_RESULTS)
    parser.add_argument("--agent", type=str, default="main")
    parser.add_argument("--db-path", type=str, default=DEFAULT_DB_PATH)
    parser.add_argument("--embedding-url", type=str, default=DEFAULT_EMBEDDING_URL)
    parser.add_argument("--embedding-model", type=str, default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    start_time = time.time()

    embedding = get_embedding(args.query, args.embedding_url, args.embedding_model)
    if embedding is None:
        print(json.dumps({"results": [], "provider": "lancedb-historical", "model": args.embedding_model}))
        return

    try:
        db = connect_db(args.db_path)
        table = ensure_table_schema(db)
        raw_results = search_similar(table, embedding, agent=args.agent, max_results=args.limit)
        formatted_results = [format_result(r) for r in raw_results]

        output = {
            "results": formatted_results,
            "provider": "lancedb-historical",
            "model": args.embedding_model,
            "count": len(formatted_results),
            "query_time_ms": int((time.time() - start_time) * 1000),
        }
        print(json.dumps(output, ensure_ascii=False))

    except Exception as e:
        logger.error(f"LanceDB search error: {e}")
        print(json.dumps({"results": [], "provider": "lancedb-historical",
                          "model": args.embedding_model, "error": str(e)}))


if __name__ == "__main__":
    exit_code = 0
    try:
        main()
    except SystemExit as e:
        exit_code = int(e.code) if isinstance(e.code, int) else 0
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        finally:
            os._exit(exit_code)
