# memory-plugin-v2 (Production-aligned skeleton)

This folder provides a **production-aligned skeleton** of our current memory-hybrid runtime design:

- Whoosh as primary retrieval
- Optional vector fallback (config-controlled)
- LanceDB historical enrichment
- Query rewrite + noise filtering

> This is a sanitized reference implementation for architecture sharing and migration.
> It is not a drop-in replacement for your exact internal environment.

## Files

- `hybrid_memory_runtime.ts` — runtime orchestration skeleton (TypeScript)
- `whoosh_search.py` — Whoosh index/search script (Python)
- `MIGRATION_GUIDE.md` — move from starter(qmd) to production-aligned v2

## Quick structure

```text
memory-plugin-v2/
  ├─ hybrid_memory_runtime.ts
  ├─ whoosh_search.py
  └─ MIGRATION_GUIDE.md
```

## Intended use

- Internal review / teammate onboarding
- Architecture communication
- Starting point for custom productionization

## Not included

- Environment-specific secrets
- Internal node/network endpoints
- Proprietary data pipelines
