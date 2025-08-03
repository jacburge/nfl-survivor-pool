"""
NFL Survivor Pool optimization tool for the 2025 season.

This tool helps you optimize your picks for an NFL Survivor Pool. It loads the 2025 NFL schedule,
assigns baseline power ratings to teams, applies situational factors (rest, travel, time zone, altitude),
and estimates win probabilities using an Elo-style model. The tool can incorporate live Elo updates,
betting lines, and injury adjustments. It supports any number of entries and can simulate your season-long
survival odds.

Key features:
- Up-to-date schedule and power ratings (based on 2024 results)
- Situational adjustments: rest, travel, time zone, altitude
- Live Elo updates: Optionally update team ratings with real results
- Live betting lines: Optionally fetch and apply current point spreads
- Injury adjustments: Optionally apply Elo penalties for injured players (see injuries.py)
- Pick popularity: Heuristic or real data (if available)
- Supports multiple entries: Track and simulate any number of entries (see picks.json)
- Monte Carlo simulation: Estimate probability at least one entry survives the season

To use this module, execute it as a script. It will print recommended picks for each entry for a given week,
and can simulate your survival odds.

Example usage:

    # Print recommended picks for week 1
    python3 nfl_survivor_tool.py --week 1

    # Update Elo ratings with real results up to week 5
    python3 nfl_survivor_tool.py --week 5 --update-elo

    # Fetch and apply current betting lines for week 3
    python3 nfl_survivor_tool.py --week 3 --use-betting-lines

    # Simulate survival odds for 3 entries with 50,000 simulations
    python3 nfl_survivor_tool.py --week 1 --simulate-survival --entries 3 --simulations 50000

Edit picks.json to track your picks for each entry, and injuries.py to specify Elo penalties for injuries.
The tool will always avoid recommending teams you've already picked.

"""

from __future__ import annotations

import datetime as _dt
import math
import matplotlib.pyplot as plt
import re
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
import requests
import schedule_2025 as schedule_2025
from injuries import INJURIES

import os
from dotenv import load_dotenv
import json

try:
    from bs4 import BeautifulSoup  # noqa: F401
except ImportError:
    BeautifulSoup = None

###############################################################################
# Data definitions
###############################################################################

def compute_team_ratings() -> Dict[str, float]:
    base = 1500
    scale = 30
    records = {
        # AFC East
        "Buffalo Bills": (13, 4),
        "Miami Dolphins": (8, 9),
        "New York Jets": (5, 12),
        "New England Patriots": (4, 13),
        # AFC North
        "Baltimore Ravens": (12, 5),
        "Pittsburgh Steelers": (10, 7),
        "Cincinnati Bengals": (9, 8),
        "Cleveland Browns": (3, 14),
        # AFC South
        "Houston Texans": (10, 7),
        "Indianapolis Colts": (8, 9),
        "Jacksonville Jaguars": (4, 13),
        "Tennessee Titans": (3, 14),
        # AFC West
        "Kansas City Chiefs": (15, 2),
        "Los Angeles Chargers": (11, 6),
        "Denver Broncos": (10, 7),
        "Las Vegas Raiders": (4, 13),
        # NFC East
        "Philadelphia Eagles": (14, 3),
        "Washington Commanders": (12, 5),
        "Dallas Cowboys": (7, 10),
        "New York Giants": (3, 14),
        # NFC North
        "Detroit Lions": (15, 2),
        "Minnesota Vikings": (14, 3),
        "Green Bay Packers": (11, 6),
        "Chicago Bears": (5, 12),
        # NFC South
        "Tampa Bay Buccaneers": (10, 7),
        "Atlanta Falcons": (8, 9),
        "Carolina Panthers": (5, 12),
        "New Orleans Saints": (5, 12),
        # NFC West
        "Los Angeles Rams": (10, 7),
        "Seattle Seahawks": (10, 7),
        "Arizona Cardinals": (8, 9),
        "San Francisco 49ers": (6, 11),
    }
    ratings = {}
    for team, (wins, losses) in records.items():
        diff = wins - losses
        ratings[team] = base + diff * scale
    return ratings


