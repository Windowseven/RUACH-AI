#!/usr/bin/env node

import { existsSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { homedir, arch, platform, cpus, totalmem, freemem } from "os";
import { execSync } from "child_process";
import { fullSetup, installRuntime, installModel } from "../src/setup/download.js";

const args = process.argv.slice(2);
const command = args[0] || "help";

const RUACH_DIR = join(homedir(), ".ruach");
const RUNTIME_DIR = join(RUACH_DIR, "runtime");
const MODELS_DIR = join(RUACH_DIR, "models");

const commands = { setup, start, doctor, test, help };

if (commands[command]) {
  commands[command]();
} else {
  console.error(`Unknown command: ${command}`);
  help();
  process.exit(1);
}

// ── Setup: everything in one command ───────────────────────
async function setup() {
  await fullSetup();
}

// ── Start: launch server + llama.cpp ───────────────────────
async function start() {
  await import("../src/server.js");
}

// ── Doctor: health check ───────────────────────────────────
async function doctor() {
  console.log("\n  RUACH Doctor\n");

  const checks = [];

  // Node.js
  const nodeVersion = process.version;
  const nodeOk = parseInt(nodeVersion.slice(1)) >= 18;
  checks.push({ name: "Node.js", ok: nodeOk, detail: `v${nodeVersion.slice(1)}` });

  // Device
  const device = detectDevice();
  checks.push({ name: "Device", ok: true, detail: `${device.platform} ${device.arch} (${device.ram_mb} MB RAM)` });

  // Runtime
  const bin = platform() === "win32" ? "llama-server.exe" : "llama-server";
  const runtimePath = findFile(RUNTIME_DIR, bin);
  checks.push({
    name: "Runtime",
    ok: !!runtimePath,
    detail: runtimePath ? "installed" : "missing — run `ruach setup`",
  });

  // Model
  const modelPath = findFile(MODELS_DIR, ".gguf");
  checks.push({
    name: "Model",
    ok: !!modelPath,
    detail: modelPath ? "installed" : "missing — run `ruach setup`",
  });

  // LLM server
  const llmRunning = await checkPort(8080);
  checks.push({
    name: "LLM server",
    ok: llmRunning,
    detail: llmRunning ? "running on :8080" : "not running",
  });

  // Print
  for (const c of checks) {
    console.log(`  ${c.ok ? "✓" : "✗"} ${c.name}: ${c.detail}`);
  }

  const allOk = checks.every((c) => c.ok);
  console.log(allOk
    ? "\n  All checks passed. Run `ruach start`.\n"
    : "\n  Some checks failed. Run `ruach setup`.\n");
}

// ── Test: try to start llama-server and report results ──────
async function test() {
  console.log("\n  RUACH LLM Test\n");

  // 1. Find binary
  const bin = platform() === "win32" ? "llama-server.exe" : "llama-server";
  const serverPath = findFile(RUNTIME_DIR, bin);
  console.log(`  Binary: ${serverPath || "NOT FOUND"}`);
  if (!serverPath) {
    console.log("  ✗ Cannot test — binary missing. Run `ruach setup`.\n");
    process.exit(1);
  }

  // 2. Check file type
  try {
    const info = execSync(`file "${serverPath}"`, { encoding: "utf8" }).trim();
    console.log(`  Type: ${info}`);
  } catch {}

  // 3. Check permissions
  try {
    const perms = execSync(`ls -la "${serverPath}"`, { encoding: "utf8" }).trim();
    console.log(`  Perms: ${perms}`);
  } catch {}

  // 4. Set up env with LD_LIBRARY_PATH
  const binDir = serverPath.replace(/\/[^/]+$/, "");
  const env = {
    ...process.env,
    LD_LIBRARY_PATH: binDir + (process.env.LD_LIBRARY_PATH ? ":" + process.env.LD_LIBRARY_PATH : ""),
    OMP_NUM_THREADS: "1",
  };

  // 5. Try --version
  console.log("\n  Testing --version...");
  try {
    const result = execSync(`"${serverPath}" --version 2>&1`, {
      encoding: "utf8",
      timeout: 5000,
      env,
      stdio: "pipe",
    });
    console.log(`  ✓ ${result.trim().split("\n")[0]}`);
  } catch (err) {
    const output = (err.stdout || err.stderr || "").toString().trim();
    if (output) {
      console.log(`  Output: ${output.split("\n")[0]}`);
    }
    console.log(`  ✗ --version failed: ${err.status !== null ? `exit code ${err.status}` : err.message}`);
  }

  // 6. Find model
  const modelPath = findFile(MODELS_DIR, ".gguf");
  console.log(`\n  Model: ${modelPath || "NOT FOUND"}`);
  if (!modelPath) {
    console.log("  ✗ Cannot test inference — model missing.\n");
    process.exit(1);
  }

  // 7. Try to start llama-server with model using Node.js spawn (no timeout cmd needed)
  console.log("\n  Starting llama-server with model (10s test)...");
  const { spawn } = await import("child_process");
  await new Promise((resolve) => {
    let output = "";
    let listening = false;

    const proc = spawn(serverPath, [
      "--model", modelPath,
      "--host", "127.0.0.1",
      "--port", "18080",
      "--ctx-size", "512",
      "--threads", "1",
    ], { env, stdio: ["ignore", "pipe", "pipe"] });

    const onLine = (data) => {
      const text = data.toString();
      output += text;
      if (!listening && text.includes("listening")) {
        listening = true;
        console.log(`  ✓ Listening detected!`);
      }
    };

    proc.stdout.on("data", onLine);
    proc.stderr.on("data", onLine);

    proc.on("error", (err) => {
      console.log(`  ✗ Spawn error: ${err.message}`);
      resolve();
    });

    proc.on("exit", (code) => {
      if (!listening) {
        console.log(`  ✗ Exited with code ${code} before listening`);
      }
      resolve();
    });

    // Kill after 10s
    setTimeout(() => {
      proc.kill("SIGTERM");
      if (!listening) {
        console.log(`  ✗ Did not detect "listening" within 10s`);
      }
      console.log(`\n  Last 15 lines of output:`);
      const lines = output.trim().split("\n");
      for (const line of lines.slice(-15)) {
        console.log(`    ${line}`);
      }
      resolve();
    }, 10000);
  });

  console.log("");
}

// ── Help ───────────────────────────────────────────────────
function help() {
  console.log(`
  RUACH AI — Local-First AI Workspace

  Usage:
    ruach setup    Install everything (runtime + model + frontend)
    ruach start    Start the server
    ruach doctor   Run diagnostics
    ruach test     Test if llama-server binary works
    ruach help     Show this message

  Quick start:
    git clone <repo>
    cd ruach
    npm install
    ruach start
  `);
}

// ── Helpers ────────────────────────────────────────────────
function detectDevice() {
  let realArch = arch();
  try {
    const uname = execSync("uname -m", { encoding: "utf8" }).trim().toLowerCase();
    if (uname === "armv7l" || uname === "armv6l") realArch = "arm";
    else if (uname === "aarch64" || uname === "arm64") realArch = "arm64";
    else if (uname === "x86_64" || uname === "amd64") realArch = "x64";
  } catch {}
  return {
    platform: platform(),
    arch: realArch,
    nodeArch: arch(),
    cpus: cpus().length,
    ram_mb: Math.round(totalmem() / 1024 / 1024),
    free_ram_mb: Math.round(freemem() / 1024 / 1024),
  };
}

function findFile(dir, nameOrExt) {
  if (!existsSync(dir)) return null;
  try {
    const entries = readdirSync(dir);
    for (const e of entries) {
      const full = join(dir, e);
      if (statSync(full).isDirectory()) {
        const found = findFile(full, nameOrExt);
        if (found) return found;
      } else if (e === nameOrExt || (nameOrExt.startsWith(".") && e.endsWith(nameOrExt))) {
        return full;
      }
    }
  } catch {}
  return null;
}

async function checkPort(port) {
  try {
    const net = await import("net");
    return new Promise((resolve) => {
      const server = net.createServer();
      server.once("error", () => resolve(true));
      server.once("listening", () => { server.close(); resolve(false); });
      server.listen(port);
    });
  } catch {
    return false;
  }
}
