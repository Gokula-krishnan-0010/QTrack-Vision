/**
 * App — Root component for QTrack Vision dashboard.
 *
 * Manages shop selection, SSE connection, and layout of all panels.
 */

import { useState, useEffect } from "react";
import { useQueueStream } from "./hooks/useQueueStream";
import Header from "./components/Header";
import QueueStats from "./components/QueueStats";
import LiveFeed from "./components/LiveFeed";
import TrendChart from "./components/TrendChart";

const API_BASE = "http://localhost:8000";

export default function App() {
  const [shops, setShops] = useState(["ration-shop-01"]);
  const [shopId, setShopId] = useState("ration-shop-01");
  const { data, history, connectionStatus, error } = useQueueStream(shopId);

  // Fetch available shops on mount
  useEffect(() => {
    async function fetchShops() {
      try {
        const res = await fetch(`${API_BASE}/api/queue/shops`);
        if (res.ok) {
          const json = await res.json();
          if (json.shops?.length > 0) {
            setShops(json.shops);
            if (!json.shops.includes(shopId)) {
              setShopId(json.shops[0]);
            }
          }
        }
      } catch {
        // Server not reachable — keep defaults
      }
    }
    fetchShops();
  }, []);

  return (
    <div className="app" id="app-root">
      <Header
        shopId={shopId}
        onShopChange={setShopId}
        shops={shops}
        connectionStatus={connectionStatus}
      />

      {error && (
        <div className="error-banner" id="error-banner">
          ⚠️ {error}
        </div>
      )}

      <main className="main-grid">
        <section className="panel panel--stats">
          <QueueStats data={data} />
        </section>

        <section className="panel panel--feed">
          <LiveFeed data={data} />
        </section>

        <section className="panel panel--chart">
          <TrendChart history={history} />
        </section>
      </main>

      <footer className="footer" id="app-footer">
        <p>
          QTrack Vision • Samsung Solve for Tomorrow •{" "}
          <span className="footer-tech">
            ESP32-CAM → FastAPI + YOLOv8n → React
          </span>
        </p>
      </footer>
    </div>
  );
}
