import { existsSync, mkdirSync, createWriteStream, chmodSync, readFileSync } from "fs";
import { join, dirname } from "path";
import { homedir, arch, platform } from "os";
import { pipeline } from "stream/promises";
import { execSync } from "child_process";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const RUACH_DIR = join(homedir(), ".ruach");
const RUNTIME_DIR = join(RUACH_DIR, "runtime");
const MODELS_DIR = join(RUACH_DIR, "models");

const RELEASES_BASE = "https://github.com/Windowseven/RUACH-AI/releases/download";

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

  const curlOk = await downloadWithCurl(url, dest);
  if (curlOk) {
    if (platform() !== "win32") chmodSync(dest, 0o755);
    console.log(`  ✓ ${label} installed`);
    return true;
  }

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
    execSync(`curl -fSL --connect-timeout 15 --max-time 300 -o "${dest}" "${url}"`, {
      stdio: "pipe",
      timeout: 310000,
    });
    return true;
  } catch {
    return false;
  }
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

// ── Build llama.cpp from source on device ──────────────────
async function buildFromSource(destDir, bin) {
  console.log("\n  Building llama.cpp from source...");

  // Check build tools
  const deps = isTermux() ? ["git", "cmake", "clang"] : ["git", "cmake", "g++"];
  const missing = [];
  for (const dep of deps) {
    try {
      execSync(`which ${dep}`, { stdio: "pipe" });
    } catch {
      missing.push(dep);
    }
  }

  if (missing.length > 0) {
    console.log(`  Installing: ${missing.join(", ")}...`);
    try {
      if (isTermux()) {
        execSync(`pkg install -y ${missing.join(" ")}`, { stdio: "inherit", timeout: 180000 });
      } else {
        execSync(`sudo apt-get install -y ${missing.join(" ")}`, { stdio: "inherit", timeout: 180000 });
      }
    } catch {
      throw new Error(
        `Failed to install build tools. Run manually:\n` +
        `  ${isTermux() ? "pkg" : "sudo apt-get install"} ${missing.join(" ")}`
      );
    }
  }

  const buildDir = join(RUACH_DIR, "build-src");
  mkdirSync(buildDir, { recursive: true });

  try {
    console.log("  Cloning llama.cpp...");
    const cloneDir = join(buildDir, "llama.cpp");
    if (existsSync(cloneDir)) {
      try { execSync("git pull", { cwd: cloneDir, stdio: "pipe", timeout: 60000 }); } catch {}
    } else {
      // Retry clone up to 3 times (slow connections on mobile)
      for (let attempt = 1; attempt <= 3; attempt++) {
        try {
          execSync("git clone --depth 1 --branch b10622 https://github.com/ggml-org/llama.cpp.git", {
            cwd: buildDir,
            stdio: "pipe",
            timeout: 300000,
          });
          break;
        } catch (err) {
          console.log(`    Clone attempt ${attempt}/3 failed: ${err.message}`);
          if (attempt === 3) throw err;
          await new Promise((r) => setTimeout(r, 3000));
        }
      }
    }

    const srcDir = join(buildDir, "llama.cpp");
    console.log("  Configuring...");
    execSync(
      `cmake -B build -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF -DGGML_NATIVE=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF`,
      { cwd: srcDir, stdio: "pipe", timeout: 120000 }
    );

    let threads = 2;
    try {
      threads = Math.max(1, parseInt(execSync("nproc", { encoding: "utf8" }).trim(), 10) || 2);
    } catch {
      try {
        threads = Math.max(1, parseInt(execSync("grep -c ^processor /proc/cpuinfo", { encoding: "utf8" }).trim(), 10) || 2);
      } catch {
        threads = 2;
      }
    }
    console.log(`  Building (${threads} threads, may take 10+ minutes on mobile)...`);
    execSync(`cmake --build build --config Release -j${threads}`, {
      cwd: srcDir,
      stdio: "pipe",
      timeout: 1200000,
    });

    const builtBin = join(srcDir, "build", "bin", bin);
    if (!existsSync(builtBin)) {
      throw new Error("Build succeeded but binary not found");
    }

    mkdirSync(destDir, { recursive: true });
    const destBin = join(destDir, bin);

    // Copy binary
    const { copyFileSync } = await import("fs");
    copyFileSync(builtBin, destBin);
    chmodSync(destBin, 0o755);

    // Copy shared libs if any
    const buildBinDir = join(srcDir, "build", "bin");
    try {
      const { readdirSync, copyFileSync: cf } = await import("fs");
      for (const f of readdirSync(buildBinDir)) {
        if (f.startsWith("lib") && f.endsWith(".so")) {
          cf(join(buildBinDir, f), join(destDir, f));
        }
      }
    } catch {}

    console.log("  ✓ Built from source successfully");
    return destBin;
  } finally {
    // Clean up build dir
    try {
      execSync(`rm -rf "${buildDir}"`, { stdio: "pipe" });
    } catch {}
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
    console.log(`  ⚠ Existing binary incompatible`);
  }

  // On Termux: always build from source (cross-compiled binaries don't work)
  if (isTermux()) {
    console.log(`\n  Building runtime from source for Termux...`);
    try {
      return await buildFromSource(destDir, bin);
    } catch (err) {
      console.log(`  ✗ Build failed: ${err.message}`);
      throw new Error(
        `Could not build llama.cpp on Termux.\n` +
        `Try manually:\n` +
        `  pkg install git cmake clang\n` +
        `  cd /tmp && git clone --depth 1 --branch b10622 https://github.com/ggml-org/llama.cpp.git\n` +
        `  cd llama.cpp && cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build -j$(nproc)\n` +
        `  cp build/bin/llama-server ~/.ruach/runtime/${archLabel}/`
      );
    }
  }

  // Non-Termux: try pre-built binary
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

      const { readdirSync, statSync, renameSync, rmSync } = await import("fs");
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

      try { (await import("fs")).unlinkSync(tarDest); } catch {}
    } catch (err) {
      console.log(`  ✗ Extraction failed: ${err.message}`);
    }
  }

  if (existsSync(dest) && testBinary(dest)) {
    console.log(`  ✓ Runtime verified (${archLabel})`);
    return dest;
  }

  throw new Error(`Runtime doesn't work. Run \`ruach setup\` to rebuild.`);
}

// ── Install model ──────────────────────────────────────────
export async function installModel() {
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
    const { execSync } = await import("child_process");
    execSync("npm link", { cwd: projectRoot, stdio: "pipe" });
    console.log("  ✓ `ruach` command linked");
  } catch {
    console.log("  ⚠ Could not link `ruach` — use `npx ruach start` instead");
  }

  const { writeFileSync } = await import("fs");
  const config = {
    version: "0.5.0",
    runtime: runtimePath,
    model: modelPath,
    installed_at: new Date().toISOString(),
  };
  writeFileSync(join(RUACH_DIR, "config.json"), JSON.stringify(config, null, 2));

  console.log("\n  ── Setup Complete ──────────────────────");
  if (runtimePath && modelPath) {
    console.log("  ✓ Everything installed. Run `ruach start` to begin.\n");
  } else {
    console.log("  ⚠ Partial install. Check errors above.\n");
  }

  return { runtime: runtimePath, model: modelPath };
}
