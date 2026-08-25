import { existsSync, mkdirSync, createWriteStream, chmodSync, readFileSync } from "fs";
import { join } from "path";
import { homedir, arch, platform } from "os";
import { pipeline } from "stream/promises";
import { execSync } from "child_process";

const RUACH_DIR = join(homedir(), ".ruach");
const RUNTIME_DIR = join(RUACH_DIR, "runtime");
const MODELS_DIR = join(RUACH_DIR, "models");

// GitHub releases base URL — update this to your repo
const RELEASES_BASE = "https://github.com/Windowseven/RUACH-AI/releases/download";

// ── Detect actual architecture (Node.js can lie on Termux) ──
function detectArch() {
  // First try uname -m (most reliable on Linux/Android)
  try {
    const uname = execSync("uname -m", { encoding: "utf8" }).trim().toLowerCase();
    if (uname === "armv7l" || uname === "armv6l") return "arm";
    if (uname === "aarch64" || uname === "arm64") return "arm64";
    if (uname === "x86_64" || uname === "amd64") return "x64";
  } catch {}

  // Fallback to Node.js process.arch
  return arch();
}

// ── Architecture mapping ───────────────────────────────────
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

function getServerBinaryName() {
  return platform() === "win32" ? "llama-server.exe" : "llama-server";
}

// ── Download helpers ───────────────────────────────────────
async function downloadFile(url, dest, label) {
  if (existsSync(dest)) {
    console.log(`  ✓ ${label} already exists`);
    return true;
  }

  console.log(`  ↓ Downloading ${label}...`);
  console.log(`    ${url}`);

  mkdirSync(join(dest, ".."), { recursive: true });

  // Try curl first (more reliable on Termux), then fetch
  const curlOk = await downloadWithCurl(url, dest);
  if (curlOk) {
    if (platform() !== "win32") chmodSync(dest, 0o755);
    console.log(`  ✓ ${label} installed`);
    return true;
  }

  // Fallback to Node.js fetch with retries
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const resp = await fetch(url, { redirect: "follow" });
      if (!resp.ok) throw new Error(`HTTP ${resp.status} ${resp.statusText}`);
      const fileStream = createWriteStream(dest);
      await pipeline(resp.body, fileStream);
      if (platform() !== "win32") chmodSync(dest, 0o755);
      console.log(`  ✓ ${label} installed`);
      return true;
    } catch (err) {
      console.log(`    fetch attempt ${attempt}/3 failed: ${err.message}`);
      if (attempt < 3) await new Promise((r) => setTimeout(r, 2000 * attempt));
    }
  }

  console.log(`  ✗ ${label} failed after 3 attempts`);
  try { if (existsSync(dest)) (await import("fs")).unlinkSync(dest); } catch {}
  return false;
}

async function downloadWithCurl(url, dest) {
  try {
    execSync(`curl -fSL --connect-timeout 15 --max-time 120 -o "${dest}" "${url}"`, {
      stdio: "pipe",
      timeout: 130000,
    });
    return true;
  } catch {
    return false;
  }
}

// ── Install runtime ────────────────────────────────────────
export async function installRuntime() {
  const archLabel = getArchLabel();
  const bin = getServerBinaryName();
  const dest = join(RUNTIME_DIR, archLabel, bin);

  if (existsSync(dest)) {
    console.log(`  ✓ Runtime already installed (${archLabel})`);
    return dest;
  }

  // Try GitHub release
  const version = "0.5.0";
  const url = `${RELEASES_BASE}/v${version}/llama-server-${archLabel}.tar.gz`;

  console.log(`\n  Installing runtime for ${archLabel}...`);

  // Download tar.gz
  const tarDest = join(RUNTIME_DIR, `${archLabel}.tar.gz`);
  const ok = await downloadFile(url, tarDest, `runtime (${archLabel})`);

  if (!ok) {
    // Fallback: try direct binary URL
    const binUrl = `${RELEASES_BASE}/v${version}/${bin}-${archLabel}`;
    const binOk = await downloadFile(binUrl, dest, `runtime binary (${archLabel})`);
    if (!binOk) {
      throw new Error(
        `Could not download runtime for ${archLabel}.\n` +
        `Manually place ${bin} in: ${join(RUNTIME_DIR, archLabel)}/`
      );
    }
    return dest;
  }

  // Extract tar.gz
  const { execSync } = await import("child_process");
  const extractDir = join(RUNTIME_DIR, archLabel);
  mkdirSync(extractDir, { recursive: true });
  try {
    // Extract to temp dir first to handle both flat and nested archives
    const tmpDir = join(RUNTIME_DIR, `_tmp_${archLabel}`);
    mkdirSync(tmpDir, { recursive: true });
    execSync(`tar -xzf "${tarDest}" -C "${tmpDir}"`, { stdio: "pipe" });

    // Check if files are in a subdirectory or at root
    const { readdirSync, statSync, renameSync, rmSync } = await import("fs");
    const entries = readdirSync(tmpDir);
    if (entries.length === 1 && statSync(join(tmpDir, entries[0])).isDirectory()) {
      // Nested: move contents from subdirectory
      const subDir = join(tmpDir, entries[0]);
      for (const f of readdirSync(subDir)) {
        renameSync(join(subDir, f), join(extractDir, f));
      }
    } else {
      // Flat: move all files directly
      for (const f of entries) {
        renameSync(join(tmpDir, f), join(extractDir, f));
      }
    }
    rmSync(tmpDir, { recursive: true, force: true });

    // Make binary executable
    if (platform() !== "win32" && existsSync(dest)) {
      chmodSync(dest, 0o755);
    }

    // Also make all extracted files executable (shared libs, etc.)
    if (platform() !== "win32") {
      try {
        const { readdirSync } = await import("fs");
        for (const f of readdirSync(extractDir)) {
          chmodSync(join(extractDir, f), 0o755);
        }
      } catch {}
    }

    // Clean up tar
    const { unlinkSync } = await import("fs");
    unlinkSync(tarDest);
  } catch (err) {
    throw new Error(`Failed to extract runtime: ${err.message}`);
  }

  if (!existsSync(dest)) {
    throw new Error(`Runtime binary not found after extraction at ${dest}`);
  }

  return dest;
}

