import { existsSync, mkdirSync, createWriteStream, chmodSync, readFileSync, readdirSync, statSync, renameSync, rmSync, unlinkSync, copyFileSync, writeFileSync } from "fs";
import { join, dirname } from "path";
import { homedir, arch, platform, cpus } from "os";
import { pipeline } from "stream/promises";
import { execSync } from "child_process";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const RUACH_DIR = join(homedir(), ".ruach");
const RUNTIME_DIR = join(RUACH_DIR, "runtime");
const MODELS_DIR = join(RUACH_DIR, "models");
const BUILD_DIR = join(RUACH_DIR, "build-src");

const RELEASES_BASE = "https://github.com/Windowseven/RUACH-AI/releases/download";

// ── Platform detection ──────────────────────────────────────
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

function isTermux() {
  return existsSync("/data/data/com.termux");
}

function isArm32() {
  return detectArch() === "arm";
}

function getServerBinaryName() {
  return platform() === "win32" ? "llama-server.exe" : "llama-server";
}

function getCpuThreads() {
  try {
    return Math.max(1, parseInt(execSync("nproc", { encoding: "utf8" }).trim(), 10) || 2);
  } catch {
    try {
      return Math.max(1, parseInt(execSync("grep -c ^processor /proc/cpuinfo", { encoding: "utf8" }).trim(), 10) || 2);
    } catch {
      return Math.max(1, cpus().length - 1);
    }
  }
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

  // Try curl first (more reliable on Termux)
  try {
    execSync(`curl -fSL --connect-timeout 15 --max-time 600 -o "${dest}" "${url}"`, {
      stdio: "pipe",
      timeout: 610000,
    });
    if (platform() !== "win32") chmodSync(dest, 0o755);
    console.log(`  ✓ ${label} installed`);
    return true;
  } catch {}

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
  try { if (existsSync(dest)) unlinkSync(dest); } catch {}
  return false;
}

// ── Test if binary actually runs ───────────────────────────
function testBinary(binPath) {
  try {
    const binDir = dirname(binPath);
    const env = {
      ...process.env,
      LD_LIBRARY_PATH: binDir + (process.env.LD_LIBRARY_PATH ? ":" + process.env.LD_LIBRARY_PATH : ""),
    };
    const result = execSync(`"${binPath}" --version`, {
      encoding: "utf8",
      timeout: 5000,
      stdio: "pipe",
      env,
    });
    return result.length > 0;
  } catch {
    return false;
  }
}

// ── Get architecture-specific cmake flags ──────────────────
function getCmakeFlags() {
  const a = detectArch();

  const flags = [
    "-DCMAKE_BUILD_TYPE=Release",
    "-DLLAMA_CURL=OFF",
    "-DLLAMA_BUILD_TESTS=OFF",
    "-DLLAMA_BUILD_EXAMPLES=OFF",
    "-DLLAMA_BUILD_UI=OFF",
    "-DGGML_LLAMAFILE=OFF",
  ];

  // ARM32: disable features that require ARMv8
  if (a === "arm") {
    flags.push("-DGGML_OPENMP=OFF");
  }

  return flags.join(" ");
}

