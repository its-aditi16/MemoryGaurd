// One command to run MemoryGuard: FastAPI on :8000 + Vite dashboard on :5173.
// Usage (from the project root):  npm run dev
//
// Security: a fresh random API token is created for every run and shared only with the API and
// the Vite proxy (written to memoryguard/data/.api_token, which is gitignored). Browser JavaScript
// never sees it, so other websites cannot call the API.
import { spawn } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const win = process.platform === "win32";
const python = path.join(root, ".venv", win ? "Scripts/python.exe" : "bin/python");

if (!existsSync(python)) {
  console.error(`Python venv not found at ${python}. See README.md -> Setup.`);
  process.exit(1);
}

const dataDir = path.join(root, "memoryguard", "data");
mkdirSync(dataDir, { recursive: true });
const token = randomBytes(32).toString("base64url");
writeFileSync(path.join(dataDir, ".api_token"), token, { mode: 0o600 });
const env = { ...process.env, MG_API_TOKEN: token };

const procs = [
  spawn(python, ["-m", "uvicorn", "api:app", "--host", "127.0.0.1", "--port", "8000"], {
    cwd: path.join(root, "memoryguard"), stdio: "inherit", env,
  }),
  spawn(win ? "npm.cmd" : "npm", ["run", "dev"], {
    cwd: path.join(root, "web"), stdio: "inherit", shell: win, env,
  }),
];

const stop = () => {
  for (const p of procs) if (!p.killed) p.kill();
  process.exit(0);
};
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
for (const p of procs) p.on("exit", (code) => { if (code) { console.error(`process exited with ${code}`); stop(); } });

console.log("\n  MemoryGuard  API http://127.0.0.1:8000   Dashboard http://localhost:5173\n");
