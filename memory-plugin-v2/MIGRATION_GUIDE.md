# Migration Guide: starter(qmd) -> production-aligned v2

## Goal
Move from starter qmd-style adapter to production-aligned pipeline:

- Whoosh primary retrieval
- Optional vector fallback
- LanceDB historical enrichment

## Step 1: keep config compatibility
Reuse existing files under `~/.openclaw/memory/`:

- `chinese_rewrite_map.json`
- `noise_intent_patterns.json`
- `hybrid_fallback_config.json` (if using fallback)

## Step 2: introduce Whoosh index lifecycle

- Build index once at startup
- Rebuild on schedule or after memory file updates

Example:

```bash
python3 memory-plugin-v2/whoosh_search.py build --index ~/.openclaw/memory/whoosh_index/main
```

## Step 3: switch search path

From:
- `qmd search -> qmd vsearch fallback`

To:
- `whoosh search -> vector fallback (optional)`
- plus `historical_solutions` enrichment from LanceDB

## Step 4: keep safe rollout

1. Shadow mode (compare results, no user-facing switch)
2. Small-traffic switch for miss-only fallback
3. Observe latency/quality metrics
4. Full switch after acceptance

## Step 5: verify acceptance

- Result relevance stable
- Latency within target
- No hard dependency on qmd runtime path
- Historical solutions field available when enabled

---

If your environment is already on memory-hybrid production chain, use this folder as reference docs/code skeleton only.
