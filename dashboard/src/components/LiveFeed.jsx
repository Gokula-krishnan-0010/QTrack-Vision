/**
 * LiveFeed — Displays the latest annotated camera frame from the server.
 * Updates automatically when new SSE data arrives.
 */

import { useState, useEffect } from "react";

const API_BASE = "http://localhost:8000";

export default function LiveFeed({ data }) {
  const [imgSrc, setImgSrc] = useState(null);
  const [isNew, setIsNew] = useState(false);

  useEffect(() => {
    if (data?.annotated_frame_url) {
      // Add cache-busting timestamp
      setImgSrc(`${API_BASE}${data.annotated_frame_url}?t=${Date.now()}`);

      // Trigger pulse animation
      setIsNew(true);
      const timer = setTimeout(() => setIsNew(false), 800);
      return () => clearTimeout(timer);
    }
  }, [data?.timestamp]);

  return (
    <div className={`live-feed ${isNew ? "live-feed--pulse" : ""}`} id="live-feed">
      <div className="live-feed-header">
        <span className="live-feed-title">📹 Camera Feed</span>
        {data?.timestamp && (
          <span className="live-feed-time">
            {new Date(data.timestamp).toLocaleTimeString()}
          </span>
        )}
      </div>
      <div className="live-feed-frame">
        {imgSrc ? (
          <img
            src={imgSrc}
            alt="Latest annotated camera frame"
            className="live-feed-img"
            onError={() => setImgSrc(null)}
          />
        ) : (
          <div className="live-feed-placeholder">
            <div className="placeholder-icon">📷</div>
            <p>Waiting for camera feed...</p>
            <p className="placeholder-hint">
              Frames will appear once the ESP32-CAM starts transmitting
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
