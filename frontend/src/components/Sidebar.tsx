import { useEffect, useRef, useState } from "react";
import type { Conversation } from "../api";

export function Sidebar({
  conversations,
  activeId,
  open,
  onSelect,
  onNewChat,
}: {
  conversations: Conversation[];
  activeId: number | null;
  open: boolean;
  onSelect: (id: number) => void;
  onNewChat: () => void;
}) {
  return (
    <aside
      id="sidebar"
      className={`sidebar ${open ? "open" : ""}`}
      aria-label="Conversations"
    >
      <button type="button" id="new-chat" onClick={onNewChat}>
        + New Chat
      </button>
      <nav id="conversation-list" aria-label="Conversation history">
        {conversations.map((convo) => (
          <button
            key={convo.id}
            type="button"
            className={`conversation-item ${convo.id === activeId ? "active" : ""}`}
            onClick={() => onSelect(convo.id)}
          >
            {convo.title || "(untitled)"}
          </button>
        ))}
      </nav>
      <footer className="sidebar-footer">
        <span className="mono muted">
          runtime: local
          <br />
          privacy: on-device
        </span>
      </footer>
    </aside>
  );
}

export function Composer({
  sending,
  onSend,
}: {
  sending: boolean;
  onSend: (text: string) => void;
}) {
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const disabled = sending || !value.trim();

  useEffect(() => {
    if (!sending) inputRef.current?.focus();
  }, [sending]);

  function autosize() {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
  }

  function submit() {
    const text = value;
    setValue("");
    requestAnimationFrame(autosize);
    onSend(text);
  }

  return (
    <form
      id="composer"
      onSubmit={(event) => {
        event.preventDefault();
        if (!disabled) submit();
      }}
    >
      <textarea
        id="composer-input"
        ref={inputRef}
        rows={1}
        placeholder="Ask Ruach…"
        aria-label="Message"
        value={value}
        onChange={(event) => {
          setValue(event.target.value);
          autosize();
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (!disabled) submit();
          }
        }}
      />
      <button
        type="submit"
        id="send-btn"
        aria-label="Send"
        disabled={disabled}
      >
        ↑
      </button>
    </form>
  );
}
