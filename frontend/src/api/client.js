const BASE = "/api";

function telegramInitData() {
  try {
    return window.Telegram?.WebApp?.initData || null;
  } catch {
    return null;
  }
}

async function request(path, options = {}) {
  const initData = telegramInitData();
  const headers = {
    ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(initData ? { "X-Telegram-Init-Data": initData } : {}),
  };

  const res = await fetch(`${BASE}${path}`, {
    headers,
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      // ignore
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return res.json();
  return res.text();
}

export const api = {
  get: (path) => request(path),
  put: (path, body) => request(path, { method: "PUT", body: JSON.stringify(body) }),
  post: (path, body) =>
    request(path, {
      method: "POST",
      body: body instanceof FormData ? body : JSON.stringify(body),
    }),
};

export default api;
