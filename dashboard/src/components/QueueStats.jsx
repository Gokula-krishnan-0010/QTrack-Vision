/** Live queue metrics and the ByteTrack IDs detected in the latest frame. */
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

export default function QueueStats({ data }) {
  const update = data?.queue_update ?? data;
  const movementReady = data?.movement_configured === true;
  const roiReady = data?.queue_roi_configured === true;
  const cards = [
    { key: "queue_length", label: roiReady ? "People in queue" : "People detected · ROI unset", value: data?.queue_length, suffix: "", decimals: 0, color: "#7c3aed" },
    { key: "avg_wait_sec", label: "Est. avg. remaining wait", value: data?.avg_wait_sec, suffix: "s", decimals: 1, color: "#f59e0b" },
    { key: "advanced_person_count", label: movementReady ? "Moved forward" : "Movement · set direction", value: movementReady ? update?.advanced_person_count : null, suffix: "", decimals: 0, color: "#10b981" },
    { key: "queue_count_delta", label: "Queue change", value: update?.queue_count_delta, suffix: "", decimals: 0, color: "#4f8cff" },
    { key: "entered_queue_count", label: "Entered queue", value: update?.entered_queue_count, suffix: "", decimals: 0, color: "#06b6d4" },
    { key: "exited_queue_count", label: "Left queue", value: update?.exited_queue_count, suffix: "", decimals: 0, color: "#f43f5e" },
  ];
  const trackedPeople = data?.tracked_people ?? [];
  const ids = trackedPeople.filter((person) => person.tracker_id != null);

  return (
    <div className="queue-analytics" id="queue-stats">
      <div className="stats-grid">
        {cards.map((card) => (
          <div
            className={`stat-card ${data ? "stat-card--active" : ""}`}
            key={card.key}
            id={`stat-${card.key}`}
            style={{ "--card-accent": card.color }}
          >
            <div className="stat-info">
              {card.value == null ? (
                <span className="stat-value stat-value--empty">—</span>
              ) : (
                <AnimatedNumber value={Number(card.value)} suffix={card.suffix} decimals={card.decimals} />
              )}
              <span className="stat-label">{card.label}</span>
            </div>
            <div className="stat-glow" />
          </div>
        ))}
      </div>

      <section className="tracker-panel" aria-live="polite">
        <div className="tracker-panel-heading">
          <div>
            <h3>ByteTrack people IDs</h3>
            <p>IDs are assigned per camera tracking session.</p>
          </div>
          <span className="tracker-count">{ids.length} tracked</span>
        </div>
        {ids.length ? (
          <div className="tracker-list">
            {ids.map((person) => (
              <div className="tracker-person" key={person.tracker_id}>
                <strong>#{person.tracker_id}</strong>
                <span className={person.in_queue && roiReady ? "tracker-state tracker-state--queue" : "tracker-state"}>
                  {!roiReady ? "ROI unset" : person.in_queue ? "In queue" : "Outside queue"}
                </span>
                <span className="tracker-confidence">{Math.round((person.confidence ?? 0) * 100)}% confidence</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="tracker-empty">
            {data ? "No ByteTrack IDs were assigned in the latest frame." : "Waiting for the first processed frame…"}
          </p>
        )}
        <p className="analytics-note">
          {!roiReady && "Queue count currently includes everyone detected; configure queue_roi in MySQL. "}
          {!movementReady && "Set queue_direction_x/y in MySQL to measure forward movement. "}
          Wait is an estimate based on SERVICE_SECONDS_PER_PERSON (default 30s/person).
        </p>
      </section>
    </div>
  );
}
