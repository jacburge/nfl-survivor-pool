# NFL Survivor Pool Optimization Tool (2025)

This tool helps you optimize your picks for an NFL Survivor Pool for the 2025 season. It uses the full schedule, team power ratings, situational factors (rest, travel, time zone, altitude), and can incorporate live betting lines and injury reports. It supports any number of entries and can simulate your season-long survival odds.

---

## Features

- **Up-to-date schedule and power ratings** (based on 2024 results)
- **Situational adjustments**: rest, travel, time zone, altitude
- **Live Elo updates**: Optionally update team ratings with real results
- **Live betting lines**: Optionally fetch and apply current point spreads
- **Injury adjustments**: Optionally apply Elo penalties for injured players
- **Pick popularity**: Heuristic or real data (if available)
- **Supports multiple entries**: Track and simulate any number of entries
- **Monte Carlo simulation**: Estimate probability at least one entry survives the season
- **Easy pick tracking**: Save your picks in a separate `picks.py` file

---

## Setup

1. **Clone the repository**  
   ```sh
   git clone https://github.com/yourusername/nfl-survivor-pool.git
   cd nfl-survivor-pool
   ```

2. **Install dependencies**  
   ```sh
   pip install requests python-dotenv
   ```

3. **Set up your picks**  
   Edit `picks.py` and enter your picks for each entry as lists of team names:
   ```python
   PICKS = [
       ["Cincinnati Bengals", "Dallas Cowboys"],      # Entry 1
       ["Pittsburgh Steelers", "Arizona Cardinals"],  # Entry 2
       # Add more lists for more entries if desired
   ]
   ```

4. **(Optional) Set up API keys**  
   - For live betting lines, get an API key from [The Odds API](https://the-odds-api.com/) and add it to a `.env` file:
     ```
     ODDS_API_KEY=your_actual_api_key_here
     ```

---

## Usage

### Basic Recommendations

Print recommended picks for a given week:
```sh
python3 nfl_survivor_tool.py --week 1
```

### With Elo Updates

Update team ratings with real results up to the given week:
```sh
python3 nfl_survivor_tool.py --week 5 --update-elo
```

### With Live Betting Lines

Fetch and apply current point spreads:
```sh
python3 nfl_survivor_tool.py --week 3 --use-betting-lines
```

### Simulate Survival Odds

Estimate the probability that at least one of your entries survives the season:
```sh
python3 nfl_survivor_tool.py --week 1 --simulate-survival
```
You can change the number of simulations and entries:
```sh
python3 nfl_survivor_tool.py --week 1 --simulate-survival --simulations 50000 --entries 3
```

---

## How It Works

- **Recommendations**: For each week, the tool recommends picks for each entry, avoiding teams you have already picked (as tracked in `picks.py`).
- **Simulation**: Runs thousands of simulated seasons, picking favorites each week (avoiding repeats per entry), and estimates your chance of survival.
- **Live Data**: If enabled, Elo ratings, betting lines, and injury adjustments are incorporated before making recommendations or running simulations.

---

## Customization

- **Edit `picks.py`** to track your picks for each entry.
- **Edit constants** in `nfl_survivor_tool.py` to adjust model sensitivity (e.g., REST_POINTS, TRAVEL_POINTS).
- **Add real pick popularity or injury data** if available.

---

## Notes

- `.env` and other sensitive files should be in your `.gitignore` and not committed to git.
- The tool is designed for educational and planning purposes and makes some simplifications compared to professional models.

---

## Example Output

```
Recommended picks for week 1: Entry1 = Dallas Cowboys, Entry2 = Buffalo Bills

Summary (team, winProb, popularity, futureValue, EV):
Dallas Cowboys           P(win)=0.765  Pop=0.40  FV=3.20  EV=0.44
Buffalo Bills            P(win)=0.710  Pop=0.35  FV=2.80  EV=0.39
...

Estimated probability at least one entry survives the season: 12.34%
```

---

## License

MIT License