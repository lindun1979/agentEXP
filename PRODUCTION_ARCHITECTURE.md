# Production Architecture (Current Internal Runtime)

This document clarifies the difference between this repository's starter sample and the production memory runtime currently used in our OpenClaw environment.

## 1) Scope clarification

- **This repo (`agentEXP`)**: starter/onboarding sample for sharing concepts and quick setup.
- **Production runtime**: internal `memory-hybrid` implementation in `~/.openclaw/extensions/memory-hybrid/`.

## 2) Production retrieval pipeline

1. Query preprocessing
   - Chinese rewrite rules
   - Noise-intent filtering
2. Primary retrieval
   - **Whoosh** index build/search (`whoosh_search.py`)
3. Optional fallback (config-driven)
   - **Vector fallback** (`vector_fallback_search.py`)
4. Historical enrichment
   - **LanceDB historical search** (`lancedb_historical.py`)
5. Return merged response
   - including optional `historical_solutions`

## 3) Key production behavior

- Memory plugin slot points to `memory-hybrid`
- Whoosh is the main path
- LanceDB is used as historical memory enrichment layer
- Base qmd fallback is disabled in production safety profile

## 4) Why this repo still mentions qmd

This repository was initially published as a **starter kit** for teammates to quickly understand:
- query rewrite
- noise filtering
- hybrid retrieval concepts

Its qmd-based adapter is intentionally lightweight and does not represent the current full production chain.

## 5) Recommended reading order

1. `README.md`
2. `memory-plugin/TEAM_ONBOARDING.md`
3. This file (`PRODUCTION_ARCHITECTURE.md`)

---

If you are validating production behavior, use internal runtime/plugin sources rather than this starter alone.
