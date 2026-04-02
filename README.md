# agentEXP

OpenClaw memory plugin sharing repo.

## Included

- `memory-plugin/hybrid_memory_adapter.py` — hybrid memory retrieval adapter
- `memory-plugin/config/*.json` — rewrite / noise / strategy config
- `memory-plugin/install.sh` — quick installer (copy configs to `~/.openclaw/memory`)

## Quick Start

```bash
git clone https://github.com/lindun1979/agentEXP.git
cd agentEXP/memory-plugin
bash install.sh
```

## What this plugin does

1. Noise-intent filtering
2. Chinese query rewrite
3. Hybrid retrieval (`qmd search` first, `qmd vsearch` fallback)

## Notes

- Requires `qmd` in PATH.
- Default config target: `~/.openclaw/memory/`.
- Adapter defaults to agent `main`; can pass `agent="OpCoder"` when initializing.
