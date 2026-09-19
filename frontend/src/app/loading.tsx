export default function Loading() {
  return (
    <div className="card" aria-busy="true" aria-live="polite">
      <div className="empty-state">
        <p className="muted">Loading…</p>
      </div>
    </div>
  );
}
