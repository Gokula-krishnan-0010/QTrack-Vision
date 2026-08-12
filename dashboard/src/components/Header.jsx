/**
 * Header — App title bar with shop selector and connection badge.
 */

import ConnectionBadge from "./ConnectionBadge";

export default function Header({ shopId, onShopChange, shops, connectionStatus }) {
  return (
    <header className="header" id="app-header">
      <div className="header-left">
        <div className="header-logo">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="32" height="32" rx="8" fill="url(#logo-gradient)" />
            <path d="M8 22V14L16 10L24 14V22L16 26L8 22Z" stroke="white" strokeWidth="1.5" fill="none" />
            <circle cx="16" cy="16" r="3" fill="white" opacity="0.8" />
            <circle cx="12" cy="20" r="1.5" fill="white" opacity="0.6" />
            <circle cx="20" cy="20" r="1.5" fill="white" opacity="0.6" />
            <defs>
              <linearGradient id="logo-gradient" x1="0" y1="0" x2="32" y2="32">
                <stop stopColor="#4f8cff" />
                <stop offset="1" stopColor="#7c3aed" />
              </linearGradient>
            </defs>
          </svg>
        </div>
        <div className="header-text">
          <h1>QTrack Vision</h1>
          <p className="header-subtitle">Real-time Queue Monitoring</p>
        </div>
      </div>

      <div className="header-right">
        <select
          className="shop-selector"
          id="shop-selector"
          value={shopId}
          onChange={(e) => onShopChange(e.target.value)}
        >
          {shops.length === 0 && <option value="">No shops found</option>}
          {shops.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <ConnectionBadge status={connectionStatus} />
      </div>
    </header>
  );
}
