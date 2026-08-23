import { useEffect, useRef, useState } from "react";
import { ApiError, type PendingApproval } from "../api";

export function ApprovalCard({
  pending,
  onDecide,
  onError,
}: {
  pending: PendingApproval;
  onDecide: (kind: "approve" | "deny", approvalId: string) => Promise<void>;
  onError: (message: string, offline: boolean) => void;
}) {
  const [settled, setSettled] = useState(false);
  const [settling, setSettling] = useState(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function decide(kind: "approve" | "deny") {
    if (settled || settling) return;
    setSettling(true);
    try {
      await onDecide(kind, pending.approval_id);
      if (!mounted.current) return;
      setSettled(true); // parent removes this card from the transcript
    } catch (err) {
      if (!mounted.current) return;
      setSettling(false);
      const code = err instanceof ApiError ? err.code : "UNKNOWN";
      onError(
        code === "OFFLINE"
          ? "The local server is unreachable. The action was not executed."
          : `Approval failed (${code}): ${err instanceof Error ? err.message : String(err)}`,
        code === "OFFLINE",
      );
    }
  }

  return (
    <section className={`approval-card ${settling ? "settling" : ""}`}>
      <header>
        <div className="approval-title">APPROVAL REQUIRED</div>
        <div className="approval-capability">{pending.capability}</div>
        <code className="approval-args">{JSON.stringify(pending.arguments)}</code>
      </header>
      <div className="approval-actions">
        <button
          type="button"
          className="btn-deny"
          disabled={settled || settling}
          onClick={() => void decide("deny")}
        >
          DENY
        </button>
        <button
          type="button"
          className="btn-approve"
          disabled={settled || settling}
          onClick={() => void decide("approve")}
        >
          APPROVE
        </button>
      </div>
    </section>
  );
}
