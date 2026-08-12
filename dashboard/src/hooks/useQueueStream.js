/**
 * useQueueStream — Custom React hook for SSE (Server-Sent Events) connection.
 *
 * Encapsulates EventSource lifecycle:
 *   • Auto-connects to /api/queue/events?shop_id=<shopId>
 *   • Reconnects with exponential backoff on error
 *   • Returns { data, connectionStatus, error }
 *   • Cleans up on unmount
 */

import { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = "http://localhost:8000";

/**
 * @param {string} shopId - Shop ID to subscribe to
 * @returns {{ data: object|null, connectionStatus: string, error: string|null }}
 */
export function useQueueStream(shopId) {
  const [data, setData] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState("disconnected"); // "connected" | "connecting" | "disconnected"
  const [error, setError] = useState(null);
  const esRef = useRef(null);
  const backoffRef = useRef(1000);
  const reconnectTimerRef = useRef(null);

  const connect = useCallback(() => {
    if (!shopId) return;

    // Clean up any existing connection
    if (esRef.current) {
      esRef.current.close();
    }
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }

    setConnectionStatus("connecting");
    setError(null);

    const url = `${API_BASE}/api/queue/events?shop_id=${encodeURIComponent(shopId)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      setConnectionStatus("connected");
      setError(null);
      backoffRef.current = 1000; // Reset backoff on successful connect
    };

    es.addEventListener("queue_update", (event) => {
      try {
        const parsed = JSON.parse(event.data);
        setData(parsed);
      } catch (e) {
        console.error("[SSE] Failed to parse event data:", e);
      }
    });

    es.onerror = () => {
      setConnectionStatus("disconnected");
      es.close();
      esRef.current = null;

      // Exponential backoff reconnect
      const delay = backoffRef.current;
      setError(`Connection lost. Reconnecting in ${Math.round(delay / 1000)}s...`);

      reconnectTimerRef.current = setTimeout(() => {
        backoffRef.current = Math.min(backoffRef.current * 2, 30000);
        connect();
      }, delay);
    };
  }, [shopId]);

  useEffect(() => {
    connect();

    return () => {
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [connect]);

  return { data, connectionStatus, error };
}