// ── Install model ──────────────────────────────────────────
export async function installModel() {
  // Check if any model exists
  if (existsSync(MODELS_DIR)) {
    try {
      const { readdirSync } = await import("fs");
      const entries = readdirSync(MODELS_DIR);
      const gguf = entries.find((e) => e.endsWith(".gguf"));
      if (gguf) {
        console.log(`  ✓ Model already installed: ${gguf}`);
        return join(MODELS_DIR, gguf);
      }
    } catch {}
  }

  mkdirSync(MODELS_DIR, { recursive: true });

  // Download TinyLlama 1.1B Q4_0 (~637 MB) — small enough for ARM32
  const modelName = "tinyllama-1.1b-q4_0.gguf";
  const url = "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_0.gguf";
  const dest = join(MODELS_DIR, modelName);

  console.log(`\n  Installing default model (TinyLlama 1.1B Q4_0, ~637 MB)...`);
  const ok = await downloadFile(url, dest, "default model");

  if (!ok) {
    throw new Error(
      `Could not download model.\n` +
      `Manually place a .gguf file in: ${MODELS_DIR}/`
    );
  }

  return dest;
}

// ── Full setup ─────────────────────────────────────────────
export async function fullSetup() {
  console.log("\n  RUACH Setup\n");

  // Create directories
  mkdirSync(RUACH_DIR, { recursive: true });
  mkdirSync(RUNTIME_DIR, { recursive: true });
  mkdirSync(MODELS_DIR, { recursive: true });

  // 1. Install runtime
  let runtimePath;
  try {
    runtimePath = await installRuntime();
  } catch (err) {
    console.log(`  ✗ Runtime: ${err.message}`);
    runtimePath = null;
  }

  // 2. Install model
  let modelPath;
  try {
    modelPath = await installModel();
  } catch (err) {
    console.log(`  ✗ Model: ${err.message}`);
    modelPath = null;
  }

  // 3. Frontend (pre-built in repo, no build needed on device)
  const projectRoot = join(import.meta.dirname, "..", "..");
  const frontendIndex = join(projectRoot, "frontend", "dist", "index.html");
  if (existsSync(frontendIndex)) {
    console.log("\n  ✓ Frontend ready");
  } else {
    console.log("\n  ⚠ Frontend not found — rebuild on dev machine: cd frontend && npm run build");
  }

  // 4. Link ruach command globally
  try {
    const { execSync } = await import("child_process");
    const projectRoot = join(import.meta.dirname, "..", "..");
    execSync("npm link", { cwd: projectRoot, stdio: "pipe" });
    console.log("  ✓ `ruach` command linked");
  } catch {
    console.log("  ⚠ Could not link `ruach` — use `npx ruach start` instead");
  }

  // 5. Save config
  const { writeFileSync } = await import("fs");
  const config = {
    version: "0.5.0",
    runtime: runtimePath,
    model: modelPath,
    installed_at: new Date().toISOString(),
  };
  writeFileSync(join(RUACH_DIR, "config.json"), JSON.stringify(config, null, 2));

  // 6. Summary
  console.log("\n  ── Setup Complete ──────────────────────");
  if (runtimePath && modelPath) {
    console.log("  ✓ Everything installed. Run `ruach start` to begin.\n");
  } else {
    console.log("  ⚠ Partial install. Check errors above.\n");
  }

  return { runtime: runtimePath, model: modelPath };
}
