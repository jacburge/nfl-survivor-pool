// Full-featured React UI for NFL Survivor Pool with charts, animations, Tailwind, icons, and modern styling

import React, { useState, useEffect, useRef } from "react";
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
  ReferenceLine
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

// Helper to color code by future value (red = low, purple = mid, blue = high)
function getFutureValueColor(futureValue) {
  // Linear gradient: red (#f87171) -> purple (#a78bfa) -> blue (#60a5fa)
  if (futureValue == null) return "#a78bfa"; // fallback to purple if missing
  if (futureValue <= 4) return "#f87171"; // red-400 (low)
  if (futureValue >= 10) return "#60a5fa"; // blue-400 (high)
  if (futureValue < 6) {
    // red to purple, t in [0,1] as futureValue goes from 4 to 6
    const t = (futureValue - 4) / 2;
    return interpolateColor("#f87171", "#a78bfa", t);
  } else {
    // purple to blue, t in [0,1] as futureValue goes from 6 to 10
    const t = (futureValue - 6) / 4;
    return interpolateColor("#a78bfa", "#60a5fa", t);
  }
}

// Helper to interpolate between two hex colors
function interpolateColor(a, b, t) {
  const ah = a.replace('#', '');
  const bh = b.replace('#', '');
  const ar = parseInt(ah.substring(0,2),16), ag = parseInt(ah.substring(2,4),16), ab = parseInt(ah.substring(4,6),16);
  const br = parseInt(bh.substring(0,2),16), bg = parseInt(bh.substring(2,4),16), bb = parseInt(bh.substring(4,6),16);
  const rr = Math.round(ar + (br-ar)*t);
  const rg = Math.round(ag + (bg-ag)*t);
  const rb = Math.round(ab + (bb-ab)*t);
  return `#${((1 << 24) + (rr << 16) + (rg << 8) + rb).toString(16).slice(1)}`;
}

function ToggleSwitch({ id, checked, onChange, label }) {
  return (
    <label htmlFor={id} className="flex items-center cursor-pointer select-none">
      <div className="relative">
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={onChange}
          className="sr-only"
        />
        <div className={`block w-12 h-7 rounded-full transition ${checked ? "bg-blue-600" : "bg-gray-300"}`}></div>
        <div
          className={`dot absolute left-1 top-1 bg-white w-5 h-5 rounded-full transition ${
            checked ? "translate-x-5" : ""
          }`}
        ></div>
      </div>
      <span className="ml-3 text-blue-700 font-medium">{label}</span>
    </label>
  );
}

// Helper to get teams playing in a given week from summaryData
function getTeamsForWeek(schedule, weekIdx) {
  // schedule: array of games, each with .week, .home, .away
  const week = weekIdx + 1;
  const teams = new Set();
  schedule.forEach(game => {
    if (game.week === week) {
      teams.add(game.home);
      teams.add(game.away);
    }
  });
  return Array.from(teams).sort();
}

