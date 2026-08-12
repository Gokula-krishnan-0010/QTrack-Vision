/**
 * QueueStats — Four animated metric cards showing live queue analytics.
 */

import { useEffect, useRef, useState } from "react";

function AnimatedNumber({ value, suffix = "", decimals = 0 }) {
  const [display, setDisplay] = useState(0);
  const animRef = useRef(null);

  useEffect(() => {
    const start = display;
    const end = value;
    const duration = 600;
    const startTime = performance.now();

    const animate = (now) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplay(start + (end - start) * eased);

      if (progress < 1) {
        animRef.current = requestAnimationFrame(animate);
      }
    };

    animRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animRef.current);
  }, [value]);

  return (
    <span className="stat-value">
      {display.toFixed(decimals)}{suffix}
    </span>
  );
}

const CARDS = [
  {
    key: "person_count",
    label: "Persons Detected",
    icon: "👥",
    suffix: "",
    decimals: 0,
    color: "#4f8cff",
  },
  {
    key: "queue_length",
    label: "Queue Length",
    icon: "📊",
    suffix: "",
    decimals: 0,
    color: "#7c3aed",
  },
  {
    key: "avg_wait_sec",
    label: "Est. Wait Time",
    icon: "⏱️",
    suffix: "s",
    decimals: 1,
    color: "#f59e0b",
  },
  {
    key: "exit_rate",
    label: "Exit Rate",
    icon: "🚪",
    suffix: "",
    decimals: 3,
    color: "#10b981",
  },
];

export default function QueueStats({ data }) {
  return (
    <div className="stats-grid" id="queue-stats">
      {CARDS.map((card) => {
        const val = data?.[card.key] ?? 0;
        return (
          <div
            className={`stat-card ${data ? "stat-card--active" : ""}`}
            key={card.key}
            id={`stat-${card.key}`}
            style={{ "--card-accent": card.color }}
          >
            <div className="stat-icon">{card.icon}</div>
            <div className="stat-info">
              <AnimatedNumber value={val} suffix={card.suffix} decimals={card.decimals} />
              <span className="stat-label">{card.label}</span>
            </div>
            <div className="stat-glow" />
          </div>
        );
      })}
    </div>
  );
}
