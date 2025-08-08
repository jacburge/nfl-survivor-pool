from flask import Flask, request, jsonify
from flask_cors import CORS
from nfl_survivor_tool import SURVIVOR_PICKER, compute_team_ratings, load_manual_schedule
from nfl_survivor_tool import Game, fetch_betting_lines
import ast
import json
import os
from schedule_2025 import SCHEDULE_2025

app = Flask(__name__)
CORS(app)

PICKS_PATH = os.path.join(os.path.dirname(__file__), "picks.json")

def serialize_schedule(schedule):
    # Convert datetime.date to string for JSON
    sched = []
    for g in schedule:
        g2 = dict(g)
        if hasattr(g2['date'], 'isoformat'):
            g2['date'] = g2['date'].isoformat()
        sched.append(g2)
    return sched

@app.route('/api/schedule')
def get_schedule():
    return jsonify(serialize_schedule(SCHEDULE_2025))

@app.route('/api/summary')
def get_summary():
    try:
        week = int(request.args.get('week', 1))
        entries = int(request.args.get('entries', 2))
        use_betting = request.args.get('betting', 'false').lower() == 'true'
        raw_schedule = load_manual_schedule()
        games = [Game(**g) for g in raw_schedule if g['week'] <= 18]
        if use_betting:
            team_ratings = compute_team_ratings(use_betting_lines=True, week=week)
        else:
            team_ratings = compute_team_ratings()
        
        try:
            with open(PICKS_PATH, "r") as f:
                picks = json.load(f)
        except Exception:
            picks = []

        while len(picks) < entries:
            picks.append([])
        for entry in picks:
            while len(entry) < week:
                entry.append(None)

        used_teams_per_entry = [
            [team for team in entry[:week-1] if team]
            for entry in picks[:entries]
        ]
        while len(used_teams_per_entry) < entries:
            used_teams_per_entry.append([])
        picker = SURVIVOR_PICKER(
            schedule=games,
            team_ratings=team_ratings,
            used_teams_per_entry=used_teams_per_entry
        )
        if use_betting:
            betting_lines = fetch_betting_lines(week)
            if betting_lines:
                picker.apply_betting_lines(betting_lines)
            picker.update_situational_factors(skip_win_prob=True)  # <-- pass a flag to skip win prob update
        else:
            picker.update_situational_factors()

        recommended_picks = picker.recommend_diversified_picks(week)
        summary = picker.summary_for_week(week)

        formatted = []
        for item in summary:
            team, win_prob, popularity, future_value, expected_value, point_spread = item
            formatted.append({
                "team": team,
                "win_prob": win_prob,
                "popularity": popularity,
                "future_value": future_value,
                "expected_value": expected_value,
                "point_spread": point_spread,
            })

        return jsonify({
            "recommended_picks": recommended_picks,
            "summary": formatted
        })
    except Exception as e:
        print("Error in /api/summary:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/simulate')
def simulate():
    try:
        week = int(request.args.get('week', 1))
        entries = int(request.args.get('entries', 2))
        sims = int(request.args.get('sims', 50000))
        raw_schedule = load_manual_schedule()
        games = [Game(**g) for g in raw_schedule if g['week'] <= 18]
        team_ratings = compute_team_ratings()

        picker = SURVIVOR_PICKER(
            schedule=games,
            team_ratings=team_ratings,
            used_teams_per_entry=[[] for _ in range(entries)]
        )
        picker.update_situational_factors()

        # Assume plot_survival_curve returns a list of dicts with 'week' and 'survival'
        curve = picker.plot_survival_curve(
            start_week=week,
            num_simulations=sims,
            num_entries=entries,
            used_teams=[set() for _ in range(entries)]
        )

        # If not, transform it here
        formatted_curve = []
        for point in curve:
            week_val, survival_val = point
            formatted_curve.append({
                "week": point.get("week"),
                "survival": point.get("survival"),
            })

        return jsonify({"curve": formatted_curve})
    except Exception as e:
        print("Error in /api/simulate:", e)
        return jsonify({"error": str(e)}), 500

@app.route('/api/picks', methods=['GET'])
def get_picks():
    try:
        with open(PICKS_PATH, "r") as f:
            picks = json.load(f)
        return jsonify({"picks": picks}), 200
    except Exception as e:
        return jsonify({"picks": []}), 200

@app.route('/api/save-picks', methods=['POST'])
def save_picks():
    picks = request.get_json()
    # Optionally validate picks format here
    try:
        with open(PICKS_PATH, "w") as f:
            json.dump(picks, f, indent=2)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def getAvailableTeamsForEntryWeek(schedule, picks, weekIdx, entryIdx):
    weekNum = weekIdx + 1
    teams_this_week = set()
    for game in schedule:
        if getattr(game, "week", None) == weekNum or (isinstance(game, dict) and game.get("week") == weekNum):
            home = getattr(game, "home", None) if hasattr(game, "home") else game.get("home")
            away = getattr(game, "away", None) if hasattr(game, "away") else game.get("away")
            if home: teams_this_week.add(home)
            if away: teams_this_week.add(away)
    already_picked = set()
    if entryIdx < len(picks):
        for w in range(weekIdx):
            if picks[entryIdx] and len(picks[entryIdx]) > w and picks[entryIdx][w]:
                already_picked.add(picks[entryIdx][w])
    available = [team for team in teams_this_week if team not in already_picked]
    # Debug output
    if not available:
        print(f"No teams for week {weekNum}, entry {entryIdx}. schedule: {schedule}")
    return available

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