// ── Build llama.cpp from source ────────────────────────────
async function buildFromSource(destDir, bin) {
  const threads = getCpuThreads();
  const cmakeFlags = getCmakeFlags();
  const a = detectArch();

  console.log(`\n  Building llama.cpp from source...`);
  console.log(`  Architecture: ${a} | Threads: ${threads} | Platform: ${platform()}`);

  // Install build tools
  const deps = isTermux() ? ["git", "cmake", "clang"] : ["git", "cmake", "g++"];
  const missing = [];
  for (const dep of deps) {
    try { execSync(`which ${dep}`, { stdio: "pipe" }); } catch { missing.push(dep); }
  }

  if (missing.length > 0) {
    console.log(`  Installing: ${missing.join(", ")}...`);
    try {
      if (isTermux()) {
        execSync(`pkg install -y ${missing.join(" ")}`, { stdio: "inherit", timeout: 180000 });
      } else if (platform() === "linux") {
        execSync(`sudo apt-get install -y ${missing.join(" ")}`, { stdio: "inherit", timeout: 180000 });
      }
    } catch {
      throw new Error(`Failed to install: ${missing.join(", ")}. Install manually first.`);
    }
  }

  mkdirSync(BUILD_DIR, { recursive: true });
  const srcDir = join(BUILD_DIR, "llama.cpp");

  try {
    // Clone with retries (slow mobile connections)
    if (existsSync(srcDir)) {
      console.log("  Updating llama.cpp...");
      try { execSync("git pull", { cwd: srcDir, stdio: "pipe", timeout: 60000 }); } catch {}
    } else {
      console.log("  Cloning llama.cpp (~35 MB)...");
      for (let attempt = 1; attempt <= 3; attempt++) {
        try {
          execSync("git clone --depth 1 --branch b10622 https://github.com/ggml-org/llama.cpp.git", {
            cwd: BUILD_DIR,
            stdio: "inherit",
            timeout: 600000,
          });
          break;
        } catch (err) {
          console.log(`    Clone attempt ${attempt}/3 failed`);
          if (attempt === 3) throw err;
          await new Promise((r) => setTimeout(r, 5000));
        }
      }
    }

    // Clean previous build
    const buildSubdir = join(srcDir, "build");
    if (existsSync(buildSubdir)) {
      rmSync(buildSubdir, { recursive: true, force: true });
    }

    // Configure
    console.log("  Configuring...");
    execSync(`cmake -B build ${cmakeFlags}`, {
      cwd: srcDir,
      stdio: "pipe",
      timeout: 120000,
    });

    // Build
    console.log(`  Building (${threads} threads, ~10 min on mobile)...`);
    execSync(`cmake --build build -j${threads}`, {
      cwd: srcDir,
      stdio: "inherit",
      timeout: 1200000,
    });

    // Verify binary was produced
    const builtBin = join(srcDir, "build", "bin", bin);
    if (!existsSync(builtBin)) {
      throw new Error("Build completed but llama-server binary not found");
    }

    // Copy to runtime directory
    mkdirSync(destDir, { recursive: true });
    const destBin = join(destDir, bin);
    copyFileSync(builtBin, destBin);
    chmodSync(destBin, 0o755);

    // Copy shared libs if any
    const buildBinDir = join(srcDir, "build", "bin");
    try {
      for (const f of readdirSync(buildBinDir)) {
        if (f.startsWith("lib") && (f.endsWith(".so") || f.endsWith(".dylib"))) {
          copyFileSync(join(buildBinDir, f), join(destDir, f));
        }
      }
    } catch {}

    // Verify it works
    if (!testBinary(destBin)) {
      throw new Error("Built binary doesn't run — missing dependencies?");
    }

    console.log("  ✓ Built and verified successfully");
    return destBin;
  } catch (err) {
    // Don't clean up on failure — let user see the error
    throw err;
  }
}

// ── Install runtime ────────────────────────────────────────
export async function installRuntime() {
  const archLabel = getArchLabel();
  const bin = getServerBinaryName();
  const destDir = join(RUNTIME_DIR, archLabel);
  const dest = join(destDir, bin);

  // Check if existing binary works
  if (existsSync(dest)) {
    if (testBinary(dest)) {
      console.log(`  ✓ Runtime already installed (${archLabel})`);
      return dest;
    }
    console.log(`  ⚠ Existing binary incompatible — will replace`);
  }

  // Strategy depends on platform:
  // - macOS/Linux x86_64: pre-built binaries work
  // - ARM32 (Termux): MUST build from source (cross-compiled never works)
  // - ARM64 Linux: try pre-built, fall back to build
  const needsBuildFromSource = isTermux() || (platform() === "linux" && isArm32());

  if (needsBuildFromSource) {
    return await buildFromSource(destDir, bin);
  }

  // Try pre-built binary
  const version = "0.5.0";
  const url = `${RELEASES_BASE}/v${version}/llama-server-${archLabel}.tar.gz`;

  console.log(`\n  Installing runtime for ${archLabel}...`);

  const tarDest = join(RUNTIME_DIR, `${archLabel}.tar.gz`);
  const ok = await downloadFile(url, tarDest, `runtime (${archLabel})`);

  if (ok) {
    try {
      mkdirSync(destDir, { recursive: true });
      const tmpDir = join(RUNTIME_DIR, `_tmp_${archLabel}`);
      mkdirSync(tmpDir, { recursive: true });
      execSync(`tar -xzf "${tarDest}" -C "${tmpDir}"`, { stdio: "pipe" });

      const entries = readdirSync(tmpDir);
      if (entries.length === 1 && statSync(join(tmpDir, entries[0])).isDirectory()) {
        for (const f of readdirSync(join(tmpDir, entries[0]))) {
          renameSync(join(tmpDir, entries[0], f), join(destDir, f));
        }
      } else {
        for (const f of entries) {
          renameSync(join(tmpDir, f), join(destDir, f));
        }
      }
      rmSync(tmpDir, { recursive: true, force: true });

      if (platform() !== "win32") {
        for (const f of readdirSync(destDir)) {
          chmodSync(join(destDir, f), 0o755);
        }
      }

      try { unlinkSync(tarDest); } catch {}
    } catch (err) {
      console.log(`  ✗ Extraction failed: ${err.message}`);
    }
  }

  // Verify
  if (existsSync(dest) && testBinary(dest)) {
    console.log(`  ✓ Runtime verified (${archLabel})`);
    return dest;
  }

  // Pre-built didn't work — try building from source
  console.log(`  ⚠ Pre-built binary incompatible — building from source...`);
  try {
    return await buildFromSource(destDir, bin);
  } catch (err) {
    throw new Error(`Runtime doesn't work and build failed: ${err.message}`);
  }
}

