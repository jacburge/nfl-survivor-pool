// Full-featured React UI for NFL Survivor Pool with charts, animations, Tailwind, icons, and modern styling

import { useState } from "react";
import { motion } from "framer-motion";
import { BarChart3, Trophy, Star } from "lucide-react";
import {
  ResponsiveContainer,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ZAxis,
  Tooltip,
  Legend,
  LabelList,
  LineChart,
  Line,
} from "recharts";

function LoadingSpinner() {
  return (
    <div className="flex justify-center items-center py-8">
      <svg className="animate-spin h-8 w-8 text-blue-500" viewBox="0 0 24 24">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/>
      </svg>
    </div>
  );
}

function SectionCard({ title, icon, children }) {
  return (
    <div className="bg-gradient-to-br from-blue-50 via-white to-red-50 rounded-xl shadow-lg p-6 mb-8 border border-blue-100">
      <div className="flex items-center mb-4">
        {icon && <span className="mr-2">{icon}</span>}
        <h2 className="text-xl font-semibold text-blue-700">{title}</h2>
      </div>
      {children}
    </div>
  );
}

// Helper to color code by future value (adjust as needed)
function getFutureValueColor(futureValue) {
  if (futureValue >= 1.5) return "#f87171"; // red-400
  if (futureValue >= 1.0) return "#60a5fa"; // blue-400
  return "#34d399"; // green-400
}

