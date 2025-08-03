from flask import Flask, request, jsonify
from flask_cors import CORS
from nfl_survivor_tool import SURVIVOR_PICKER, compute_team_ratings, load_manual_schedule
from nfl_survivor_tool import Game
import ast
import json

app = Flask(__name__)
CORS(app)

PICKS_FILE = "picks.json"

@app.route('/api/summary')
def get_summary():
    try:
        week = int(request.args.get('week', 1))
        entries = int(request.args.get('entries', 2))
        use_betting = request.args.get('betting', 'false').lower() == 'true'
        raw_schedule = load_manual_schedule()
        games = [Game(**g) for g in raw_schedule if g['week'] <= 18]
        if use_betting:
            team_ratings = compute_team_ratings(use_betting_lines=True)
        else:
            team_ratings = compute_team_ratings()
        picker = SURVIVOR_PICKER(
            schedule=games,
            team_ratings=team_ratings,
            used_teams_per_entry=[[] for _ in range(entries)]
        )
        picker.update_situational_factors()
        picker.recommend_picks(week)
        summary = picker.summary_for_week(week)

        # Ensure summary is a list of dicts with the correct keys
        # If not, transform it here
        formatted = []
        for item in summary:
            team, win_prob, popularity, future_value, expected_value = item
            formatted.append({
                "team": team,
                "win_prob": win_prob,
                "popularity": popularity,
                "future_value": future_value,
                "expected_value": expected_value,
            })

        return jsonify({"summary": formatted})
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
        with open(PICKS_FILE, "r") as f:
            picks = json.load(f)
    except Exception:
        picks = []
    return jsonify({"picks": picks})

@app.route('/api/picks', methods=['POST'])
def save_picks():
    try:
        data = request.json
        week = int(data.get("week"))
        selected_teams = data.get("selectedTeams", [])
        entries = int(data.get("entries", len(selected_teams)))

        # Load current picks
        try:
            with open(PICKS_FILE, "r") as f:
                picks = json.load(f)
        except Exception:
            picks = []

        # Ensure correct shape
        while len(picks) < entries:
            picks.append([])
        for entry in picks:
            while len(entry) < week:
                entry.append(None)

        # Update only the current week for each entry
        for i, team in enumerate(selected_teams):
            picks[i][week - 1] = team

        # Write back to picks.json
        with open(PICKS_FILE, "w") as f:
            json.dump(picks, f)

        return jsonify({"success": True, "picks": picks})
    except Exception as e:
        print("Error saving picks:", e)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
