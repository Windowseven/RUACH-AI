import { Router } from "express";
import { existsSync, readFileSync, readdirSync } from "fs";
import { join } from "path";
import { homedir, arch, platform } from "os";
import { execSync } from "child_process";

export const router = Router();

const RUACH_DIR = join(homedir(), ".ruach");

function detectArch() {
  try {
    const uname = execSync("uname -m", { encoding: "utf8" }).trim().toLowerCase();
    if (uname === "armv7l" || uname === "armv6l") return "arm";
    if (uname === "aarch64" || uname === "arm64") return "arm64";
    if (uname === "x86_64" || uname === "amd64") return "x64";
  } catch {}
  return arch();
}

function getArchLabel() {
  const a = detectArch();
  const p = platform();
  if (p === "android" || p === "linux") {
    if (a === "arm") return "arm-linux";
    if (a === "arm64") return "aarch64-linux";
    if (a === "x64") return "x86_64-linux";
  }
  if (p === "darwin") {
    if (a === "arm64") return "aarch64-macos";
    if (a === "x64") return "x86_64-macos";
  }
  if (p === "win32") return "x86_64-windows";
  return `${a}-${p}`;
}

// GET /api/v1/ready — health check (matches frontend expectations)
router.get("/ready", (req, res) => {
  const llm = req.app.get("llm");
  const modelPath = findModel();
  const serverBin = findServer();

  const hasRuntime = !!serverBin;
  const hasModel = !!modelPath;

  // Frontend expects: status, database, inference
  // database = "available" if runtime + model exist
  // inference = "available" if LLM is running or can start
  let status = "ready";
  let database = "unavailable";
  let inference = "unavailable";

  if (hasRuntime && hasModel) {
    database = "available";
  }
  if (llm.isRunning()) {
    inference = "available";
  } else if (hasRuntime && hasModel) {
    // Can start on demand
    inference = "available";
    status = "ready";
  } else {
    status = "degraded";
  }

  res.json({
    data: {
      status,
      database,
      inference,
    },
  });
});

// GET /api/v1/health — detailed health
router.get("/health", (req, res) => {
  const llm = req.app.get("llm");
  const modelPath = findModel();
  const serverBin = findServer();

  res.json({
    data: {
      server: "ok",
      inference: {
        status: llm.isRunning() ? "running" : "stopped",
        pid: llm.getPid(),
        uptime: llm.getUptime(),
      },
      model: {
        path: modelPath,
        exists: !!modelPath,
      },
      runtime: {
        path: serverBin,
        exists: !!serverBin,
      },
      platform: process.platform,
      arch: process.arch,
      memory: process.memoryUsage(),
    },
  });
});

// ── Helpers ────────────────────────────────────────────────
function findModel() {
  const modelsDir = join(RUACH_DIR, "models");
  if (!existsSync(modelsDir)) return null;
  const files = ["model.gguf", "model-q4_0.gguf"];
  for (const f of files) {
    const p = join(modelsDir, f);
    if (existsSync(p)) return p;
  }
  try {
    const entries = readdirSync(modelsDir);
    const gguf = entries.find((e) => e.endsWith(".gguf"));
    return gguf ? join(modelsDir, gguf) : null;
  } catch {
    return null;
  }
}

function findServer() {
  const archLabel = getArchLabel();
  const bin = process.platform === "win32" ? "llama-server.exe" : "llama-server";
  const candidates = [
    join(RUACH_DIR, "runtime", archLabel, bin),
    join(RUACH_DIR, "runtime", bin),
  ];
  return candidates.find((p) => existsSync(p)) || null;
}
