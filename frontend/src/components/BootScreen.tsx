/* Boot experience — reflects REAL backend readiness (docs/09 §7: no fake progress). */

import { useEffect, useState } from "react";
import { api, type ReadyInfo } from "../api";

type RowState = "wait" | "ok" | "bad";

interface Row {
  key: string;
  label: string;
  state: RowState;
  stateLabel: string;
  locked?: boolean;
}

const STATIC_ROWS = {
  tools: { key: "tools", label: "TOOLS", stateLabel: "LOCKED", locked: true },
  security: { key: "security", label: "SECURITY", stateLabel: "READY" },
} as const;

const INITIAL_ROWS: Row[] = [
  { key: "core", label: "CORE", state: "wait", stateLabel: "WAIT" },
  { key: "storage", label: "STORAGE", state: "wait", stateLabel: "WAIT" },
  { key: "inference", label: "INFERENCE", state: "wait", stateLabel: "WAIT" },
  { key: "tools", label: "TOOLS", state: "wait", stateLabel: "LOCKED" },
  { key: "security", label: "SECURITY", state: "wait", stateLabel: "READY" },
];

const STATE_TEXT: Record<RowState, string> = {
  wait: "text-ink-faint",
  ok: "text-ok",
  bad: "text-danger",
};

function setRow(rows: Row[], key: string, state: RowState, stateLabel: string): Row[] {
  return rows.map((row) => (row.key === key ? { ...row, state, stateLabel } : row));
}

export function BootScreen({ onReady }: { onReady: () => void }) {
  const [rows, setRows] = useState<Row[]>(INITIAL_ROWS);
  const [status, setStatus] = useState("CONNECTING");
  const [error, setError] = useState<{ title: string; detail: string } | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      setStatus("CONNECTING");
      setError(null);
      setRows((current) =>
        current.map((row) =>
          STATIC_ROWS.hasOwnProperty(row.key) ? row : { ...row, state: "wait", stateLabel: "WAIT" },
        ),
      );
      try {
        const ready: ReadyInfo = await api.ready();
        if (cancelled) return;
        setRows((current) =>
          setRow(
            setRow(
              current,
              "core",
              "ok",
              "READY",
            ),
            "storage",
            ready.database === "available" ? "ok" : "bad",
            ready.database.toUpperCase(),
          ),
        );
        setRows((current) =>
          setRow(
            current,
            "inference",
            ready.inference === "available" ? "ok" : "bad",
            ready.inference.toUpperCase(),
          ),
        );

        if (ready.status === "ready") {
          setStatus("INITIALIZING");
          setTimeout(() => {
            if (!cancelled) onReady();
          }, 450);
        } else {
          // DEGRADED (docs/09 §8): say exactly what is unavailable.
          setStatus("DEGRADED");
          setError({
            title: "UNABLE TO INITIALIZE",
            detail:
              ready.inference !== "available"
                ? "The local inference runtime is unavailable. Start the model runtime, then retry."
                : "The local storage layer is unavailable. Retry or view diagnostics.",
          });
        }
      } catch (err) {
        if (cancelled) return;
        const code = err instanceof Error && "code" in err ? String((err as { code: unknown }).code) : "";
        setRows((current) => setRow(current, "core", "bad", "DOWN"));
        setStatus("ERROR");
        setError({
          title: "RUACH OFFLINE",
          detail:
            code === "OFFLINE"
              ? "Cannot reach the local server at this address."
              : `Initialization failed: ${err instanceof Error ? err.message : String(err)}`,
        });
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [attempt, onReady]);

  return (
    <section
      id="boot-screen"
      aria-live="polite"
      className="fixed inset-0 z-50 flex items-center justify-center bg-background"
    >
      <div className="w-full max-w-xs px-6 text-center">
        <p
          className="mb-2 text-accent"
          style={{ fontFamily: "var(--font-display)", fontSize: 28, letterSpacing: "0.35em" }}
        >
          RUACH
        </p>
        <div className="mb-2 flex h-[34px] items-center justify-center">
          <span className="orb block h-3 w-3 rounded-full bg-accent" />
        </div>
        <p className="font-mono text-[11px] tracking-[0.3em] text-ink-muted">LOCAL INTELLIGENCE</p>
        <hr className="my-4 border-edge" />
        <ul id="boot-checklist" className="space-y-2 text-left">
          {rows.map((row) => (
            <li
              key={row.key}
              data-check={row.key}
              data-state={row.state}
              className="flex items-baseline gap-2 font-mono text-[11px]"
            >
              <span className="min-w-[72px] tracking-widest text-ink-muted">{row.label}</span>
              <span className="flex-1 border-b border-dotted border-edge" />
              <span className={STATE_TEXT[row.state]}>{row.stateLabel}</span>
            </li>
          ))}
        </ul>
        <hr className="my-4 border-edge" />
        <p id="boot-status" className="font-mono text-[11px] tracking-[0.25em] text-ink-faint">
          {status}
        </p>
        <div id="boot-error" hidden={!error}>
          <p id="boot-error-title" className="mt-4 font-mono text-xs tracking-widest text-danger">
            {error?.title ?? ""}
          </p>
          <p id="boot-error-detail" className="mt-1 text-sm text-ink-muted">
            {error?.detail ?? ""}
          </p>
          <div className="mt-3">
            <button
              type="button"
              id="boot-retry"
              onClick={() => setAttempt((n) => n + 1)}
              className="rounded-sm border border-edge-strong px-3 py-1.5 font-mono text-[11px] tracking-widest text-ink-muted hover:border-accent hover:text-accent"
            >
              RETRY
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
