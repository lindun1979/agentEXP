# memory-hybrid for OpenClaw 4.5

Hybrid memory plugin combining **Whoosh BM25 full-text search** and **LanceDB vector search** for OpenClaw 4.5, with Chinese language support.

## Features

- **Whoosh BM25**: Full-text search with custom Chinese tokenizer and score adjustments
- **LanceDB Vector**: Semantic search over historical solutions/decisions
- **Vector Fallback**: Automatic fallback to vector search when BM25 confidence is low
- **Chinese Query Rewrite**: Pattern-based query rewriting for better Chinese recall
- **Noise Filtering**: Filters out low-value queries (greetings, confirmations)
- **Auto-Recall**: Injects relevant memories at conversation start (`before_agent_start` hook)
- **Auto-Capture**: Saves important information at conversation end (`agent_end` hook)
- **Result Caching**: 5-minute TTL, 200-entry LRU cache

## Architecture

```
Query → Noise Filter → Chinese Rewrite
  ↓
  Whoosh BM25 Search (MEMORY.md + memory/**/*.md)
  ↓
  Low Confidence? → Vector Fallback (embedding-based)
  ↓
  LanceDB Historical (solutions/decisions)
  ↓
  Merge & Dedupe → Cache → Return
```

## Plugin Structure

```
memory-hybrid-v45/
├── openclaw.plugin.json    # Plugin manifest (kind: "memory")
├── package.json            # Node deps (@sinclair/typebox)
├── index.ts                # Main entry (definePluginEntry)
├── scripts/
│   ├── embedding_server.py # FastAPI /v1/embeddings (bge-small-zh-v1.5, 512d)
│   ├── whoosh_search.py    # BM25 search with ChineseTokenizer
│   ├── lancedb_historical.py   # Vector search over historical memory
│   ├── vector_fallback_search.py # Fallback when BM25 misses
│   └── requirements.txt
└── config/
    ├── chinese_rewrite_map.json
    ├── noise_intent_patterns.json
    └── hybrid_fallback_config.json
```

## Installation

### 1. Copy plugin to OpenClaw extensions

```bash
cp -r memory-hybrid-v45 ~/.openclaw/extensions/memory-hybrid
cd ~/.openclaw/extensions/memory-hybrid && npm install
```

### 2. Set up Python environment

```bash
python3 -m venv /Volumes/data/workspace/memory-hybrid-venv
/Volumes/data/workspace/memory-hybrid-venv/bin/pip install -r scripts/requirements.txt
```

### 3. Download embedding model

```bash
HF_HOME=/Volumes/data/workspace/hf_cache \
python3 -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"
```

### 4. Configure openclaw.json

```json
{
  "plugins": {
    "allow": ["memory-hybrid"],
    "entries": {
      "memory-lancedb": { "enabled": false },
      "memory-core": { "enabled": false },
      "memory-hybrid": {
        "enabled": true,
        "config": {
          "embedding": {
            "serviceUrl": "http://localhost:8090",
            "model": "bge-small-zh",
            "dimensions": 512
          },
          "pythonBin": "/Volumes/data/workspace/memory-hybrid-venv/bin/python",
          "hfHome": "/Volumes/data/workspace/hf_cache",
          "whooshIndexDir": "/Volumes/data/workspace/openclaw-memory/whoosh_index",
          "lancedbPath": "/Volumes/data/workspace/openclaw-memory/lancedb",
          "autoRecall": true,
          "autoCapture": true
        }
      }
    },
    "slots": {
      "memory": "memory-hybrid"
    }
  }
}
```

### 5. Set up embedding server as system service (macOS)

Create `~/Library/LaunchAgents/ai.openclaw.embedding-server.plist` — see deployment notes.

## Compatibility

- OpenClaw >= 4.5 (`definePluginEntry` API)
- Python >= 3.9
- macOS / Linux

## Differences from 3.7 version

| Aspect | 3.7 | 4.5 |
|--------|-----|-----|
| Entry point | `export default { register(api) {} }` | `definePluginEntry({ register(api) {} })` |
| Tool parameters | Raw JSON schema | `@sinclair/typebox` |
| Tool return | `JSON.stringify(result)` | `{ content: [{type:"text",text}], details }` |
| Lifecycle hooks | `api.on(event, handler)` | Same (compatible) |
| Embedding server | External (assumed running) | Bundled + launchd service |
