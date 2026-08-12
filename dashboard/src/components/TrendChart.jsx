/**
 * TrendChart — Line chart showing queue length and wait time over time.
 * Uses Chart.js via react-chartjs-2.
 */

import { useEffect, useState, useRef } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

const MAX_POINTS = 60; // Show last 60 data points (~5 min at 5s intervals)

export default function TrendChart({ data }) {
  const [history, setHistory] = useState([]);

  useEffect(() => {
    if (!data) return;
    setHistory((prev) => {
      const next = [
        ...prev,
        {
          time: new Date(data.timestamp || Date.now()).toLocaleTimeString(),
          queueLength: data.queue_length ?? 0,
          waitTime: data.avg_wait_sec ?? 0,
          personCount: data.person_count ?? 0,
        },
      ];
      return next.slice(-MAX_POINTS);
    });
  }, [data?.timestamp]);

  const chartData = {
    labels: history.map((h) => h.time),
    datasets: [
      {
        label: "Queue Length",
        data: history.map((h) => h.queueLength),
        borderColor: "#7c3aed",
        backgroundColor: "rgba(124, 58, 237, 0.1)",
        fill: true,
        tension: 0.4,
        pointRadius: 2,
        pointHoverRadius: 5,
      },
      {
        label: "Persons Detected",
        data: history.map((h) => h.personCount),
        borderColor: "#4f8cff",
        backgroundColor: "rgba(79, 140, 255, 0.1)",
        fill: true,
        tension: 0.4,
        pointRadius: 2,
        pointHoverRadius: 5,
      },
      {
        label: "Wait Time (s)",
        data: history.map((h) => h.waitTime),
        borderColor: "#f59e0b",
        backgroundColor: "rgba(245, 158, 11, 0.05)",
        fill: false,
        tension: 0.4,
        pointRadius: 2,
        pointHoverRadius: 5,
        yAxisID: "y1",
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: {
      intersect: false,
      mode: "index",
    },
    plugins: {
      legend: {
        labels: {
          color: "#94a3b8",
          font: { family: "Inter, sans-serif", size: 12 },
          usePointStyle: true,
          pointStyleWidth: 10,
        },
      },
      tooltip: {
        backgroundColor: "rgba(10, 14, 39, 0.9)",
        titleColor: "#e2e8f0",
        bodyColor: "#94a3b8",
        borderColor: "rgba(79, 140, 255, 0.3)",
        borderWidth: 1,
        cornerRadius: 8,
        padding: 12,
      },
    },
    scales: {
      x: {
        ticks: { color: "#475569", maxRotation: 0, maxTicksLimit: 10 },
        grid: { color: "rgba(71, 85, 105, 0.15)" },
      },
      y: {
        type: "linear",
        position: "left",
        ticks: { color: "#475569", precision: 0 },
        grid: { color: "rgba(71, 85, 105, 0.15)" },
        title: { display: true, text: "Count", color: "#64748b" },
      },
      y1: {
        type: "linear",
        position: "right",
        ticks: { color: "#f59e0b" },
        grid: { drawOnChartArea: false },
        title: { display: true, text: "Seconds", color: "#f59e0b" },
      },
    },
    animation: {
      duration: 400,
    },
  };

  return (
    <div className="trend-chart" id="trend-chart">
      <div className="trend-chart-header">
        <span className="trend-chart-title">📈 Queue Trends</span>
        <span className="trend-chart-subtitle">
          Last {history.length} readings
        </span>
      </div>
      <div className="trend-chart-canvas">
        {history.length > 0 ? (
          <Line data={chartData} options={options} />
        ) : (
          <div className="chart-placeholder">
            Waiting for data to build trend...
          </div>
        )}
      </div>
    </div>
  );
}
