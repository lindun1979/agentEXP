# agentEXP

OpenClaw memory plugin sharing repo.

> ⚠️ **Important scope note**
> This repo currently contains a **starter kit / onboarding sample** for hybrid memory retrieval.
> It is **NOT** a full mirror of our production runtime implementation.

## Included

- `memory-plugin/hybrid_memory_adapter.py` — starter hybrid memory adapter (qmd-based sample)
- `memory-plugin/config/*.json` — rewrite / noise / strategy config
- `memory-plugin/install.sh` — quick installer (copy configs to `~/.openclaw/memory`)
- `PRODUCTION_ARCHITECTURE.md` — production architecture & differences vs starter

## Quick Start

```bash
git clone https://github.com/lindun1979/agentEXP.git
cd agentEXP/memory-plugin
bash install.sh
```

## Starter capabilities (this repo)

1. Noise-intent filtering
2. Chinese query rewrite
3. Hybrid retrieval (`qmd search` first, `qmd vsearch` fallback)

## Production reality (current internal runtime)

- Primary retrieval: **Whoosh**
- Optional fallback: **Vector fallback (CPU-only path, config-controlled)**
- Historical memory enrichment: **LanceDB historical solutions/decisions**
- Plugin slot: `memory-hybrid`
- Base qmd chain fallback: disabled in production safety profile

See `PRODUCTION_ARCHITECTURE.md` for details.

## Notes

- This starter requires `qmd` in PATH.
- Default config target: `~/.openclaw/memory/`.
- Adapter defaults to agent `main`; can pass `agent="OpCoder"` when initializing.