export default function SurvivorUI() {
  const [week, setWeek] = useState(1);
  const [entries, setEntries] = useState(2);
  const [summaryData, setSummaryData] = useState([]);
  const [simResults, setSimResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [topPicks, setTopPicks] = useState([]);
  const [userPicks, setUserPicks] = useState([]);
  const [selectedTeams, setSelectedTeams] = useState([]);
  const [showPicks, setShowPicks] = useState(false);
  const [useBetting, setUseBetting] = useState(false);
  const [showToast, setShowToast] = useState(false);
  const toastTimeout = useRef(null);
  const [sortColumn, setSortColumn] = useState("expected_value");
  const [sortDirection, setSortDirection] = useState("desc");
  const [recommendedPicks, setRecommendedPicks] = useState([]);
  const [showTop2, setShowTop2] = useState(false);
  const [editPicks, setEditPicks] = useState([]); // [ [team, team, ...], ... ] for each entry
  const [schedule, setSchedule] = useState([]);

  // Fetch picks on mount and when entries changes
  useEffect(() => {
    fetch('/api/picks')
      .then(res => res.json())
      .then(data => {
        let picks = data.picks || [];
        if (picks.length < entries) {
          picks = [...picks, ...Array(entries - picks.length).fill([])];
        } else if (picks.length > entries) {
          picks = picks.slice(0, entries);
        }
        setUserPicks(picks);
      });
  }, [entries, week]);

  // Initialize editPicks when userPicks or week changes
  useEffect(() => {
    setEditPicks(userPicks.map(entry => [...entry]));
  }, [userPicks, week]);

  // Fetch schedule on mount
  useEffect(() => {
    fetch('/api/schedule')
      .then(res => res.json())
      .then(data => setSchedule(data));
  }, []);

  const fetchSummary = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/summary?week=${week}&entries=${entries}&betting=${useBetting}`);
      const data = await res.json();
      const sorted = [...data.summary].sort((a, b) => b.expected_value - a.expected_value);
      setSummaryData(sorted);
      setRecommendedPicks(data.recommended_picks || []);
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

  // Handler for dropdown change
  const handlePickChange = (weekIdx, entryIdx, team) => {
    setEditPicks(prev => {
      const updated = prev.map(arr => [...arr]);
      updated[weekIdx][entryIdx] = team;
      // Remove this team from subsequent weeks for this entry
      for (let w = weekIdx + 1; w < updated.length; w++) {
        if (updated[w][entryIdx] === team) {
          updated[w][entryIdx] = null;
        }
      }
      return updated;
    });
  };

  // Helper to get available teams for a dropdown (removes already picked teams in prior weeks for this entry)
  const getAvailableTeams = (entryIdx, weekIdx) => {
    const teamsThisWeek = getTeamsForWeek(summaryData, weekIdx);
    const alreadyPicked = new Set(editPicks[entryIdx]?.slice(0, weekIdx).filter(Boolean));
    return teamsThisWeek.filter(team => !alreadyPicked.has(team));
  };

  // Handle checkbox change
  const handleCheckboxChange = (team) => {
    setSelectedTeams(prev => {
      if (prev.includes(team)) {
        return prev.filter(t => t !== team);
      } else if (prev.length < entries) {
        return [...prev, team];
      }
      return prev;
    });
  };

  // Save picks for current week
  const savePicks = async () => {
    await fetch('/api/picks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ week, selectedTeams, entries }),
    });
    // Refresh picks after saving
    fetch('/api/picks')
      .then(res => res.json())
      .then(data => setUserPicks(data.picks || []));
    setSelectedTeams([]);
    setShowToast(true);
    if (toastTimeout.current) clearTimeout(toastTimeout.current);
    toastTimeout.current = setTimeout(() => setShowToast(false), 3000);
  };

  const handleSort = (column) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortColumn(column);
      setSortDirection("desc");
    }
  };

  const sortedSummaryData = [...summaryData].sort((a, b) => {
    let aVal = a[sortColumn];
    let bVal = b[sortColumn];
    if (typeof aVal === "string") {
      aVal = aVal.toLowerCase();
      bVal = bVal.toLowerCase();
    }
    if (aVal < bVal) return sortDirection === "asc" ? -1 : 1;
    if (aVal > bVal) return sortDirection === "asc" ? 1 : -1;
    return 0;
  });

  return (
    <>
      {/* Toast Notification */}
      {showToast && (
        <div className="fixed top-6 right-6 z-50">
          <div className="bg-blue-700 text-white px-6 py-3 rounded-lg shadow-lg flex items-center space-x-3 min-w-[220px] relative overflow-hidden">
            <span className="font-semibold">Picks saved to picks.py!</span>
            <div className="absolute bottom-0 left-0 h-1 bg-blue-300 animate-toast-bar" style={{ width: "100%" }} />
          </div>
          <style>
            {`
              @keyframes toast-bar {
                from { width: 100%; }
                to { width: 0%; }
              }
              .animate-toast-bar {
                animation: toast-bar 3s linear forwards;
              }
            `}
          </style>
        </div>
      )}

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
              className="grid grid-cols-1 md:grid-cols-4 gap-6"
              onSubmit={e => { e.preventDefault(); fetchSummary(); }}
          >
            <div>
              <label className="block text-sm font-medium text-blue-700 mb-1">Week</label>
              <input
                type="number"
                min={1}
                max={18}
                value={week}
                onChange={e => {
                  let val = parseInt(e.target.value);
                  if (val > 18) val = 18;
                  if (val < 1) val = 1;
                  setWeek(val);
                }}
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
            <div className="flex items-center mt-6">
              <ToggleSwitch
                id="betting"
                checked={useBetting}
                onChange={e => setUseBetting(e.target.checked)}
                label="Use Betting Lines"
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
              {/* <button
                type="button"
                onClick={runSimulation}
                disabled={loading}
                className="w-full inline-flex justify-center items-center rounded-md border border-blue-500 bg-white px-4 py-2 text-base font-bold text-blue-700 shadow-sm hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition"
              >
                {loading ? "Running..." : "📊 Simulate Survival"}
              </button> */}
            </div>
          </form>
        </SectionCard>

        {/* Recommended Picks Card (always shown if available)
        {recommendedPicks.length > 0 && (
          <SectionCard title="Recommended Picks This Week">
            <div className="flex overflow-x-auto gap-4 pb-2">
              {recommendedPicks.map((pick, idx) => (
                <div
                  key={idx}
                  className="min-w-[220px] flex-shrink-0 bg-gradient-to-br from-blue-100 via-white to-red-100 rounded-lg shadow p-4 border border-blue-200"
                >
                  <div className="flex items-center mb-2">
                    <span className="text-2xl font-bold text-blue-700 mr-2">Entry {idx + 1}</span>
                  </div>
                  <div className="text-xl font-semibold text-red-600">{pick || "-"}</div>
                </div>
              ))}
            </div>
          </SectionCard>
        )} */}

        {/* Toggle for Top 2 Picks */}
        {/* {recommendedPicks.length > 0 && (
          <div className="flex items-center mb-6">
            <ToggleSwitch
              id="showTop2"
              checked={showTop2}
              onChange={() => setShowTop2(v => !v)}
              label="Show Top 2 Picks This Week"
            />
          </div>
        )} */}

        {/* Top 2 Picks Card (conditionally shown) */}
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
                  <th></th>
                  <th
                    className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase cursor-pointer"
                    onClick={() => handleSort("team")}
                  >
                    Team {sortColumn === "team" && (sortDirection === "asc" ? "▲" : "▼")}
                  </th>
                  <th
                    className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase cursor-pointer"
                    onClick={() => handleSort("win_prob")}
                  >
                    Win Prob {sortColumn === "win_prob" && (sortDirection === "asc" ? "▲" : "▼")}
                  </th>
                  <th
                    className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase cursor-pointer"
                    onClick={() => handleSort("popularity")}
                  >
                    Popularity {sortColumn === "popularity" && (sortDirection === "asc" ? "▲" : "▼")}
                  </th>
                  <th
                    className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase cursor-pointer"
                    onClick={() => handleSort("expected_value")}
                  >
                    Expected Value {sortColumn === "expected_value" && (sortDirection === "asc" ? "▲" : "▼")}
                  </th>
                  <th
                    className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase cursor-pointer"
                    onClick={() => handleSort("future_value")}
                  >
                    Future Value {sortColumn === "future_value" && (sortDirection === "asc" ? "▲" : "▼")}
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-blue-100">
                {sortedSummaryData.map((row) => (
                  <tr key={row.team}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedTeams.includes(row.team)}
                        disabled={
                          !selectedTeams.includes(row.team) &&
                          selectedTeams.length >= entries
                        }
                        onChange={() => handleCheckboxChange(row.team)}
                      />
                    </td>
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
          {/* Legends moved to top */}
          <div className="mb-6 flex flex-col md:flex-row items-start md:items-center gap-8">
            {/* Color Gradient Legend for Future Value */}
            <div className="flex items-center">
              <span className="text-xs text-gray-700 mr-2">Future Value:</span>
              <span className="text-xs text-gray-700 ml-2 mr-1">Low </span>
              <div className="w-40 h-3 bg-gradient-to-r from-red-400 via-purple-400 to-blue-400 rounded" />
              <span className="text-xs text-gray-700 ml-2">High</span>
            </div>
            {/* Bubble Size Legend for Expected Value */}
            <div className="flex items-center ml-8">
              <span className="text-xs text-gray-700 mr-2">Expected Value:</span>
              <svg width="80" height="24">
                <circle cx="15" cy="12" r="7" fill="#d1d5db" stroke="#2563eb" strokeWidth="1" />
                <circle cx="40" cy="12" r="13" fill="#d1d5db" stroke="#2563eb" strokeWidth="1" />
                <circle cx="70" cy="12" r="18" fill="#d1d5db" stroke="#2563eb" strokeWidth="1" />
              </svg>
              <span className="text-xs text-gray-700 ml-2">Low</span>
              <span className="text-xs text-gray-700 ml-2">Med</span>
              <span className="text-xs text-gray-700 ml-2">High</span>
            </div>
          </div>
          {loading ? (
            <LoadingSpinner />
          ) : summaryData.length > 0 ? (
            <ResponsiveContainer width="100%" height={360}>
              <ScatterChart
                margin={{ top: 20, right: 40, bottom: 40, left: 40 }}
              >
                {/* X and Y axis cross at midpoint */}
                <XAxis
                  dataKey="win_prob"
                  name="Win Probability"
                  type="number"
                  domain={[0.4, 1]}
                  tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                  label={{
                    value: "Win Probability (%)",
                    position: "bottom",
                    offset: 0,
                    style: { textAnchor: "middle", fontWeight: 600, fill: "#1e293b" }
                  }}
                  axisLine={{ stroke: "#8884d8", strokeWidth: 2 }}
                />
                <YAxis
                  dataKey="popularity"
                  name="Popularity"
                  type="number"
                  domain={[0.4, .5]}
                  tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                  label={{
                    value: "Popularity (%)",
                    angle: -90,
                    position: "insideLeft",
                    style: { textAnchor: "middle", fontWeight: 600, fill: "#1e293b" }
                  }}
                  axisLine={{ stroke: "#8884d8", strokeWidth: 2 }}
                />
                {/* Reference lines for quadrants */}
                <ReferenceLine
                  x={0.7}
                  stroke="#aaa"
                  strokeDasharray="3 3"
                />
                <ReferenceLine
                  y={0.3}
                  stroke="#aaa"
                  strokeDasharray="3 3"
                />
                <ZAxis
                  dataKey="expected_value"
                  name="Expected Value"
                  range={[50, 2000]}
                  label="Expected Value"
                />
                <Tooltip
                  cursor={{ strokeDasharray: '3 3' }}
                  formatter={(val, name) =>
                    name === "Expected Value"
                      ? val.toFixed(2)
                      : `${(val * 100).toFixed(1)}%`
                  }
                  contentStyle={{ background: "#fff" }}
                />
                <Scatter
                  // name="Teams"
                  data={summaryData.map(row => ({
                    ...row,
                    fill: getFutureValueColor(row.future_value)
                  }))}
                  shape="circle"
                  fillOpacity={0.85}
                >
                  <LabelList
                    dataKey="team"
                    position="top"
                    style={{ fontSize: 9, fontWeight: 600, fill: "#1e293b" }}
                  />
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

        {/* 
          TRANSPOSE FUNCTION - Uncomment to use for debugging or analysis
        */}
        {/* <SectionCard title="Transpose Picks (Debug)">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-blue-200 rounded-lg shadow">
              <thead>
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase">Entry</th>
                  {[...Array(entries)].map((_, e) => (
                    <th key={e} className="px-4 py-2 text-left text-xs font-bold text-blue-700 uppercase">
                      Entry {e + 1}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {transposePicks(editPicks).map((entry, entryIdx) => (
                  <tr key={entryIdx}>
                    <td className="px-4 py-2 font-semibold text-blue-800">Entry {entryIdx + 1}</td>
                    {entry.map((team, weekIdx) => (
                      <td key={weekIdx} className="px-4 py-2">{team || "-"}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard> */}
      
      </motion.div>

      {/* Padding above the sticky footer */}
      <div className="h-16" />

      {/* Sticky Footer */}
      <footer className="w-full py-6 text-center text-sm text-blue-700 bg-gradient-to-r from-blue-50 via-white to-red-50 border-t border-blue-100 rounded-b-xl
        fixed bottom-0 left-0 right-0 z-40">
        &copy; 2025 &middot; Made by Jac
      </footer>
    </>
    );
  }

// Transpose [week][entry] to [entry][week] for display
function transposePicks(weekEntryArray) {
  if (!weekEntryArray || weekEntryArray.length === 0) return [];
  const numWeeks = weekEntryArray.length;
  const numEntries = weekEntryArray[0]?.length || 0;
  const result = [];
  for (let entry = 0; entry < numEntries; entry++) {
    const row = [];
    for (let week = 0; week < numWeeks; week++) {
      row.push(weekEntryArray[week][entry] || "");
    }
    result.push(row);
  }
  return result;
}

// Helper to get available teams for a specific entry and week
function getAvailableTeamsForEntryWeek(schedule, picks, weekIdx, entryIdx) {
  // Get all teams playing in this week
  const weekNum = weekIdx + 1;
  const teamsThisWeek = new Set();
  schedule.forEach(game => {
    if (game.week === weekNum) {
      teamsThisWeek.add(game.home);
      teamsThisWeek.add(game.away);
    }
  });

  // Remove teams already picked by this entry in prior weeks
  const alreadyPicked = new Set();
  for (let w = 0; w < weekIdx; w++) {
    if (picks[w] && picks[w][entryIdx]) {
      alreadyPicked.add(picks[w][entryIdx]);
    }
  }

  return Array.from(teamsThisWeek).filter(team => !alreadyPicked.has(team));
}