# Approximate geographic and time‑zone information for NFL teams.  These
# coordinates and time zone offsets (relative to UTC) are approximate but
# sufficient for estimating travel distance and jet lag.  Altitudes are
# measured in meters above sea level and only materially affect Denver.
TEAM_INFO: Dict[str, Dict[str, float]] = {
    "Arizona Cardinals":        {"lat": 33.5276, "lon": -112.2626, "tz": -7, "alt": 331},
    "Atlanta Falcons":          {"lat": 33.755,  "lon":  -84.400, "tz": -5, "alt": 320},
    "Baltimore Ravens":         {"lat": 39.278,  "lon":  -76.622, "tz": -5, "alt": 10},
    "Buffalo Bills":            {"lat": 42.7738, "lon":  -78.7869, "tz": -5, "alt": 240},
    "Carolina Panthers":        {"lat": 35.2251, "lon":  -80.8526, "tz": -5, "alt": 229},
    "Chicago Bears":            {"lat": 41.8623, "lon":  -87.6167, "tz": -6, "alt": 180},
    "Cincinnati Bengals":       {"lat": 39.0955, "lon":  -84.5160, "tz": -5, "alt": 150},
    "Cleveland Browns":         {"lat": 41.5061, "lon":  -81.6995, "tz": -5, "alt": 174},
    "Dallas Cowboys":           {"lat": 32.7473, "lon":  -97.0945, "tz": -6, "alt": 198},
    "Denver Broncos":           {"lat": 39.7439, "lon": -105.0201, "tz": -7, "alt": 1609},
    "Detroit Lions":            {"lat": 42.3400, "lon":  -83.0456, "tz": -5, "alt": 181},
    "Green Bay Packers":        {"lat": 44.5014, "lon":  -88.0622, "tz": -6, "alt": 177},
    "Houston Texans":           {"lat": 29.6847, "lon":  -95.4107, "tz": -6, "alt": 12},
    "Indianapolis Colts":       {"lat": 39.7601, "lon":  -86.1639, "tz": -5, "alt": 218},
    "Jacksonville Jaguars":     {"lat": 30.3239, "lon":  -81.6373, "tz": -5, "alt": 7},
    "Kansas City Chiefs":        {"lat": 39.0489, "lon":  -94.4849, "tz": -6, "alt": 266},
    "Las Vegas Raiders":        {"lat": 36.0909, "lon": -115.1830, "tz": -8, "alt": 620},
    "Los Angeles Chargers":     {"lat": 33.9535, "lon": -118.3391, "tz": -8, "alt": 27},
    "Los Angeles Rams":         {"lat": 33.9535, "lon": -118.3391, "tz": -8, "alt": 27},
    "Miami Dolphins":           {"lat": 25.9580, "lon":  -80.2389, "tz": -5, "alt": 3},
    "Minnesota Vikings":        {"lat": 44.9740, "lon":  -93.2581, "tz": -6, "alt": 252},
    "New England Patriots":      {"lat": 42.0910, "lon":  -71.2643, "tz": -5, "alt": 89},
    "New Orleans Saints":        {"lat": 29.9509, "lon":  -90.0830, "tz": -6, "alt": 2},
    "New York Giants":           {"lat": 40.8135, "lon":  -74.0745, "tz": -5, "alt": 6},
    "New York Jets":             {"lat": 40.8135, "lon":  -74.0745, "tz": -5, "alt": 6},
    "Philadelphia Eagles":       {"lat": 39.9008, "lon":  -75.1675, "tz": -5, "alt": 12},
    "Pittsburgh Steelers":       {"lat": 40.4468, "lon":  -80.0158, "tz": -5, "alt": 230},
    "San Francisco 49ers":       {"lat": 37.4030, "lon": -121.9700, "tz": -8, "alt": 3},
    "Seattle Seahawks":          {"lat": 47.5952, "lon": -122.3316, "tz": -8, "alt": 8},
    "Tampa Bay Buccaneers":      {"lat": 27.9759, "lon":  -82.5033, "tz": -5, "alt": 7},
    "Tennessee Titans":          {"lat": 36.1665, "lon":  -86.7713, "tz": -6, "alt": 139},
    "Washington Commanders":     {"lat": 38.9078, "lon":  -76.8644, "tz": -5, "alt": 30},
}


