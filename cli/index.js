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

const commands = { setup, start, doctor, help };

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
function start() {
  import("../src/server.js");
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

// ── Help ───────────────────────────────────────────────────
function help() {
  console.log(`
  RUACH AI — Local-First AI Workspace

  Usage:
    ruach setup    Install everything (runtime + model + frontend)
    ruach start    Start the server
    ruach doctor   Run diagnostics
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
