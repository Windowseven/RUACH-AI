import { useEffect, useRef } from "react";
import type { PendingApproval } from "../api";
import { ApprovalCard } from "./ApprovalCard";

export type Entry =
  | { kind: "message"; role: "user" | "assistant" | "error"; content: string }
  | { kind: "thinking" }
  | { kind: "tool"; capability: string; state: string }
  | { kind: "approval"; pending: PendingApproval };

const WHO: Record<"user" | "assistant" | "error", string> = {
  user: "YOU",
  assistant: "RUACH",
  error: "SYSTEM",
};

export function MessageList({
  entries,
  onDecideApproval,
}: {
  entries: Entry[];
  onDecideApproval: (kind: "approve" | "deny", approvalId: string) => Promise<void>;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries]);

  return (
    <div id="messages" aria-live="polite" className="messages-scroll" ref={ref}>
      {entries.length === 0 && <EmptyState />}
      {entries.map((entry, index) => {
        switch (entry.kind) {
          case "message":
            return (
              <article key={index} className={`message ${entry.role}`}>
                <div className="message-head">
                  {entry.role === "assistant" && <span className="state-glyph">◉</span>}
                  <span className="who">{WHO[entry.role]}</span>
                </div>
                <div className="body">{entry.content}</div>
              </article>
            );
          case "thinking":
            return (
              <article key={index} className="message assistant state-thinking">
                <div className="message-head">
                  <span className="state-glyph">◉</span>
                  <span className="who">RUACH</span>
                </div>
                <div className="body">…</div>
              </article>
            );
          case "tool":
            return (
              <div key={index} className={`tool-activity tool-${entry.state.toLowerCase()}`}>
                TOOL {entry.capability} — {entry.state}
              </div>
            );
          case "approval":
            return (
              <ApprovalCard
                key={index}
                pending={entry.pending}
                onDecide={onDecideApproval}
                onError={(message, offline) => {
                  // Error text renders as a transcript line, exactly like the
                  // legacy implementation; offline also flips the badge.
                  window.dispatchEvent(
                    new CustomEvent("ruach:transcript-error", { detail: message }),
                  );
                  if (offline) window.dispatchEvent(new CustomEvent("ruach:offline"));
                }}
              />
            );
        }
      })}
    </div>
  );
}

function EmptyState() {
  return (
    <div id="empty-state">
      <p
        className="empty-mark text-accent"
        style={{ fontFamily: "var(--font-display)", letterSpacing: "0.3em" }}
      >
        RUACH
      </p>
      <p className="empty-question">What are we working on?</p>
      <div className="empty-suggestions font-mono" aria-hidden="true">
        <span>explore my files</span>
        <span>explain something</span>
        <span>help me build</span>
      </div>
    </div>
  );
}
