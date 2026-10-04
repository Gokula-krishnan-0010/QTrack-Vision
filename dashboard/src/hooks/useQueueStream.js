/** Load persisted frames and follow committed analytics over server-sent events. */
import { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = "http://localhost:8000";

export function useQueueStream(shopId) {
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [connectionStatus, setConnectionStatus] = useState("disconnected");
  const [error, setError] = useState(null);
  const esRef = useRef(null);
  const historyAbortRef = useRef(null);
  const backoffRef = useRef(1000);
  const reconnectTimerRef = useRef(null);
  const receivedLiveEventRef = useRef(false);

  const connect = useCallback(() => {
    if (!shopId) return;

    esRef.current?.close();
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    setConnectionStatus("connecting");
    setError(null);

    historyAbortRef.current?.abort();
    const controller = new AbortController();
    historyAbortRef.current = controller;
    let active = true;
    const loadHistory = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/api/queue/history?shop_id=${encodeURIComponent(shopId)}&hours=24&limit=60`,
          { signal: controller.signal }
        );
        if (!response.ok) throw new Error(`History request failed (${response.status})`);
        const rows = await response.json();
        if (!active) return;
        setHistory((previous) => mergeRows(previous, rows));
        if (!receivedLiveEventRef.current && rows.length) setData(rows[rows.length - 1]);
      } catch (requestError) {
        if (requestError.name !== "AbortError") {
          setError("Could not load saved queue history. Waiting for live frames...");
        }
      }
    };

    // Subscribe first so a frame arriving during the history request is not missed.
    const url = `${API_BASE}/api/queue/events?shop_id=${encodeURIComponent(shopId)}`;
    const es = new EventSource(url);
    esRef.current = es;
    loadHistory();

    es.onopen = () => {
      setConnectionStatus("connected");
      setError(null);
      backoffRef.current = 1000;
      loadHistory(); // Recover updates received while the browser was offline.
    };

    es.addEventListener("queue_update", (event) => {
      try {
        const parsed = JSON.parse(event.data);
        receivedLiveEventRef.current = true;
        setData(parsed);
        setHistory((previous) => mergeRows(previous, [parsed]));
      } catch (parseError) {
        console.error("[SSE] Failed to parse event data:", parseError);
      }
    });

    es.onerror = () => {
      setConnectionStatus("disconnected");
      es.close();
      esRef.current = null;
      active = false;
      controller.abort();
      const delay = backoffRef.current;
      setError(`Connection lost. Reconnecting in ${Math.round(delay / 1000)}s...`);
      reconnectTimerRef.current = setTimeout(() => {
        backoffRef.current = Math.min(backoffRef.current * 2, 30000);
        connect();
      }, delay);
    };

    return () => {
      active = false;
      controller.abort();
      historyAbortRef.current?.abort();
      historyAbortRef.current = null;
      esRef.current?.close();
      esRef.current = null;
    };
  }, [shopId]);

  useEffect(() => {
    receivedLiveEventRef.current = false;
    setData(null);
    setHistory([]);
    const cleanup = connect();
    return () => {
      cleanup?.();
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    };
  }, [connect]);

  return { data, history, connectionStatus, error };
}

function mergeRows(previous, incoming) {
  const byId = new Map(previous.map((row) => [row.id, row]));
  for (const row of incoming) {
    if (row?.id != null) byId.set(row.id, { ...byId.get(row.id), ...row });
  }
  return [...byId.values()]
    .sort((a, b) => (a.sequence_no ?? a.id) - (b.sequence_no ?? b.id))
    .slice(-60);
}
