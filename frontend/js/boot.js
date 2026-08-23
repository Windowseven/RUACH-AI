/* Boot experience — reflects REAL backend readiness (docs/09 §7: no fake progress). */

import { api } from "./api.js";

const checklist = document.getElementById("boot-checklist");
const statusLine = document.getElementById("boot-status");
const errorBox = document.getElementById("boot-error");
const errorTitle = document.getElementById("boot-error-title");
const errorDetail = document.getElementById("boot-error-detail");
const retryBtn = document.getElementById("boot-retry");

function setRow(name, state, label) {
  const row = checklist.querySelector(`[data-check="${name}"]`);
  if (!row) return;
  row.dataset.state = state;
  row.querySelector(".check-state").textContent = label;
}

export function boot(onReady) {
  let cancelled = false;

  async function attempt() {
    statusLine.textContent = "CONNECTING";
    setRow("core", "wait", "WAIT");

    try {
      const ready = await api.ready();
      if (cancelled) return;
      setRow("core", "ok", "READY");
      setRow("storage", ready.database === "available" ? "ok" : "bad", ready.database.toUpperCase());
      setRow(
        "inference",
        ready.inference === "available" ? "ok" : "bad",
        ready.inference.toUpperCase(),
      );

      if (ready.status === "ready") {
        statusLine.textContent = "INITIALIZING";
        setTimeout(() => {
          if (!cancelled) onReady();
        }, 450);
      } else {
        // DEGRADED (docs/09 §8): say exactly what is unavailable.
        statusLine.textContent = "DEGRADED";
        errorTitle.textContent = "UNABLE TO INITIALIZE";
        errorDetail.textContent =
          ready.inference !== "available"
            ? "The local inference runtime is unavailable. Start the model runtime, then retry."
            : "The local storage layer is unavailable. Retry or view diagnostics.";
        errorBox.hidden = false;
      }
    } catch (err) {
      if (cancelled) return;
      setRow("core", "bad", "DOWN");
      statusLine.textContent = "ERROR";
      errorTitle.textContent = "RUACH OFFLINE";
      errorDetail.textContent =
        err.code === "OFFLINE"
          ? "Cannot reach the local server at this address."
          : `Initialization failed: ${err.message}`;
      errorBox.hidden = false;
    }
  }

  retryBtn.addEventListener("click", () => {
    errorBox.hidden = true;
    attempt();
  });

  attempt();

  return () => {
    cancelled = true;
  };
}