export default function SurvivorUI() {
  const [week, setWeek] = useState(1);
  const [entries, setEntries] = useState(2);
  const [summaryData, setSummaryData] = useState([]);
  const [simResults, setSimResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [topPicks, setTopPicks] = useState([]);

  const fetchSummary = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/summary?week=${week}&entries=${entries}`);
      const data = await res.json();
      // Sort by expected_value (or your preferred metric)
      const sorted = [...data.summary].sort((a, b) => b.expected_value - a.expected_value);
      setSummaryData(sorted);
      setTopPicks(sorted.slice(0, 2));
    } catch (err) {
      console.error("Error fetching summary:", err);
    }
    setLoading(false);
  };

  const runSimulation = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/simulate?week=${week}&entries=${entries}&sims=50000`);
      const data = await res.json();
      setSimResults(data.curve);
    } catch (err) {
      console.error("Error running simulation:", err);
    }
    setLoading(false);
  };

  return (
    <motion.div
      className="max-w-4xl mx-auto px-4 py-10 space-y-10 text-gray-800"
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7 }}
    >
      {/* Header */}
      <div className="text-center space-y-2">
        <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-700 via-blue-400 to-red-500 drop-shadow-lg">
          <Trophy className="inline-block mr-3 mb-2 text-blue-600" size={36} />
          2025 NFL Survivor Pool Optimizer
        </h1>
        <p className="text-base text-blue-700 font-medium">
          Smarter weekly picks using dynamic win probabilities, real pick popularity, and future value forecasts.
        </p>
      </div>

      {/* Controls */}
      <SectionCard title="Configure Your Pool">
        <form
          className="grid grid-cols-1 md:grid-cols-3 gap-6"
          onSubmit={e => { e.preventDefault(); fetchSummary(); }}
        >
          <div>
            <label className="block text-sm font-medium text-blue-700 mb-1">Week</label>
            <input
              type="number"
              min={1}
              max={18}
              value={week}
              onChange={(e) => setWeek(parseInt(e.target.value))}
              className="block w-full rounded-md border-blue-300 shadow-sm focus:border-red-500 focus:ring-red-500 px-3 py-2"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-blue-700 mb-1">Entries</label>
            <input
              type="number"
              min={1}
              max={10}
              value={entries}
              onChange={(e) => setEntries(parseInt(e.target.value))}
              className="block w-full rounded-md border-blue-300 shadow-sm focus:border-red-500 focus:ring-red-500 px-3 py-2"
            />
          </div>
          <div className="flex flex-col space-y-2 justify-end">
            <button
              type="submit"
              disabled={loading}
              className="w-full inline-flex justify-center items-center rounded-md border border-transparent bg-gradient-to-r from-blue-600 to-red-500 px-4 py-2 text-base font-bold text-white shadow-sm hover:from-blue-700 hover:to-red-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition"
            >
              {loading ? "Loading..." : "📋 Get Picks"}
            </button>
            <button
              type="button"
              onClick={runSimulation}
              disabled={loading}
              className="w-full inline-flex justify-center items-center rounded-md border border-blue-500 bg-white px-4 py-2 text-base font-bold text-blue-700 shadow-sm hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition"
            >
              {loading ? "Running..." : "📊 Simulate Survival"}
            </button>
          </div>
        </form>
      </SectionCard>

      {/* Top Picks Card */}
      {topPicks.length > 0 && (
        <SectionCard
          title="Top 2 Picks This Week"
          icon={<Star className="text-yellow-400" />}
        >
          <div className="flex flex-col md:flex-row gap-4">
            {topPicks.map((pick, idx) => (
              <div
                key={pick.team}
                className="flex-1 bg-gradient-to-br from-blue-100 via-white to-red-100 rounded-lg shadow p-4 border border-blue-200"
              >
                <div className="flex items-center mb-2">
                  <span className="text-2xl font-bold text-blue-700 mr-2">{idx + 1}.</span>
                  <span className="text-xl font-semibold text-red-600">{pick.team}</span>
                </div>
                <div className="text-sm text-gray-700">
                  <div>Win Probability: <span className="font-bold">{(pick.win_prob * 100).toFixed(1)}%</span></div>
                  <div>Popularity: <span className="font-bold">{(pick.popularity * 100).toFixed(1)}%</span></div>
                  <div>Expected Value: <span className="font-bold">{pick.expected_value.toFixed(2)}</span></div>
                  <div>Future Value: <span className="font-bold">{pick.future_value?.toFixed(2)}</span></div>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}

      {/* Table View */}
      {summaryData.length > 0 && (
        <div className="overflow-x-auto mb-6">
          <table className="min-w-full divide-y divide-blue-200 rounded-lg shadow">
            <thead className="bg-gradient-to-r from-blue-100 to-red-100">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase">Team</th>
                <th className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase">Win Prob</th>
                <th className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase">Popularity</th>
                <th className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase">Expected Value</th>
                <th className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase">Future Value</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-blue-100">
              {summaryData.map((row) => (
                <tr key={row.team}>
                  <td className="px-4 py-2 font-semibold text-blue-800">{row.team}</td>
                  <td className="px-4 py-2">{(row.win_prob * 100).toFixed(1)}%</td>
                  <td className="px-4 py-2">{(row.popularity * 100).toFixed(1)}%</td>
                  <td className="px-4 py-2">{row.expected_value.toFixed(2)}</td>
                  <td className="px-4 py-2">{row.future_value?.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pick Summary Graph */}
      <SectionCard title="Weekly Pick Summary" icon={<BarChart3 className="mr-1 text-blue-600" />}>
        {loading ? (
          <LoadingSpinner />
        ) : summaryData.length > 0 ? (
          <ResponsiveContainer width="100%" height={340}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 0 }}>
              <XAxis dataKey="popularity" name="Popularity" type="number" tickFormatter={v => `${(v*100).toFixed(0)}%`} />
              <YAxis dataKey="win_prob" name="Win Probability" type="number" tickFormatter={v => `${(v*100).toFixed(0)}%`} />
              <ZAxis dataKey="expected_value" name="Expected Value" type="number" range={[100, 600]} />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                formatter={(val, name) =>
                  name === "Expected Value"
                    ? val.toFixed(2)
                    : `${(val * 100).toFixed(1)}%`
                }
                contentStyle={{ background: "#fff" }}
              />
              <Legend />
              <Scatter
                name="Teams"
                data={summaryData}
                shape="circle"
                fill="#2563eb"
                // Color points by future value
                fillOpacity={0.85}
              >
                <LabelList
                  dataKey="team"
                  position="top"
                  style={{ fontSize: 12, fontWeight: 600, fill: "#1e293b" }}
                />
                {/* Color points by future value */}
                {summaryData.map((entry, idx) => (
                  <circle
                    key={entry.team}
                    cx={0}
                    cy={0}
                    r={0}
                    fill={getFutureValueColor(entry.future_value)}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        ) : (
          <div className="text-sm text-blue-500">No data to display. Click "Get Picks" to load.</div>
        )}
      </SectionCard>

      {/* Simulation Results */}
      {simResults.length > 0 && (
        <SectionCard title="Simulated Survival Probability">
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={simResults}>
              <XAxis dataKey="week" name="Week" />
              <YAxis dataKey="survival" name="Survival %" tickFormatter={v => `${(v*100).toFixed(0)}%`} />
              <Tooltip formatter={val => `${(val * 100).toFixed(2)}%`} />
              <Legend />
              <Line type="monotone" dataKey="survival" stroke="#ef4444" strokeWidth={3} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </SectionCard>
      )}
    </motion.div>
  );
}