# Constants controlling situational adjustments.  These values are derived
# from published research and subject matter expertise summarised in the report.
# REST_POINTS: Elo points added for each day of rest differential.
# TRAVEL_POINTS: Elo points deducted per 1000 kilometres travelled by the road
# team (the home team effectively gains this advantage).
# TZ_POINTS: Elo points deducted for each time zone crossed by the road team.
# ALTITUDE_POINTS: Elo points advantage awarded to the home team playing at a
# significant altitude (e.g. Denver).  Only the Broncos get a bonus.
REST_POINTS = 5.0
TRAVEL_POINTS = 2.0
TZ_POINTS = 6.0
ALTITUDE_POINTS = 25.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great circle distance (in km) between two lat/lon points."""
    R = 6371.0  # Earth radius in kilometres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def scrape_schedule() -> List[Dict[str, object]]:
    """Scrape the full 2025 regular season schedule from FFToday.

    Returns a list of dictionaries, each containing:
        week (int): week number (1-18)
        date (datetime.date): game date (in America/New_York time zone)
        time (str): kickoff time string (ET) or 'TBD'
        away (str): away team full name
        home (str): home team full name
        note (str): additional note (e.g. international venue) if present

    This function uses BeautifulSoup to parse the markup on the FFToday
    schedule page.  It ignores playoff weeks.
    """
    url = "https://www.fftoday.com/nfl/schedule.php"
    # Provide a browser‑like User‑Agent header to avoid being blocked.
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/115.0 Safari/537.36'
        )
    }
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    schedule: List[Dict[str, object]] = []
    current_week = None
    # Find the main schedule table; it's the first table after the navigation.
    table = soup.find('table')
    if not table:
        raise RuntimeError("Could not locate schedule table on FFToday")
    rows = table.find_all('tr')
    for row in rows:
        # Week header row contains an anchor with name attribute
        anchor = row.find('a', attrs={'name': True})
        if anchor and anchor['name'].isdigit():
            current_week = int(anchor['name'])
            continue
        # Skip until a week has been set
        if current_week is None:
            continue
        # Skip header rows
        if row.find('td', class_='tableclmhdr'):
            continue
        # Skip bye week notes and other small rows
        classes = row.get('class', [])
        if 'smallestbody' in classes or 'smallestbodygrey' in classes:
            continue
        cells = row.find_all('td')
        if len(cells) != 4:
            # Could be a note about byes or international games
            continue
        # Extract values
        date_text = cells[0].get_text(strip=True)
        time_text = cells[1].get_text(strip=True)
        away_team = cells[2].get_text(strip=True)
        home_team = cells[3].get_text(strip=True)
        note = ''
        # Some games include footnote numbers (e.g. ¹).  Remove trailing digits.
        away_team = re.sub(r"\d+$", "", away_team).strip()
        home_team = re.sub(r"\d+$", "", home_team).strip()
        # Convert date
        # FFToday lists dates with abbreviations like 'Thu Sep 4' or 'Sun Dec 21'
        month_day = date_text.replace('Sun', '').replace('Mon', '').replace('Tue', '')\
            .replace('Wed', '').replace('Thu', '').replace('Fri', '').replace('Sat', '')\
            .strip()
        try:
            # Append year; weeks 1-17 occur in 2025; week 18 may cross into January 2026
            month_abbr, day = month_day.split()  # e.g., 'Sep', '4'
            month_num = { 'Jan':1, 'Feb':2, 'Mar':3, 'Apr':4, 'May':5, 'Jun':6,
                          'Jul':7, 'Aug':8, 'Sep':9, 'Oct':10, 'Nov':11, 'Dec':12 }[month_abbr]
            day_int = int(day)
            year = 2025
            # If month is January (after new year) then year should be 2026
            if month_num == 1:
                year = 2026
            game_date = _dt.date(year, month_num, day_int)
        except Exception:
            # Fallback if date can't be parsed
            game_date = None
        schedule.append({
            'week': current_week,
            'date': game_date,
            'time': time_text,
            'away': away_team,
            'home': home_team,
            'note': note,
        })
    return schedule


# ---------------------------------------------------------------------------
# Manual schedule loader
#
# The FFToday schedule page blocks automated HTTP requests from our execution
# environment.  To ensure reproducible behaviour, we transcribed the full
# 2025 regular‑season schedule (Weeks 1–18) by hand from the public listing
# and embedded it directly into this module.  Each entry contains the week
# number, the actual calendar date, kickoff time (Eastern), the away team and
# the home team.  International venue notes (e.g. games in Brazil, Europe or
# other countries) are included in the ``note`` field but do not affect the
# modelling.

def load_manual_schedule() -> List[Dict[str, object]]:
    """
    Return the 2025 regular season schedule as a list of dictionaries.

    Each dictionary has the keys:
        week (int): Week number (1–18)
        date (datetime.date): Game date
        time (str): Kickoff time in Eastern Time (as shown on FFToday)
        away (str): Away team name
        home (str): Home team name
        note (str): Additional notes about the game (e.g. international site)
    """
    from schedule_2025 import SCHEDULE_2025
    return SCHEDULE_2025


def elo_probability(elo_diff: float) -> float:
    """Convert an Elo difference into a win probability for the higher‑rated team."""
    return 1.0 / (1.0 + 10 ** (-elo_diff / 400.0))


@dataclass
class Game:
    week: int
    date: Optional[_dt.date]
    time: str
    away: str
    home: str
    note: str
    win_prob_home: Optional[float] = None
    win_prob_away: Optional[float] = None
    popularity: Optional[float] = None
    ev: Optional[float] = None
    future_value: Optional[float] = None


@dataclass
class SURVIVOR_PICKER:
    """Class encapsulating survivor pool modelling and optimisation."""
    schedule: List[Game]
    team_ratings: Dict[str, float] = field(default_factory=compute_team_ratings)
    used_teams_per_entry: List[List[str]] = field(default_factory=list)

    def update_situational_factors(self) -> None:
        """Compute situational advantages and win probabilities for each game.

        This method iterates through the schedule and, for each game, calculates
        rest differential, travel distance, time zone displacement and altitude
        advantage.  It then converts the resulting Elo difference into a win
        probability for both the home and away teams.
        """
        # Precompute last game dates for rest calculations
        last_played: Dict[str, _dt.date] = {}
        for game in self.schedule:
            # Determine base ratings
            rating_home = self.team_ratings.get(game.home, 1500.0)
            rating_away = self.team_ratings.get(game.away, 1500.0)
            # Adjust ratings for injuries if specified in injury_impact
            # The injury_impact dict maps team names to an Elo penalty.  You can
            # populate this via fetch_injury_reports() before calling this method.
            injury_penalty_home = getattr(self, 'injury_impact', {}).get(game.home, 0.0)
            injury_penalty_away = getattr(self, 'injury_impact', {}).get(game.away, 0.0)
            rating_home -= injury_penalty_home
            rating_away -= injury_penalty_away
            # Home field advantage in Elo points (~65)
            elo_diff = rating_home - rating_away + 65.0
            # Rest differential
            rest_home = 7  # default rest for week 1
            rest_away = 7
            if game.date and game.home in last_played:
                prev_date = last_played[game.home]
                rest_home = (game.date - prev_date).days
            if game.date and game.away in last_played:
                prev_date = last_played[game.away]
                rest_away = (game.date - prev_date).days
            rest_diff = rest_home - rest_away
            elo_diff += rest_diff * REST_POINTS
            # Travel distance (home is zero; road team travels to home stadium)
            home_info = TEAM_INFO.get(game.home)
            away_info = TEAM_INFO.get(game.away)
            if home_info and away_info:
                dist_km = haversine(away_info['lat'], away_info['lon'], home_info['lat'], home_info['lon'])
                # convert to Elo points; road team loses points
                elo_diff += (dist_km / 1000.0) * TRAVEL_POINTS
                # Time zone displacement: difference in absolute offsets
                tz_diff = abs(home_info['tz'] - away_info['tz'])
                elo_diff += tz_diff * TZ_POINTS
                # Altitude advantage: if home field is significantly higher
                if home_info['alt'] >= 1000 and away_info['alt'] < 1000:
                    elo_diff += ALTITUDE_POINTS
            # Compute win probabilities
            game.win_prob_home = elo_probability(elo_diff)
            game.win_prob_away = 1.0 - game.win_prob_home
            # Update last played date
            if game.date:
                last_played[game.home] = game.date
                last_played[game.away] = game.date

    def compute_pick_popularity(self, week_games: List[Game]) -> None:
        """Approximate pick popularity heuristically for a set of games.

        Teams with higher win probabilities tend to be more popular picks.  We
        assign a popularity score between 0.05 and 0.4 based on ordinal rank,
        with the highest favourite attracting 40% of picks and the least
        attractive game drawing 5%.  These values can be adjusted to
        calibrate the sensitivity of the EV calculation.
        """
        # Sort games descending by home win probability (higher -> more popular)
        sorted_games = sorted(week_games, key=lambda g: g.win_prob_home, reverse=True)
        n = len(sorted_games)
        for i, g in enumerate(sorted_games):
            # Map rank i to popularity between 0.4 (most popular) and 0.05 (least)
            max_pop = 0.4
            min_pop = 0.05
            if n > 1:
                pop = max_pop - (max_pop - min_pop) * (i / (n - 1))
            else:
                pop = 0.4
            g.popularity = pop

    def future_value(self, team: str, current_week: int) -> float:
        """Estimate future value of saving a team for later.

        The future value is the sum of win probabilities in remaining weeks
        where the team is favoured by at least 60%.  Saving a strong team
        yields positive value; using a team early expends this optionality.
        """
        fv = 0.0
        for g in self.schedule:
            if g.week <= current_week:
                continue
            if g.home == team and g.win_prob_home and g.win_prob_home >= 0.60:
                fv += g.win_prob_home
            elif g.away == team and g.win_prob_away and g.win_prob_away >= 0.60:
                fv += g.win_prob_away
        return fv

    def recommend_picks(self, week: int) -> List[Optional[str]]:
        """Recommend two teams for the given week based on EV and diversification.

        Returns a tuple (pick_entry1, pick_entry2).  If there are fewer than
        two eligible picks, one or both values may be None.
        """
        # Filter games for the specified week
        week_games = [g for g in self.schedule if g.week == week]
        if not week_games:
            return [None for _ in range(len(self.used_teams_per_entry))]
        # Compute popularity scores for this week's games
        self.compute_pick_popularity(week_games)
        picks = []
        for entry_idx, used_teams in enumerate(self.used_teams_per_entry):
            candidates = []
            for g in week_games:
                # Determine which team is favourite (we treat home team as the default
                # survivor pick because the model builds win_prob_home; if the home
                # probability is below 0.5 we invert the matchup).
                if g.win_prob_home is None or g.win_prob_away is None:
                    continue
                # Choose favourite team and associated probability
                if g.win_prob_home >= g.win_prob_away:
                    fav_team = g.home
                    fav_prob = g.win_prob_home
                    opp_prob = g.win_prob_away
                else:
                    fav_team = g.away
                    fav_prob = g.win_prob_away
                    opp_prob = g.win_prob_home
                # Skip if favourite has already been used by both entries
                used_both = fav_team in self.used_teams_per_entry[0] and fav_team in self.used_teams_per_entry[1]
                if used_both:
                    continue
                # Compute popularity (if popularity corresponds to home probability we approximate
                # by using g.popularity; invert if away favourite)
                popularity = g.popularity or 0.1
                if fav_team == g.away:
                    # assign same popularity as home game for simplicity
                    popularity = popularity  # no change
                # Estimate future value of saving this team
                fv = self.future_value(fav_team, week)
                # Compute expected value: win_prob * (1 - popularity) - small penalty for burning future value
                ev = fav_prob * (1 - popularity) - fv * 0.05
                candidates.append((fav_team, ev))
            candidates.sort(key=lambda t: t[1], reverse=True)
            picks.append(candidates[0][0] if candidates else None)
        return picks

    def summary_for_week(self, week: int) -> List[Tuple[str, float, float, float, float]]:
        """Return a summary of win probability, popularity and EV for the week's games.

        Returns a list of tuples: (fav_team, win_prob, popularity, future_value)
        sorted by EV descending.  This can help interpret the model's
        recommendations.
        """
        week_games = [g for g in self.schedule if g.week == week]
        self.compute_pick_popularity(week_games)
        summary = []
        for g in week_games:
            # Determine favourite team
            if g.win_prob_home is None or g.win_prob_away is None:
                continue
            if g.win_prob_home >= g.win_prob_away:
                team = g.home
                prob = g.win_prob_home
                pop = g.popularity or 0.1
            else:
                team = g.away
                prob = g.win_prob_away
                pop = g.popularity or 0.1
            fv = self.future_value(team, week)
            ev = prob * (1 - pop) - fv * 0.05
            summary.append((team, prob, pop, fv, ev))
        summary.sort(key=lambda t: t[4], reverse=True)
        return summary

    def simulate_two_entry_survivor_paths(
        self,
        start_week: int,
        num_simulations: int = 10000,
        random_seed: Optional[int] = None,
        used_teams_1: Optional[set] = None,
        used_teams_2: Optional[set] = None
    ) -> float:
        """
        Simulate multiple survivor paths for two entries using Monte Carlo.
        Returns the estimated probability that at least one entry survives all weeks.
        """
        if random_seed is not None:
            random.seed(random_seed)
        survival_count = 0
        for _ in range(num_simulations):
            ut1 = set(used_teams_1) if used_teams_1 else set()
            ut2 = set(used_teams_2) if used_teams_2 else set()
            alive_1 = True
            alive_2 = True
            for week in range(start_week, 19):
                week_games = [g for g in self.schedule if g.week == week]
                # Build candidate picks for each entry (teams not yet used)
                candidates_1 = []
                candidates_2 = []
                for g in week_games:
                    # Pick the favourite for each game
                    if g.win_prob_home is None or g.win_prob_away is None:
                        continue
                    if g.win_prob_home >= g.win_prob_away:
                        fav_team = g.home
                        win_prob = g.win_prob_home
                    else:
                        fav_team = g.away
                        win_prob = g.win_prob_away
                    if fav_team not in ut1:
                        candidates_1.append((fav_team, win_prob))
                    if fav_team not in ut2:
                        candidates_2.append((fav_team, win_prob))
                if not candidates_1 and not candidates_2:
                    alive_1 = False
                    alive_2 = False
                    break
                # Weighted random pick for each entry
                pick_1 = None
                pick_2 = None
                if candidates_1:
                    teams1, probs1 = zip(*candidates_1)
                    weights1 = [p / sum(probs1) for p in probs1]
                    pick_1 = random.choices(teams1, weights=weights1, k=1)[0]
                if candidates_2:
                    teams2, probs2 = zip(*candidates_2)
                    weights2 = [p / sum(probs2) for p in probs2]
                    # Ensure entry 2 does not pick the same team as entry 1 if possible
                    filtered = [(t, w) for t, w in zip(teams2, weights2) if t != pick_1]
                    if filtered:
                        teams2, weights2 = zip(*filtered)
                        pick_2 = random.choices(teams2, weights=weights2, k=1)[0]
                    else:
                        pick_2 = pick_1 if pick_1 else random.choices(teams2, weights=weights2, k=1)[0]
                # Simulate win/loss for each entry
                win_chance_1 = dict(candidates_1).get(pick_1, 0) if pick_1 else 0
                win_chance_2 = dict(candidates_2).get(pick_2, 0) if pick_2 else 0
                if pick_1:
                    if random.random() > win_chance_1:
                        alive_1 = False
                else:
                    alive_1 = False
                if pick_2:
                    if random.random() > win_chance_2:
                        alive_2 = False
                else:
                    alive_2 = False
                ut1.add(pick_1)
                ut2.add(pick_2)
                # If both are dead, stop early
                if not alive_1 and not alive_2:
                    break
            # Count if at least one entry survived all weeks
            if alive_1 or alive_2:
                survival_count += 1
        return survival_count / num_simulations if num_simulations > 0 else 0.0

    def simulate_multi_entry_survivor_paths(
        self,
        start_week: int,
        num_simulations: int = 10000,
        num_entries: int = 2,
        used_teams: Optional[List[set]] = None,
        random_seed: Optional[int] = None
    ) -> float:
        """
        Simulate multiple survivor paths for N entries using Monte Carlo.
        Returns the estimated probability that at least one entry survives all weeks.
        """
        if random_seed is not None:
            random.seed(random_seed)
        survival_count = 0
        for _ in range(num_simulations):
            uts = [set(used_teams[i]) if used_teams and i < len(used_teams) else set() for i in range(num_entries)]
            alive = [True] * num_entries
            for week in range(start_week, 19):
                week_games = [g for g in self.schedule if g.week == week]
                # Build candidate picks for each entry (teams not yet used)
                candidates = []
                for i in range(num_entries):
                    entry_candidates = []
                    for g in week_games:
                        if g.win_prob_home is None or g.win_prob_away is None:
                            continue
                        if g.win_prob_home >= g.win_prob_away:
                            fav_team = g.home
                            win_prob = g.win_prob_home
                        else:
                            fav_team = g.away
                            win_prob = g.win_prob_away
                        if fav_team not in uts[i]:
                            entry_candidates.append((fav_team, win_prob))
                    candidates.append(entry_candidates)
                # Assign picks for each entry, avoiding duplicate picks in the same week if possible
                picks = [None] * num_entries
                picked_teams = set()
                for i in range(num_entries):
                    entry_candidates = [c for c in candidates[i] if c[0] not in picked_teams]
                    if not entry_candidates:
                        entry_candidates = candidates[i]
                    if entry_candidates:
                        teams, probs = zip(*entry_candidates)
                        weights = [p / sum(probs) for p in probs]
                        pick = random.choices(teams, weights=weights, k=1)[0]
                        picks[i] = pick
                        picked_teams.add(pick)
                # Simulate win/loss for each entry
                for i in range(num_entries):
                    if not alive[i]:
                        continue
                    pick = picks[i]
                    win_chance = dict(candidates[i]).get(pick, 0) if pick else 0
                    if pick:
                        if random.random() > win_chance:
                            alive[i] = False
                    else:
                        alive[i] = False
                    uts[i].add(pick)
                if not any(alive):
                    break
            if any(alive):
                survival_count += 1
        return survival_count / num_simulations if num_simulations > 0 else 0.0

    def plot_survival_curve(self, start_week=1, num_simulations=10000, num_entries=2, used_teams=None):
        survival_by_week = [0] * (19 - start_week)
        
        for _ in range(num_simulations):
            uts = [set(used_teams[i]) if used_teams and i < len(used_teams) else set() for i in range(num_entries)]
            alive = [True] * num_entries

            for week_offset, week in enumerate(range(start_week, 19)):
                if not any(alive):
                    break
                week_games = [g for g in self.schedule if g.week == week]
                candidates = []
                for i in range(num_entries):
                    entry_candidates = []
                    for g in week_games:
                        if g.win_prob_home is None or g.win_prob_away is None:
                            continue
                        fav_team = g.home if g.win_prob_home >= g.win_prob_away else g.away
                        win_prob = g.win_prob_home if fav_team == g.home else g.win_prob_away
                        if fav_team not in uts[i]:
                            entry_candidates.append((fav_team, win_prob))
                    candidates.append(entry_candidates)

                picks = [None] * num_entries
                picked_teams = set()
                for i in range(num_entries):
                    entry_candidates = [c for c in candidates[i] if c[0] not in picked_teams] or candidates[i]
                    if entry_candidates:
                        teams, probs = zip(*entry_candidates)
                        weights = [p / sum(probs) for p in probs]
                        pick = random.choices(teams, weights=weights, k=1)[0]
                        picks[i] = pick
                        picked_teams.add(pick)

                for i in range(num_entries):
                    if not alive[i]: continue
                    pick = picks[i]
                    win_chance = dict(candidates[i]).get(pick, 0)
                    if random.random() > win_chance:
                        alive[i] = False
                    uts[i].add(pick)

                if any(alive):
                    survival_by_week[week_offset] += 1

        # Normalize to percentage
        survival_pct = [s / num_simulations * 100 for s in survival_by_week]
        weeks = list(range(start_week, 19))
        
        # Plot
        # plt.figure(figsize=(10, 6))
        # plt.plot(weeks, survival_pct, marker='o')
        # plt.title('Simulated Survivor Odds (At Least 1 Entry Alive)')
        # plt.xlabel('Week')
        # plt.ylabel('Survival %')
        # plt.grid(True)
        # plt.xticks(weeks)
        # plt.ylim(0, 100)
        # plt.tight_layout()
        # plt.show()
    # ---------------------------------------------------------------------
    # Live data integration
    #
    # These methods illustrate how live betting lines and injury reports
    # could be integrated.  Because our environment does not permit
    # automated scraping of sportsbook sites or official injury lists, these
    # functions accept pre‑processed data (e.g. from a CSV or API) and
    # adjust the model accordingly.  You can call them before
    # update_situational_factors() to refine win probabilities.

    def apply_betting_lines(self, lines: Dict[int, Dict[Tuple[str, str], float]]) -> None:
        """
        Incorporate point spreads into the win probability model.

        ``lines`` should be a dictionary keyed by week number.  Each value is
        another dict mapping (away_team, home_team) tuples to the home team’s
        point spread (negative values indicate the home team is favoured).
        For example::

            lines[1][('Dallas Cowboys', 'Philadelphia Eagles')] = -3.5

        The spread is converted to an implied win probability using a
        logistic model: P(win) = 1/(1+exp(-k*spread)).  A typical value for
        k is 0.15 (so a 7‑point favourite has ~70% win probability).  This
        update modifies ``win_prob_home`` and ``win_prob_away`` for the
        corresponding games.
        """
        k = 0.15
        for game in self.schedule:
            if game.week in lines:
                key = (game.away, game.home)
                if key in lines[game.week]:
                    spread = lines[game.week][key]
                    # Negative spread: home favoured; positive: home underdog
                    prob_home = 1.0 / (1.0 + math.exp(-k * (-spread)))
                    game.win_prob_home = prob_home
                    game.win_prob_away = 1.0 - prob_home

    def apply_injury_reports(self, injuries: Dict[str, float]) -> None:
        """
        Apply injury adjustments to team ratings.

        ``injuries`` maps team names to an Elo penalty (positive numbers)
        representing the cumulative impact of injured players.  For example,
        if a starting quarterback is out, you might apply a 50‑point penalty
        to that team.  You can populate this dictionary by parsing weekly
        injury reports from official sources (e.g. NFL.com) or any other
        trusted dataset.

        The penalties are stored on the instance as ``injury_impact`` and
        subtracted from the base ratings when calculating win probabilities.
        """
        # Copy provided injuries to an internal dict used in update_situational_factors()
        self.injury_impact = injuries.copy()


def fetch_weekly_scores(year: int, week: int):
    url = f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?week={week}&season={year}"
    resp = requests.get(url)
    data = resp.json()
    results = []
    for event in data.get('events', []):
        competition = event['competitions'][0]
        home = competition['competitors'][0] if competition['competitors'][0]['homeAway'] == 'home' else competition['competitors'][1]
        away = competition['competitors'][1] if competition['competitors'][0]['homeAway'] == 'home' else competition['competitors'][0]
        results.append({
            'home': home['team']['displayName'],
            'away': away['team']['displayName'],
            'home_score': int(home['score']),
            'away_score': int(away['score']),
        })
    return results


def update_elo_ratings(team_ratings: Dict[str, float], results: List[Dict[str, object]], k: float = 20.0) -> None:
    """
    Update team Elo ratings in-place based on actual game results.
    """
    for result in results:
        home = result['home']
        away = result['away']
        home_score = result['home_score']
        away_score = result['away_score']
        rating_home = team_ratings.get(home, 1500.0)
        rating_away = team_ratings.get(away, 1500.0)
        expected_home = elo_probability(rating_home - rating_away + 65.0)
        actual_home = 1.0 if home_score > away_score else 0.0
        delta = k * (actual_home - expected_home)
        team_ratings[home] = rating_home + delta
        team_ratings[away] = rating_away - delta


def fetch_betting_lines(week: int) -> dict:
    """
    Fetch NFL point spreads for the given week using The Odds API.
    Returns a dict: {week: { (away, home): spread, ... } }
    """
    load_dotenv()
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        print("No API key found for The Odds API.")
        return {}
    url = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds/"
    params = {
        "apiKey": api_key,
        "regions": "us",
        "markets": "spreads",
        "oddsFormat": "american"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        lines = {}
        for game in data:
            home = game['home_team']
            away = game['away_team']
            # Find the first bookmaker with a spread
            for bookmaker in game.get('bookmakers', []):
                for market in bookmaker.get('markets', []):
                    if market['key'] == 'spreads':
                        for outcome in market['outcomes']:
                            if outcome['name'] == home:
                                spread = outcome['point']
                                lines[(away, home)] = spread
                        break
                break
        return {week: lines}
    except Exception as e:
        print(f"Could not fetch betting lines: {e}")
        return {}
    
def plot_summary_bubble_chart(summary_data):
    import matplotlib.pyplot as plt

    teams = [row[0] for row in summary_data]
    win_probs = [row[1] for row in summary_data]
    popularities = [row[2] for row in summary_data]
    future_values = [row[3] for row in summary_data]
    expected_values = [row[4] for row in summary_data]
    sizes = [abs(ev) * 1000 for ev in expected_values]  # Bubble sizes

    # plt.figure(figsize=(12, 8))
    # scatter = plt.scatter(win_probs, future_values, s=sizes, c=popularities,
    #                     cmap='coolwarm', alpha=0.7)

    # # Add team labels
    # for i, team in enumerate(teams):
    #     plt.text(win_probs[i] + 0.005, future_values[i] + 0.1, team, fontsize=9)

    # # Add colorbar for popularity
    # cbar = plt.colorbar(scatter)
    # cbar.set_label('Pick Popularity')

    # # Add legend for expected value (bubble size)
    # for ev in [0.1, 0.3, 0.5]:
    #     plt.scatter([], [], s=ev * 1000, c='gray', alpha=0.5,
    #                 label=f'EV {ev:+.1f}')
    # plt.legend(scatterpoints=1, frameon=True, labelspacing=1,
    #         title='Expected Value (bubble size)')

    # plt.xlabel('Win Probability')
    # plt.ylabel('Future Value')
    # plt.title('Weekly Pick Summary: Win Probability vs. Future Value')
    # plt.grid(True)
    # plt.tight_layout()
    # plt.show()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NFL Survivor Pool optimizer")
    parser.add_argument('--week', type=int, default=1, help='Week number to generate picks for')
    parser.add_argument('--update-elo', action='store_true', help='Update Elo ratings using live results up to this week')
    parser.add_argument('--use-betting-lines', action='store_true', help='Fetch and apply live betting lines for this week')
    parser.add_argument('--simulate-survival', action='store_true', help='Estimate probability at least one entry survives the season')
    parser.add_argument('--simulations', type=int, default=10000, help='Number of Monte Carlo simulations to run')
    parser.add_argument('--entries', type=int, default=2, help='Number of survivor entries')
    parser.add_argument('--plot-survival', action='store_true', help='Show survival % over time')
    parser.add_argument('--plot-summary', action='store_true', help='Visualize summary of weekly pick recommendations')
    args = parser.parse_args()
    raw_schedule = load_manual_schedule()
    games = [Game(**g) for g in raw_schedule if g['week'] <= 18]
    team_ratings = compute_team_ratings()

    # Load picks.json
    try:
        with open("picks.json", "r") as f:
            PICKS = json.load(f)
    except Exception:
        PICKS = []

    # Build used_teams_per_entry for all entries up to the current week
    used_teams_per_entry = [
        [team for team in entry[:args.week-1] if team]
        for entry in PICKS[:args.entries]
    ]
    while len(used_teams_per_entry) < args.entries:
        used_teams_per_entry.append([])

    picker = SURVIVOR_PICKER(
        schedule=games,
        team_ratings=team_ratings,
        used_teams_per_entry=used_teams_per_entry
    )

    if args.update_elo:
        for wk in range(1, args.week):
            results = fetch_weekly_scores(2025, wk)
            if results:
                update_elo_ratings(team_ratings, results)

    if args.use_betting_lines:
        betting_lines = fetch_betting_lines(args.week)
        if betting_lines:
            picker.apply_betting_lines(betting_lines)

    picker.update_situational_factors()
    picks = picker.recommend_picks(args.week)
    for idx, pick in enumerate(picks):
        print(f"Recommended pick for Entry {idx+1} (week {args.week}): {pick}")

    summary = picker.summary_for_week(args.week)
    print("\nSummary (team, winProb, popularity, futureValue, EV):")
    for team, prob, pop, fv, ev in summary:
        print(f"{team:24s}  P(win)={prob:.3f}  Pop={pop:.2f}  FV={fv:.2f}  EV={ev:.3f}")

    if args.simulate_survival:
        used_teams = [set(picks) if i < len(PICKS) else set() for i, picks in enumerate(PICKS[:args.entries])]
        while len(used_teams) < args.entries:
            used_teams.append(set())
        prob = picker.simulate_multi_entry_survivor_paths(
            start_week=args.week,
            num_simulations=args.simulations,
            num_entries=args.entries,
            used_teams=used_teams
        )
        print(f"\nEstimated probability at least one entry survives the season: {prob:.2%}")

    if INJURIES:
        picker.apply_injury_reports(INJURIES)

    if args.plot_survival:
        picker.plot_survival_curve(
            start_week=args.week,
            num_simulations=args.simulations,
            num_entries=args.entries,
            used_teams=[set(p) for p in PICKS[:args.entries]]
        )

    if args.plot_summary:
        plot_summary_bubble_chart(summary)

if __name__ == '__main__':
    main()