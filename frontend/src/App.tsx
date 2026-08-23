import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type ApprovalOutcome, type Conversation } from "./api";
import { BootScreen } from "./components/BootScreen";
import { MessageList, type Entry } from "./components/MessageList";
import { Composer, Sidebar } from "./components/Sidebar";

type Connection = "connecting" | "connected" | "disconnected";

export function App() {
  const [booted, setBooted] = useState(false);
  const [bootGone, setBootGone] = useState(false);
  const [connection, setConnection] = useState<Connection>("connecting");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [sending, setSending] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations(await api.conversations());
    } catch (err) {
      if (err instanceof ApiError && err.code === "OFFLINE") setConnection("disconnected");
    }
  }, []);

  const handleReady = useCallback(() => {
    setConnection("connected");
    setBooted(true);
    setTimeout(() => setBootGone(true), 250);
    void refreshConversations();
  }, [refreshConversations]);

  /* Transcript error lines coming from approval cards (offline etc.). */
  useEffect(() => {
    const onError = (event: Event) => {
      setEntries((current) => [
        ...current,
        { kind: "message", role: "error", content: (event as CustomEvent<string>).detail },
      ]);
    };
    const onOffline = () => setConnection("disconnected");
    window.addEventListener("ruach:transcript-error", onError);
    window.addEventListener("ruach:offline", onOffline);
    return () => {
      window.removeEventListener("ruach:transcript-error", onError);
      window.removeEventListener("ruach:offline", onOffline);
    };
  }, []);

  /* Escape closes the drawer, matching the legacy behavior. */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const selectConversation = useCallback(
    async (id: number) => {
      setActiveId(id);
      try {
        const detail = await api.conversationDetail(id);
        const loaded: Entry[] = [];
        for (const msg of detail.messages) {
          if (msg.role === "tool") {
            try {
              const event = JSON.parse(msg.content) as { capability?: string; state?: string };
              loaded.push({
                kind: "tool",
                capability: event.capability || "unknown",
                state: event.state || "?",
              });
            } catch {
              loaded.push({ kind: "tool", capability: "unknown", state: "LOGGED" });
            }
          } else {
            loaded.push({
              kind: "message",
              role: msg.role === "user" ? "user" : "assistant",
              content: msg.content,
            });
          }
        }
        setEntries(loaded);
        setDrawerOpen(false);
      } catch (err) {
        if (err instanceof ApiError && err.code === "OFFLINE") setConnection("disconnected");
      }
    },
    [],
  );

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || sending) return;
      setSending(true);
      let conversationIdAtSend = activeId;

      setEntries((current) => [
        ...current,
        { kind: "message", role: "user", content: text },
        { kind: "thinking" },
      ]);

      try {
        const result = await api.send(conversationIdAtSend, text.trim());
        setEntries((current) => {
          const withoutThinking = current.filter((entry) => entry.kind !== "thinking");
          const next: Entry[] = [...withoutThinking];
          if (result.tool) {
            next.push({ kind: "tool", capability: result.tool.capability, state: result.tool.state });
          }
          next.push({ kind: "message", role: "assistant", content: result.content });
          if (result.pending_approval) {
            next.push({ kind: "approval", pending: result.pending_approval });
          }
          return next;
        });
        if (!conversationIdAtSend) {
          conversationIdAtSend = result.conversation_id;
          setActiveId(result.conversation_id);
        }
        await refreshConversations();
      } catch (err) {
        setEntries((current) => [
          ...current.filter((entry) => entry.kind !== "thinking"),
          {
            kind: "message",
            role: "error",
            content:
              err instanceof ApiError && err.code === "OFFLINE"
                ? "The local server is unreachable. Your message was not delivered."
                : `Inference error (${err instanceof ApiError ? err.code : "UNKNOWN"}): ${
                    err instanceof Error ? err.message : String(err)
                  }`,
          },
        ]);
        if (err instanceof ApiError && err.code === "OFFLINE") setConnection("disconnected");
      } finally {
        setSending(false);
      }
    },
    [activeId, sending, refreshConversations],
  );

  const decideApproval = useCallback(
    async (kind: "approve" | "deny", approvalId: string): Promise<void> => {
      const result: ApprovalOutcome =
        kind === "approve" ? await api.approveTool(approvalId) : await api.rejectTool(approvalId);

      // Success: the parent transcript replaces the card with the outcome.
      setEntries((current) =>
        current.flatMap((entry) => {
          if (!(entry.kind === "approval" && entry.pending.approval_id === approvalId)) {
            return [entry];
          }
          const replacement: Entry[] = [];
          if (result.tool) {
            replacement.push({
              kind: "tool",
              capability: result.tool.capability,
              state: result.tool.state,
            });
          }
          replacement.push({ kind: "message", role: "assistant", content: result.content });
          return replacement;
        }),
      );
      await refreshConversations();
    },
    [refreshConversations],
  );

  function resetToNewChat() {
    setActiveId(null);
    setEntries([]);
    setDrawerOpen(false);
    document.getElementById("composer-input")?.focus();
  }

  if (!bootGone) {
    return <BootScreen onReady={handleReady} />;
  }

  return (
    <main id="workspace" className={`workspace ${booted ? "visible" : ""}`}>
      <header className="topbar">
        <button
          type="button"
          id="drawer-toggle"
          aria-label="Open menu"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen((open) => !open)}
        >
          ☰
        </button>
        <span className="topbar-mark">RUACH</span>
        <span id="connection-badge" title="Local backend connection">
          <span className={`dot ${connection === "connected" ? "dot-ok" : ""}`} aria-hidden="true" />
          LOCAL
        </span>
      </header>

      <div className="body-row">
        <Sidebar
          conversations={conversations}
          activeId={activeId}
          open={drawerOpen}
          onSelect={(id) => void selectConversation(id)}
          onNewChat={resetToNewChat}
        />
        <div
          id="drawer-backdrop"
          hidden={!drawerOpen}
          onClick={() => setDrawerOpen(false)}
        />

        <section className="chat-column">
          <MessageList entries={entries} onDecideApproval={decideApproval} />
          <Composer sending={sending} onSend={(text) => void sendMessage(text)} />
        </section>
      </div>

      <div id="offline-banner" hidden={connection !== "disconnected"}>
        RUACH OFFLINE — the local server is unreachable.{" "}
        <button type="button" id="reconnect-btn" onClick={() => location.reload()}>
          RECONNECT
        </button>
      </div>
    </main>
  );
}

export default App;
