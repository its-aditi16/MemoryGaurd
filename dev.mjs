// One command to run MemoryGuard: FastAPI on :8000 + Vite dashboard on :5173
// (+ the Hindsight memory server on :8888 when MEMORY_BACKEND=hindsight).
// Usage (from the project root):  npm run dev
//
// Security: a fresh random API token is created for every run and shared only with the API and
// the Vite proxy (written to memoryguard/data/.api_token, which is gitignored). Browser JavaScript
// never sees it, so other websites cannot call the API. Hindsight is bound to 127.0.0.1 only.
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const win = process.platform === "win32";
const python = path.join(root, ".venv", win ? "Scripts/python.exe" : "bin/python");
const HINDSIGHT_URL = "http://127.0.0.1:8888";

if (!existsSync(python)) {
  console.error(`Python venv not found at ${python}. See README.md -> Setup.`);
  process.exit(1);
}

// Minimal .env reader (KEY=value lines) - values are passed to child processes, never printed.
const dotenv = {};
const envFile = path.join(root, ".env");
if (existsSync(envFile)) {
  for (const line of readFileSync(envFile, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)\s*$/);
    if (m) dotenv[m[1]] = m[2];
  }
}
const backend = (process.env.MEMORY_BACKEND || dotenv.MEMORY_BACKEND || "local").toLowerCase();

const dataDir = path.join(root, "memoryguard", "data");
mkdirSync(dataDir, { recursive: true });
const token = randomBytes(32).toString("base64url");
writeFileSync(path.join(dataDir, ".api_token"), token, { mode: 0o600 });
const env = { ...process.env, MG_API_TOKEN: token };

const procs = [];
const stop = () => {
  for (const p of procs) if (!p.killed) p.kill();
  process.exit(0);
};
process.on("SIGINT", stop);
process.on("SIGTERM", stop);

async function hindsightUp() {
  try { return (await fetch(`${HINDSIGHT_URL}/version`)).ok; } catch { return false; }
}

async function startHindsight() {
  if (await hindsightUp()) {
    console.log("  Hindsight already running on 127.0.0.1:8888 - reusing it");
    return;
  }
  const exe = path.join(root, ".venv-hindsight", win ? "Scripts/hindsight-api.exe" : "bin/hindsight-api");
  if (!existsSync(exe)) {
    console.error("MEMORY_BACKEND=hindsight but the Hindsight server isn't installed. See README.md -> Hindsight.");
    process.exit(1);
  }
  const provider = (dotenv.LLM_PROVIDER || "groq").toLowerCase();
  const model = dotenv.LLM_MODEL || { groq: "openai/gpt-oss-120b", anthropic: "claude-opus-5-5", openai: "gpt-4o-mini" }[provider];
  const hs = spawn(exe, ["--host", "127.0.0.1", "--port", "8888", "--log-level", "warning"], {
    stdio: "ignore",
    env: {
      ...process.env,
      HINDSIGHT_API_LLM_PROVIDER: provider,
      HINDSIGHT_API_LLM_API_KEY: dotenv.LLM_API_KEY || "",
      ...(model ? { HINDSIGHT_API_LLM_MODEL: model } : {}),
      ...(dotenv.LLM_BASE_URL ? { HINDSIGHT_API_LLM_BASE_URL: dotenv.LLM_BASE_URL } : {}),
    },
  });
  procs.push(hs);
  process.stdout.write("  Starting Hindsight memory server (first start downloads local models)");
  for (let i = 0; i < 180; i++) {
    if (await hindsightUp()) { console.log(" - ready"); return; }
    if (hs.exitCode !== null) { console.error("\nHindsight server exited during startup."); process.exit(1); }
    await new Promise((r) => setTimeout(r, 2000));
    process.stdout.write(".");
  }
  console.error("\nHindsight server did not become ready within 6 minutes.");
  stop();
}

const hindsightUrl = dotenv.HINDSIGHT_URL || HINDSIGHT_URL;
const localHindsight = /^https?:\/\/(127\.0\.0\.1|localhost)(:|\/|$)/.test(hindsightUrl);
if (backend === "hindsight" && localHindsight) await startHindsight();
else if (backend === "hindsight") console.log(`  Using Hindsight Cloud at ${new URL(hindsightUrl).host}`);

procs.push(
  spawn(python, ["-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8000"], {
    cwd: path.join(root, "memoryguard"), stdio: "inherit", env,
  }),
  spawn(win ? "npm.cmd" : "npm", ["run", "dev"], {
    cwd: path.join(root, "web"), stdio: "inherit", shell: win, env,
  }),
);
for (const p of procs.slice(-2)) p.on("exit", (code) => { if (code) { console.error(`process exited with ${code}`); stop(); } });

console.log(`\n  MemoryGuard  memory=${backend}${backend === "hindsight" ? (localHindsight ? " (local)" : " (cloud)") : ""}  API http://127.0.0.1:8000   Dashboard http://localhost:5173\n`);