// ── Install model ──────────────────────────────────────────
export async function installModel() {
  if (existsSync(MODELS_DIR)) {
    try {
      const entries = readdirSync(MODELS_DIR);
      const gguf = entries.find((e) => e.endsWith(".gguf"));
      if (gguf) {
        console.log(`  ✓ Model already installed: ${gguf}`);
        return join(MODELS_DIR, gguf);
      }
    } catch {}
  }

  mkdirSync(MODELS_DIR, { recursive: true });

  const modelName = "tinyllama-1.1b-q4_0.gguf";
  const url = "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_0.gguf";
  const dest = join(MODELS_DIR, modelName);

  console.log(`\n  Installing default model (TinyLlama 1.1B Q4_0, ~637 MB)...`);
  const ok = await downloadFile(url, dest, "default model");

  if (!ok) {
    throw new Error(`Could not download model. Manually place a .gguf file in: ${MODELS_DIR}/`);
  }

  return dest;
}

// ── Full setup ─────────────────────────────────────────────
export async function fullSetup() {
  console.log("\n  RUACH Setup\n");

  mkdirSync(RUACH_DIR, { recursive: true });
  mkdirSync(RUNTIME_DIR, { recursive: true });
  mkdirSync(MODELS_DIR, { recursive: true });

  let runtimePath;
  try {
    runtimePath = await installRuntime();
  } catch (err) {
    console.log(`  ✗ Runtime: ${err.message}`);
    runtimePath = null;
  }

  let modelPath;
  try {
    modelPath = await installModel();
  } catch (err) {
    console.log(`  ✗ Model: ${err.message}`);
    modelPath = null;
  }

  const projectRoot = join(__dirname, "..", "..");
  const frontendIndex = join(projectRoot, "frontend", "dist", "index.html");
  if (existsSync(frontendIndex)) {
    console.log("\n  ✓ Frontend ready");
  } else {
    console.log("\n  ⚠ Frontend not found — rebuild on dev machine: cd frontend && npm run build");
  }

  try {
    execSync("npm link", { cwd: projectRoot, stdio: "pipe" });
    console.log("  ✓ `ruach` command linked");
  } catch {
    console.log("  ⚠ Could not link `ruach` — use `npx ruach start` instead");
  }

  writeFileSync(join(RUACH_DIR, "config.json"), JSON.stringify({
    version: "0.5.0",
    runtime: runtimePath,
    model: modelPath,
    installed_at: new Date().toISOString(),
  }, null, 2));

  console.log("\n  ── Setup Complete ──────────────────────");
  if (runtimePath && modelPath) {
    console.log("  ✓ Everything installed. Run `ruach start` to begin.\n");
  } else {
    console.log("  ⚠ Partial install. Check errors above.\n");
  }

  return { runtime: runtimePath, model: modelPath };
}
