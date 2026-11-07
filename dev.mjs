// One command to run MemoryGuard: FastAPI on :8000 + Vite dashboard on :5173.
// Usage (from the project root):  npm run dev
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const win = process.platform === "win32";
const python = path.join(root, ".venv", win ? "Scripts/python.exe" : "bin/python");

if (!existsSync(python)) {
  console.error(`Python venv not found at ${python}. See README.md -> Setup.`);
  process.exit(1);
}

const procs = [
  spawn(python, ["-m", "uvicorn", "api:app", "--port", "8000"], {
    cwd: path.join(root, "memoryguard"), stdio: "inherit",
  }),
  spawn(win ? "npm.cmd" : "npm", ["run", "dev"], {
    cwd: path.join(root, "web"), stdio: "inherit", shell: win,
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
