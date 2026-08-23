/* API boundary — envelope-aware fetch wrapper (docs/09 §76). */

const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(code, message, requestId) {
    super(message);
    this.code = code;
    this.requestId = requestId;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(BASE + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    throw new ApiError("OFFLINE", "The local server is unreachable.", null);
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  if (!response.ok) {
    const err = body && body.error ? body.error : {};
    throw new ApiError(
      err.code || `HTTP_${response.status}`,
      err.message || "Request failed.",
      body ? body.request_id : null,
    );
  }
  return body ? body.data : null;
}

export const api = {
  ready: () => request("/ready"),
  system: () => request("/system"),
  conversations: () => request("/conversations"),
  conversationDetail: (id) => request(`/conversations/${id}`),
  send: (conversationId, message, maxTokens = 512) =>
    request("/chat", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: conversationId,
        message,
      }),
    }),
  approveTool: (approvalId) =>
    request(`/chat/approvals/${encodeURIComponent(approvalId)}/approve`, {
      method: "POST",
      body: JSON.stringify({ approved: true }),
    }),
  rejectTool: (approvalId) =>
    request(`/chat/approvals/${encodeURIComponent(approvalId)}/reject`, {
      method: "POST",
    }),
};
