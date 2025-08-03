from flask import Flask, request, jsonify
from flask_cors import CORS
from nfl_survivor_tool import SURVIVOR_PICKER, compute_team_ratings, load_manual_schedule
from nfl_survivor_tool import Game

app = Flask(__name__)
CORS(app)

@app.route('/api/summary')
def get_summary():
    try:
        week = int(request.args.get('week', 1))
        entries = int(request.args.get('entries', 2))
        raw_schedule = load_manual_schedule()
        games = [Game(**g) for g in raw_schedule if g['week'] <= 18]
        team_ratings = compute_team_ratings()

        picker = SURVIVOR_PICKER(
            schedule=games,
            team_ratings=team_ratings,
            used_teams_entry1=[],
            used_teams_entry2=[]
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
            used_teams_entry1=[],
            used_teams_entry2=[]
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

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
