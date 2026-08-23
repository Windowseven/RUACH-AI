/* Typed API boundary — envelope-aware (docs/06 §error-envelope, docs/09 §76). */

const BASE = "/api/v1";

export class ApiError extends Error {
  code: string;
  requestId: string | null;
  constructor(code: string, message: string, requestId: string | null) {
    super(message);
    this.code = code;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError("OFFLINE", "The local server is unreachable.", null);
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const err =
      body && typeof body === "object" && "error" in body
        ? (body as { error?: { code?: string; message?: string } }).error
        : {};
    throw new ApiError(
      err?.code ?? `HTTP_${response.status}`,
      err?.message ?? "Request failed.",
      body && typeof body === "object" && "request_id" in body
        ? String((body as { request_id: unknown }).request_id)
        : null,
    );
  }
  return (body as { data: T }).data;
}

export interface ReadyInfo {
  status: string;
  database: string;
  inference: string;
}

export interface Conversation {
  id: number;
  title: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant" | "tool" | "system";
  content: string;
}

export interface ToolEvent {
  capability: string;
  state: string;
}

export interface PendingApproval {
  approval_id: string;
  capability: string;
  arguments: Record<string, unknown>;
}

export interface ChatResult {
  conversation_id: number;
  content: string;
  tool?: ToolEvent;
  pending_approval?: PendingApproval;
}

export interface ConversationDetail {
  messages: ChatMessage[];
}

export interface ApprovalOutcome {
  content: string;
  tool?: ToolEvent;
}

export const api = {
  ready: () => request<ReadyInfo>("/ready"),
  conversations: () => request<Conversation[]>("/conversations"),
  conversationDetail: (id: number) => request<ConversationDetail>(`/conversations/${id}`),
  send: (conversationId: number | null, message: string) =>
    request<ChatResult>("/chat", {
      method: "POST",
      body: JSON.stringify({ conversation_id: conversationId, message }),
    }),
  approveTool: (approvalId: string) =>
    request<ApprovalOutcome>(
      `/chat/approvals/${encodeURIComponent(approvalId)}/approve`,
      { method: "POST", body: JSON.stringify({ approved: true }) },
    ),
  rejectTool: (approvalId: string) =>
    request<ApprovalOutcome>(
      `/chat/approvals/${encodeURIComponent(approvalId)}/reject`,
      { method: "POST" },
    ),
};
