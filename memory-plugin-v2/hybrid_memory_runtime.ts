import fs from "node:fs";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

type RewriteRule = { pattern: string; rewrite: string };
type NoiseRule = { regex: string; action?: string };

type RuntimeConfig = {
  rewriteRules: RewriteRule[];
  noiseRules: NoiseRule[];
  fallbackEnabled: boolean;
  vectorScriptPath?: string;
  pythonBin: string;
};

function loadJson<T>(file: string, fallback: T): T {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8")) as T;
  } catch {
    return fallback;
  }
}

function loadRuntimeConfig(baseDir = path.join(process.env.HOME || "", ".openclaw", "memory")): RuntimeConfig {
  const rewrite = loadJson<{ rules?: RewriteRule[] }>(path.join(baseDir, "chinese_rewrite_map.json"), {});
  const noise = loadJson<{ patterns?: NoiseRule[] }>(path.join(baseDir, "noise_intent_patterns.json"), {});
  const fallback = loadJson<{ enabled?: boolean; scriptPath?: string; pythonBin?: string }>(
    path.join(baseDir, "hybrid_fallback_config.json"),
    {},
  );

  return {
    rewriteRules: rewrite.rules || [],
    noiseRules: noise.patterns || [],
    fallbackEnabled: Boolean(fallback.enabled ?? false),
    vectorScriptPath: fallback.scriptPath,
    pythonBin: fallback.pythonBin || "python3",
  };
}

function isNoiseQuery(query: string, rules: NoiseRule[]): boolean {
  for (const r of rules) {
    if (!r.regex) continue;
    const hit = new RegExp(r.regex, "i").test(query);
    if (!hit) continue;
    if ((r.action || "short_circuit") === "exclude") return false;
    return true;
  }
  return false;
}

function rewriteQuery(query: string, rules: RewriteRule[]): string {
  const sorted = [...rules].sort((a, b) => (b.pattern?.length || 0) - (a.pattern?.length || 0));
  for (const r of sorted) {
    if (query.includes(r.pattern)) return r.rewrite;
  }
  return query;
}

async function whooshSearch(query: string, limit = 8): Promise<any> {
  const script = path.join(process.cwd(), "memory-plugin-v2", "whoosh_search.py");
  const { stdout } = await execFileAsync("python3", [script, "search", "--query", query, "--limit", String(limit)], {
    timeout: 3000,
    maxBuffer: 2 * 1024 * 1024,
  });
  return stdout ? JSON.parse(stdout) : { results: [] };
}

async function vectorFallback(query: string, limit: number, cfg: RuntimeConfig): Promise<any | null> {
  if (!cfg.fallbackEnabled || !cfg.vectorScriptPath || !fs.existsSync(cfg.vectorScriptPath)) return null;
  const { stdout } = await execFileAsync(cfg.pythonBin, [cfg.vectorScriptPath, "--query", query, "--limit", String(limit)], {
    timeout: 1500,
    maxBuffer: 2 * 1024 * 1024,
  });
  return stdout ? JSON.parse(stdout) : null;
}

async function lancedbHistorical(query: string, limit = 3): Promise<any[]> {
  // Placeholder: connect your lancedb_historical.py / service here.
  return [];
}

export async function hybridSearch(query: string, limit = 8): Promise<any> {
  const cfg = loadRuntimeConfig();

  if (isNoiseQuery(query, cfg.noiseRules)) {
    return { results: [], provider: "hybrid", noise_flagged: true };
  }

  const rewritten = rewriteQuery(query, cfg.rewriteRules);
  const main = await whooshSearch(rewritten, limit);

  let result = main;
  if (!Array.isArray(main?.results) || main.results.length === 0) {
    const fb = await vectorFallback(rewritten, limit, cfg);
    if (fb?.results?.length) result = fb;
  }

  const historical = await lancedbHistorical(rewritten, 3);
  return {
    ...(result || { results: [] }),
    rewritten_query: rewritten === query ? undefined : rewritten,
    historical_solutions: historical,
  };
}
