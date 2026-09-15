export function Loading() {
  return <div className="empty-state">Loading…</div>;
}

export function ErrorBanner({ message }) {
  if (!message) return null;
  return <div className="error-banner">{message}</div>;
}

export function EmptyState({ children }) {
  return <div className="empty-state">{children}</div>;
}
