/**
 * ConnectionBadge — Visual indicator for SSE connection status.
 * Shows a pulsing dot with status text: Live / Connecting / Offline.
 */

export default function ConnectionBadge({ status }) {
  const config = {
    connected: { label: "Live", className: "badge--live" },
    connecting: { label: "Connecting", className: "badge--connecting" },
    disconnected: { label: "Offline", className: "badge--offline" },
  };

  const { label, className } = config[status] || config.disconnected;

  return (
    <div className={`connection-badge ${className}`} id="connection-badge">
      <span className="badge-dot" />
      <span className="badge-label">{label}</span>
    </div>
  );
}
