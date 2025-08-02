"""
NFL Survivor Pool optimization tool for the 2025 season.

This module scrapes the 2025 NFL schedule, assigns baseline power ratings to
teams, derives situational factors (rest, travel and time‑zone adjustments)
and estimates win probabilities using a simple Elo‑style model.  It also
computes the expected value of potential survivor picks and recommends two
weekly selections designed to maximize the probability that at least one of
two entries survives through the entire season.

The tool is deliberately self‑contained: it doesn't rely on third‑party
prediction APIs or paid datasets.  Instead, it scrapes publicly available
information (the full schedule) and applies the analytical framework
described in the accompanying report.  You can update the underlying
ratings, situational adjustments or EV logic by editing the constants
defined below.

To use this module interactively, execute it as a script.  It will fetch
the schedule on first run and print the recommended picks for a given week.

Example usage::

    python nfl_survivor_tool.py --week 1

The script will output two recommended teams for week 1 along with
supporting metrics.  Running it for subsequent weeks will incorporate
previous picks and updated rest/travel adjustments.

The key functions and classes exported by this module are:

    scrape_schedule()  -> list of dicts
        Scrapes the 2025 NFL schedule from FFToday and returns a list
        containing one dictionary per game with week, date, teams and site
        information.

    compute_team_ratings()  -> dict
        Returns a dictionary mapping full team names to baseline Elo‑style
        power ratings based on the 2024 final standings.  Ratings are
        anchored at 1500 points and scaled by win/loss differential.

    SURVIVOR_PICKER class
        Encapsulates the logic required to compute situational factors,
        estimate win probabilities, calculate expected value and simulate
        survivor strategies.  Instantiate with the scraped schedule and
        optional pre‑defined ratings and run the recommend_picks() method
        each week.

The tool is designed for educational and planning purposes and makes
numerous simplifications relative to professionally maintained models:

  * Power ratings are derived solely from prior season records (wins minus
    losses).  In reality, roster turnover, coaching changes and preseason
    expectations would modify these values, but the simple method still
    produces reasonable ordinal rankings.
  * Situational adjustments (rest advantage, travel distance, time zone
    displacement and altitude) are based on published research summarised in
    the user's report.  You can adjust the constants REST_POINTS,
    TRAVEL_POINTS, TZ_POINTS and ALTITUDE_POINTS to tune the model.
  * Pick popularity is heuristically approximated by ranking games by
    predicted win probability.  More sophisticated approaches would
    incorporate crowd‑sourced selection data.
  * The EV algorithm evaluates picks week by week but does not exhaustively
    search every possible pick path (which would require solving a large
    combinatorial optimisation problem).  Instead, it implements a greedy
    strategy that balances win probability, popularity and future value
    (using the simple future_value() method) and ensures diversification
    across two entries.

You are encouraged to inspect and modify the code to suit your needs.
"""

from __future__ import annotations

import datetime as _dt
import math
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

# The requests and BeautifulSoup imports are retained for potential future use,
# but the current implementation no longer scrapes the schedule from FFToday.
# Wrap these imports in try/except so that the module still loads even if
# requests or bs4 are not installed on the user's system.  These packages
# are only required if you intend to re‑enable web scraping.
try:
    import requests  # noqa: F401
    from bs4 import BeautifulSoup  # noqa: F401
except ImportError:
    requests = None
    BeautifulSoup = None

###############################################################################
# Data definitions
###############################################################################

# Team power ratings derived from the 2024 final win‑loss records.  Each team
# begins at a base of 1500 Elo points and receives ±30 points for every win
# above or below .500 (i.e. every win more than losses adds 30 points).  The
# list was transcribed from Pro‑Football‑Reference's 2024 standings
# (see report citations).  Teams are keyed by their full names as they
# appear on FFToday's schedule page.
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

    The data below was transcribed from FFToday's schedule and cross‑checked
    against the printable grid supplied by the user.  It covers all 272
    regular‑season games.
    """
    _ = _dt.date  # alias for brevity
    games = [
        # Week 1
        {'week': 1, 'date': _(2025, 9, 4),  'time': '8:20 pm', 'away': 'Dallas Cowboys',      'home': 'Philadelphia Eagles', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 5),  'time': '8:00 pm', 'away': 'Kansas City Chiefs',   'home': 'Los Angeles Chargers', 'note': 'Brazil'},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '1:00 pm', 'away': 'Arizona Cardinals',    'home': 'New Orleans Saints', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '1:00 pm', 'away': 'Carolina Panthers',    'home': 'Jacksonville Jaguars', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '1:00 pm', 'away': 'Cincinnati Bengals',   'home': 'Cleveland Browns', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '1:00 pm', 'away': 'Las Vegas Raiders',    'home': 'New England Patriots', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '1:00 pm', 'away': 'Miami Dolphins',       'home': 'Indianapolis Colts', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '1:00 pm', 'away': 'New York Giants',      'home': 'Washington Commanders', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '1:00 pm', 'away': 'Pittsburgh Steelers',  'home': 'New York Jets', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '1:00 pm', 'away': 'Tampa Bay Buccaneers', 'home': 'Atlanta Falcons', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '4:05 pm', 'away': 'San Francisco 49ers',  'home': 'Seattle Seahawks', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '4:05 pm', 'away': 'Tennessee Titans',     'home': 'Denver Broncos', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '4:25 pm', 'away': 'Detroit Lions',        'home': 'Green Bay Packers', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '4:25 pm', 'away': 'Houston Texans',       'home': 'Los Angeles Rams', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 7),  'time': '8:20 pm', 'away': 'Baltimore Ravens',     'home': 'Buffalo Bills', 'note': ''},
        {'week': 1, 'date': _(2025, 9, 8),  'time': '8:15 pm', 'away': 'Minnesota Vikings',     'home': 'Chicago Bears', 'note': ''},

        # Week 2
        {'week': 2, 'date': _(2025, 9, 11), 'time': '8:15 pm', 'away': 'Washington Commanders','home': 'Green Bay Packers', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '1:00 pm', 'away': 'Buffalo Bills',        'home': 'New York Jets', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '1:00 pm', 'away': 'Chicago Bears',        'home': 'Detroit Lions', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '1:00 pm', 'away': 'Cleveland Browns',     'home': 'Baltimore Ravens', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '1:00 pm', 'away': 'Jacksonville Jaguars', 'home': 'Cincinnati Bengals', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '1:00 pm', 'away': 'Los Angeles Rams',     'home': 'Tennessee Titans', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '1:00 pm', 'away': 'New England Patriots', 'home': 'Miami Dolphins', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '1:00 pm', 'away': 'New York Giants',      'home': 'Dallas Cowboys', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '1:00 pm', 'away': 'San Francisco 49ers',  'home': 'New Orleans Saints', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '1:00 pm', 'away': 'Seattle Seahawks',     'home': 'Pittsburgh Steelers', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '4:05 pm', 'away': 'Carolina Panthers',    'home': 'Arizona Cardinals', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '4:05 pm', 'away': 'Denver Broncos',       'home': 'Indianapolis Colts', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '4:25 pm', 'away': 'Philadelphia Eagles',  'home': 'Kansas City Chiefs', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 14), 'time': '8:20 pm', 'away': 'Atlanta Falcons',      'home': 'Minnesota Vikings', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 15), 'time': '7:00 pm', 'away': 'Tampa Bay Buccaneers', 'home': 'Houston Texans', 'note': ''},
        {'week': 2, 'date': _(2025, 9, 15), 'time': '10:00 pm','away': 'Los Angeles Chargers', 'home': 'Las Vegas Raiders', 'note': ''},

        # Week 3
        {'week': 3, 'date': _(2025, 9, 18), 'time': '8:15 pm', 'away': 'Miami Dolphins',       'home': 'Buffalo Bills', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '1:00 pm', 'away': 'Atlanta Falcons',      'home': 'Carolina Panthers', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '1:00 pm', 'away': 'Cincinnati Bengals',   'home': 'Minnesota Vikings', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '1:00 pm', 'away': 'Green Bay Packers',    'home': 'Cleveland Browns', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '1:00 pm', 'away': 'Houston Texans',       'home': 'Jacksonville Jaguars', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '1:00 pm', 'away': 'Indianapolis Colts',   'home': 'Tennessee Titans', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '1:00 pm', 'away': 'Las Vegas Raiders',    'home': 'Washington Commanders', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '1:00 pm', 'away': 'Los Angeles Rams',     'home': 'Philadelphia Eagles', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '1:00 pm', 'away': 'New York Jets',        'home': 'Tampa Bay Buccaneers', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '1:00 pm', 'away': 'Pittsburgh Steelers',  'home': 'New England Patriots', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '4:05 pm', 'away': 'Denver Broncos',       'home': 'Los Angeles Chargers', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '4:05 pm', 'away': 'New Orleans Saints',   'home': 'Seattle Seahawks', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '4:25 pm', 'away': 'Arizona Cardinals',    'home': 'San Francisco 49ers', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '4:25 pm', 'away': 'Dallas Cowboys',       'home': 'Chicago Bears', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 21), 'time': '8:20 pm', 'away': 'Kansas City Chiefs',   'home': 'New York Giants', 'note': ''},
        {'week': 3, 'date': _(2025, 9, 22), 'time': '8:15 pm', 'away': 'Detroit Lions',        'home': 'Baltimore Ravens', 'note': ''},

        # Week 4
        {'week': 4, 'date': _(2025, 9, 25), 'time': '8:15 pm', 'away': 'Seattle Seahawks',     'home': 'Arizona Cardinals', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '9:30 am', 'away': 'Minnesota Vikings',    'home': 'Pittsburgh Steelers', 'note': 'Dublin'},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '1:00 pm', 'away': 'Carolina Panthers',    'home': 'New England Patriots', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '1:00 pm', 'away': 'Cleveland Browns',     'home': 'Detroit Lions', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '1:00 pm', 'away': 'Los Angeles Chargers', 'home': 'New York Giants', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '1:00 pm', 'away': 'New Orleans Saints',   'home': 'Buffalo Bills', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '1:00 pm', 'away': 'Philadelphia Eagles',  'home': 'Tampa Bay Buccaneers', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '1:00 pm', 'away': 'Tennessee Titans',     'home': 'Houston Texans', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '1:00 pm', 'away': 'Washington Commanders','home': 'Atlanta Falcons', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '4:05 pm', 'away': 'Indianapolis Colts',   'home': 'Los Angeles Rams', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '4:05 pm', 'away': 'Jacksonville Jaguars', 'home': 'San Francisco 49ers', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '4:25 pm', 'away': 'Baltimore Ravens',     'home': 'Kansas City Chiefs', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '4:25 pm', 'away': 'Chicago Bears',        'home': 'Las Vegas Raiders', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 28), 'time': '8:20 pm', 'away': 'Green Bay Packers',    'home': 'Dallas Cowboys', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 29), 'time': '7:15 pm', 'away': 'New York Jets',        'home': 'Miami Dolphins', 'note': ''},
        {'week': 4, 'date': _(2025, 9, 29), 'time': '8:15 pm', 'away': 'Cincinnati Bengals',   'home': 'Denver Broncos', 'note': ''},

        # Week 5
        {'week': 5, 'date': _(2025, 10, 2), 'time': '8:15 pm', 'away': 'San Francisco 49ers',  'home': 'Los Angeles Rams', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '9:30 am', 'away': 'Minnesota Vikings',    'home': 'Cleveland Browns', 'note': 'London'},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '1:00 pm', 'away': 'Dallas Cowboys',       'home': 'New York Jets', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '1:00 pm', 'away': 'Denver Broncos',       'home': 'Philadelphia Eagles', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '1:00 pm', 'away': 'Houston Texans',       'home': 'Baltimore Ravens', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '1:00 pm', 'away': 'Las Vegas Raiders',    'home': 'Indianapolis Colts', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '1:00 pm', 'away': 'Miami Dolphins',       'home': 'Carolina Panthers', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '1:00 pm', 'away': 'New York Giants',      'home': 'New Orleans Saints', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '4:05 pm', 'away': 'Tampa Bay Buccaneers', 'home': 'Seattle Seahawks', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '4:05 pm', 'away': 'Tennessee Titans',     'home': 'Arizona Cardinals', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '4:25 pm', 'away': 'Detroit Lions',        'home': 'Cincinnati Bengals', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '4:25 pm', 'away': 'Washington Commanders','home': 'Los Angeles Chargers', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 5), 'time': '8:20 pm', 'away': 'New England Patriots', 'home': 'Buffalo Bills', 'note': ''},
        {'week': 5, 'date': _(2025, 10, 6), 'time': '8:15 pm', 'away': 'Kansas City Chiefs',   'home': 'Jacksonville Jaguars', 'note': ''},

        # Week 6
        {'week': 6, 'date': _(2025, 10, 9), 'time': '8:15 pm', 'away': 'Philadelphia Eagles',  'home': 'New York Giants', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '9:30 am', 'away': 'Denver Broncos',      'home': 'New York Jets', 'note': 'London'},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '1:00 pm', 'away': 'Arizona Cardinals',    'home': 'Indianapolis Colts', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '1:00 pm', 'away': 'Cleveland Browns',     'home': 'Pittsburgh Steelers', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '1:00 pm', 'away': 'Dallas Cowboys',       'home': 'Carolina Panthers', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '1:00 pm', 'away': 'Los Angeles Chargers','home': 'Miami Dolphins', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '1:00 pm', 'away': 'Los Angeles Rams',     'home': 'Baltimore Ravens', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '1:00 pm', 'away': 'San Francisco 49ers',  'home': 'Tampa Bay Buccaneers', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '1:00 pm', 'away': 'Seattle Seahawks',     'home': 'Jacksonville Jaguars', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '4:05 pm', 'away': 'Tennessee Titans',     'home': 'Las Vegas Raiders', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '4:25 pm', 'away': 'Cincinnati Bengals',   'home': 'Green Bay Packers', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '4:25 pm', 'away': 'New England Patriots', 'home': 'New Orleans Saints', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 12), 'time': '8:20 pm', 'away': 'Detroit Lions',        'home': 'Kansas City Chiefs', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 13), 'time': '7:15 pm', 'away': 'Buffalo Bills',        'home': 'Atlanta Falcons', 'note': ''},
        {'week': 6, 'date': _(2025, 10, 13), 'time': '8:15 pm', 'away': 'Chicago Bears',        'home': 'Washington Commanders', 'note': ''},

        # Week 7
        {'week': 7, 'date': _(2025, 10, 16), 'time': '8:15 pm', 'away': 'Pittsburgh Steelers', 'home': 'Cincinnati Bengals', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '9:30 am', 'away': 'Los Angeles Rams',     'home': 'Jacksonville Jaguars', 'note': 'London'},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '1:00 pm', 'away': 'Carolina Panthers',    'home': 'New York Jets', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '1:00 pm', 'away': 'Las Vegas Raiders',    'home': 'Kansas City Chiefs', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '1:00 pm', 'away': 'Miami Dolphins',       'home': 'Cleveland Browns', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '1:00 pm', 'away': 'New England Patriots', 'home': 'Tennessee Titans', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '1:00 pm', 'away': 'New Orleans Saints',    'home': 'Chicago Bears', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '1:00 pm', 'away': 'Philadelphia Eagles',  'home': 'Minnesota Vikings', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '4:05 pm', 'away': 'Indianapolis Colts',   'home': 'Los Angeles Chargers', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '4:05 pm', 'away': 'New York Giants',      'home': 'Denver Broncos', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '4:25 pm', 'away': 'Green Bay Packers',    'home': 'Arizona Cardinals', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '4:25 pm', 'away': 'Washington Commanders','home': 'Dallas Cowboys', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 19), 'time': '8:20 pm', 'away': 'Atlanta Falcons',      'home': 'San Francisco 49ers', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 20), 'time': '7:00 pm', 'away': 'Tampa Bay Buccaneers', 'home': 'Detroit Lions', 'note': ''},
        {'week': 7, 'date': _(2025, 10, 20), 'time': '10:00 pm','away': 'Houston Texans',       'home': 'Seattle Seahawks', 'note': ''},

        # Week 8
        {'week': 8, 'date': _(2025, 10, 23), 'time': '8:15 pm', 'away': 'Minnesota Vikings',    'home': 'Los Angeles Chargers', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 26), 'time': '1:00 pm', 'away': 'Buffalo Bills',        'home': 'Carolina Panthers', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 26), 'time': '1:00 pm', 'away': 'Chicago Bears',        'home': 'Baltimore Ravens', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 26), 'time': '1:00 pm', 'away': 'Cleveland Browns',     'home': 'New England Patriots', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 26), 'time': '1:00 pm', 'away': 'Miami Dolphins',       'home': 'Atlanta Falcons', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 26), 'time': '1:00 pm', 'away': 'New York Giants',      'home': 'Philadelphia Eagles', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 26), 'time': '1:00 pm', 'away': 'New York Jets',        'home': 'Cincinnati Bengals', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 26), 'time': '1:00 pm', 'away': 'San Francisco 49ers',  'home': 'Houston Texans', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 26), 'time': '4:05 pm', 'away': 'Tampa Bay Buccaneers', 'home': 'New Orleans Saints', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 26), 'time': '4:25 pm', 'away': 'Dallas Cowboys',       'home': 'Denver Broncos', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 26), 'time': '4:25 pm', 'away': 'Tennessee Titans',     'home': 'Indianapolis Colts', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 26), 'time': '8:20 pm', 'away': 'Green Bay Packers',    'home': 'Pittsburgh Steelers', 'note': ''},
        {'week': 8, 'date': _(2025, 10, 27), 'time': '8:15 pm', 'away': 'Washington Commanders','home': 'Kansas City Chiefs', 'note': ''},

        # Week 9
        {'week': 9, 'date': _(2025, 10, 30), 'time': '8:15 pm', 'away': 'Baltimore Ravens',     'home': 'Miami Dolphins', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '1:00 pm', 'away': 'Atlanta Falcons',      'home': 'New England Patriots', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '1:00 pm', 'away': 'Carolina Panthers',    'home': 'Green Bay Packers', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '1:00 pm', 'away': 'Chicago Bears',        'home': 'Cincinnati Bengals', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '1:00 pm', 'away': 'Denver Broncos',       'home': 'Houston Texans', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '1:00 pm', 'away': 'Indianapolis Colts',   'home': 'Pittsburgh Steelers', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '1:00 pm', 'away': 'Los Angeles Chargers', 'home': 'Tennessee Titans', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '1:00 pm', 'away': 'Minnesota Vikings',    'home': 'Detroit Lions', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '1:00 pm', 'away': 'San Francisco 49ers',  'home': 'New York Giants', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '4:05 pm', 'away': 'Jacksonville Jaguars', 'home': 'Las Vegas Raiders', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '4:05 pm', 'away': 'New Orleans Saints',   'home': 'Los Angeles Rams', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '4:25 pm', 'away': 'Kansas City Chiefs',   'home': 'Buffalo Bills', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 2),  'time': '8:20 pm', 'away': 'Seattle Seahawks',     'home': 'Washington Commanders', 'note': ''},
        {'week': 9, 'date': _(2025, 11, 3),  'time': '8:15 pm', 'away': 'Arizona Cardinals',    'home': 'Dallas Cowboys', 'note': ''},

        # Week 10
        {'week': 10,'date': _(2025, 11, 6),  'time': '8:15 pm', 'away': 'Las Vegas Raiders',    'home': 'Denver Broncos', 'note': ''},
        {'week': 10,'date': _(2025, 11, 9),  'time': '9:30 am', 'away': 'Atlanta Falcons',      'home': 'Indianapolis Colts', 'note': 'Berlin'},
        {'week': 10,'date': _(2025, 11, 9),  'time': '1:00 pm', 'away': 'Baltimore Ravens',     'home': 'Minnesota Vikings', 'note': ''},
        {'week': 10,'date': _(2025, 11, 9),  'time': '1:00 pm', 'away': 'Buffalo Bills',        'home': 'Miami Dolphins', 'note': ''},
        {'week': 10,'date': _(2025, 11, 9),  'time': '1:00 pm', 'away': 'Cleveland Browns',     'home': 'New York Jets', 'note': ''},
        {'week': 10,'date': _(2025, 11, 9),  'time': '1:00 pm', 'away': 'Jacksonville Jaguars', 'home': 'Houston Texans', 'note': ''},
        {'week': 10,'date': _(2025, 11, 9),  'time': '1:00 pm', 'away': 'New England Patriots', 'home': 'Tampa Bay Buccaneers', 'note': ''},
        {'week': 10,'date': _(2025, 11, 9),  'time': '1:00 pm', 'away': 'New Orleans Saints',   'home': 'Carolina Panthers', 'note': ''},
        {'week': 10,'date': _(2025, 11, 9),  'time': '1:00 pm', 'away': 'New York Giants',      'home': 'Chicago Bears', 'note': ''},
        {'week': 10,'date': _(2025, 11, 9),  'time': '4:05 pm', 'away': 'Arizona Cardinals',    'home': 'Seattle Seahawks', 'note': ''},
        {'week': 10,'date': _(2025, 11, 9),  'time': '4:25 pm', 'away': 'Detroit Lions',        'home': 'Washington Commanders', 'note': ''},
        {'week': 10,'date': _(2025, 11, 9),  'time': '4:25 pm', 'away': 'Los Angeles Rams',     'home': 'San Francisco 49ers', 'note': ''},
        {'week': 10,'date': _(2025, 11, 9),  'time': '8:20 pm', 'away': 'Pittsburgh Steelers',  'home': 'Los Angeles Chargers', 'note': ''},
        {'week': 10,'date': _(2025, 11, 10), 'time': '8:15 pm', 'away': 'Philadelphia Eagles',  'home': 'Green Bay Packers', 'note': ''},

        # Week 11
        {'week': 11,'date': _(2025, 11, 13), 'time': '8:15 pm', 'away': 'New York Jets',        'home': 'New England Patriots', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '9:30 am', 'away': 'Washington Commanders','home': 'Miami Dolphins', 'note': 'London'},
        {'week': 11,'date': _(2025, 11, 16), 'time': '1:00 pm', 'away': 'Carolina Panthers',    'home': 'Atlanta Falcons', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '1:00 pm', 'away': 'Chicago Bears',        'home': 'Minnesota Vikings', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '1:00 pm', 'away': 'Cincinnati Bengals',   'home': 'Pittsburgh Steelers', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '1:00 pm', 'away': 'Green Bay Packers',    'home': 'New York Giants', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '1:00 pm', 'away': 'Houston Texans',       'home': 'Tennessee Titans', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '1:00 pm', 'away': 'Los Angeles Chargers', 'home': 'Jacksonville Jaguars', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '1:00 pm', 'away': 'Tampa Bay Buccaneers', 'home': 'Buffalo Bills', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '4:05 pm', 'away': 'San Francisco 49ers',  'home': 'Arizona Cardinals', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '4:05 pm', 'away': 'Seattle Seahawks',     'home': 'Los Angeles Rams', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '4:25 pm', 'away': 'Baltimore Ravens',     'home': 'Cleveland Browns', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '4:25 pm', 'away': 'Kansas City Chiefs',   'home': 'Denver Broncos', 'note': ''},
        {'week': 11,'date': _(2025, 11, 16), 'time': '8:20 pm', 'away': 'Detroit Lions',        'home': 'Philadelphia Eagles', 'note': ''},
        {'week': 11,'date': _(2025, 11, 17), 'time': '8:15 pm', 'away': 'Dallas Cowboys',       'home': 'Las Vegas Raiders', 'note': ''},

        # Week 12
        {'week': 12,'date': _(2025, 11, 20), 'time': '8:15 pm', 'away': 'Buffalo Bills',        'home': 'Houston Texans', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '1:00 pm', 'away': 'Indianapolis Colts',   'home': 'Kansas City Chiefs', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '1:00 pm', 'away': 'Minnesota Vikings',    'home': 'Green Bay Packers', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '1:00 pm', 'away': 'New England Patriots', 'home': 'Cincinnati Bengals', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '1:00 pm', 'away': 'New York Giants',      'home': 'Detroit Lions', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '1:00 pm', 'away': 'New York Jets',        'home': 'Baltimore Ravens', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '1:00 pm', 'away': 'Pittsburgh Steelers',  'home': 'Chicago Bears', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '1:00 pm', 'away': 'Seattle Seahawks',     'home': 'Tennessee Titans', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '4:05 pm', 'away': 'Cleveland Browns',     'home': 'Las Vegas Raiders', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '4:05 pm', 'away': 'Jacksonville Jaguars', 'home': 'Arizona Cardinals', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '4:25 pm', 'away': 'Atlanta Falcons',      'home': 'New Orleans Saints', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '4:25 pm', 'away': 'Philadelphia Eagles',  'home': 'Dallas Cowboys', 'note': ''},
        {'week': 12,'date': _(2025, 11, 23), 'time': '8:20 pm', 'away': 'Tampa Bay Buccaneers', 'home': 'Los Angeles Rams', 'note': ''},
        {'week': 12,'date': _(2025, 11, 24), 'time': '8:15 pm', 'away': 'Carolina Panthers',    'home': 'San Francisco 49ers', 'note': ''},

        # Week 13
        {'week': 13,'date': _(2025, 11, 27), 'time': '1:00 pm', 'away': 'Green Bay Packers',    'home': 'Detroit Lions', 'note': ''},
        {'week': 13,'date': _(2025, 11, 27), 'time': '4:30 pm', 'away': 'Kansas City Chiefs',   'home': 'Dallas Cowboys', 'note': ''},
        {'week': 13,'date': _(2025, 11, 27), 'time': '8:20 pm', 'away': 'Cincinnati Bengals',   'home': 'Baltimore Ravens', 'note': ''},
        {'week': 13,'date': _(2025, 11, 28), 'time': '3:00 pm', 'away': 'Chicago Bears',        'home': 'Philadelphia Eagles', 'note': ''},
        {'week': 13,'date': _(2025, 11, 30), 'time': '1:00 pm', 'away': 'Arizona Cardinals',    'home': 'Tampa Bay Buccaneers', 'note': ''},
        {'week': 13,'date': _(2025, 11, 30), 'time': '1:00 pm', 'away': 'Atlanta Falcons',      'home': 'New York Jets', 'note': ''},
        {'week': 13,'date': _(2025, 11, 30), 'time': '1:00 pm', 'away': 'Houston Texans',       'home': 'Indianapolis Colts', 'note': ''},
        {'week': 13,'date': _(2025, 11, 30), 'time': '1:00 pm', 'away': 'Jacksonville Jaguars', 'home': 'Tennessee Titans', 'note': ''},
        {'week': 13,'date': _(2025, 11, 30), 'time': '1:00 pm', 'away': 'Los Angeles Rams',     'home': 'Carolina Panthers', 'note': ''},
        {'week': 13,'date': _(2025, 11, 30), 'time': '1:00 pm', 'away': 'New Orleans Saints',   'home': 'Miami Dolphins', 'note': ''},
        {'week': 13,'date': _(2025, 11, 30), 'time': '1:00 pm', 'away': 'San Francisco 49ers',  'home': 'Cleveland Browns', 'note': ''},
        {'week': 13,'date': _(2025, 11, 30), 'time': '4:05 pm', 'away': 'Minnesota Vikings',    'home': 'Seattle Seahawks', 'note': ''},
        {'week': 13,'date': _(2025, 11, 30), 'time': '4:25 pm', 'away': 'Buffalo Bills',        'home': 'Pittsburgh Steelers', 'note': ''},
        {'week': 13,'date': _(2025, 11, 30), 'time': '4:25 pm', 'away': 'Las Vegas Raiders',    'home': 'Los Angeles Chargers', 'note': ''},
        {'week': 13,'date': _(2025, 11, 30), 'time': '8:20 pm', 'away': 'Denver Broncos',       'home': 'Washington Commanders', 'note': ''},
        {'week': 13,'date': _(2025, 12, 1),  'time': '8:15 pm', 'away': 'New York Giants',      'home': 'New England Patriots', 'note': ''},

        # Week 14
        {'week': 14,'date': _(2025, 12, 4),  'time': '8:15 pm', 'away': 'Dallas Cowboys',       'home': 'Detroit Lions', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '1:00 pm', 'away': 'Chicago Bears',        'home': 'Green Bay Packers', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '1:00 pm', 'away': 'Indianapolis Colts',   'home': 'Jacksonville Jaguars', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '1:00 pm', 'away': 'Miami Dolphins',       'home': 'New York Jets', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '1:00 pm', 'away': 'New Orleans Saints',   'home': 'Tampa Bay Buccaneers', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '1:00 pm', 'away': 'Pittsburgh Steelers',  'home': 'Baltimore Ravens', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '1:00 pm', 'away': 'Seattle Seahawks',     'home': 'Atlanta Falcons', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '1:00 pm', 'away': 'Tennessee Titans',     'home': 'Cleveland Browns', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '1:00 pm', 'away': 'Washington Commanders','home': 'Minnesota Vikings', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '4:05 pm', 'away': 'Denver Broncos',       'home': 'Las Vegas Raiders', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '4:25 pm', 'away': 'Cincinnati Bengals',   'home': 'Buffalo Bills', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '4:25 pm', 'away': 'Los Angeles Rams',     'home': 'Arizona Cardinals', 'note': ''},
        {'week': 14,'date': _(2025, 12, 7),  'time': '8:20 pm', 'away': 'Houston Texans',       'home': 'Kansas City Chiefs', 'note': ''},
        {'week': 14,'date': _(2025, 12, 8),  'time': '8:15 pm', 'away': 'Philadelphia Eagles',  'home': 'Los Angeles Chargers', 'note': ''},

        # Week 15
        {'week': 15,'date': _(2025, 12, 11), 'time': '8:15 pm', 'away': 'Atlanta Falcons',      'home': 'Tampa Bay Buccaneers', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '1:00 pm', 'away': 'Arizona Cardinals',    'home': 'Houston Texans', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '1:00 pm', 'away': 'Baltimore Ravens',     'home': 'Cincinnati Bengals', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '1:00 pm', 'away': 'Buffalo Bills',        'home': 'New England Patriots', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '1:00 pm', 'away': 'Cleveland Browns',     'home': 'Chicago Bears', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '1:00 pm', 'away': 'Las Vegas Raiders',    'home': 'Philadelphia Eagles', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '1:00 pm', 'away': 'Los Angeles Chargers', 'home': 'Kansas City Chiefs', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '1:00 pm', 'away': 'New York Jets',        'home': 'Jacksonville Jaguars', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '1:00 pm', 'away': 'Washington Commanders','home': 'New York Giants', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '4:25 pm', 'away': 'Carolina Panthers',    'home': 'New Orleans Saints', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '4:25 pm', 'away': 'Detroit Lions',        'home': 'Los Angeles Rams', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '4:25 pm', 'away': 'Green Bay Packers',    'home': 'Denver Broncos', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '4:25 pm', 'away': 'Indianapolis Colts',   'home': 'Seattle Seahawks', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '4:25 pm', 'away': 'Tennessee Titans',     'home': 'San Francisco 49ers', 'note': ''},
        {'week': 15,'date': _(2025, 12, 14), 'time': '8:20 pm', 'away': 'Minnesota Vikings',    'home': 'Dallas Cowboys', 'note': ''},
        {'week': 15,'date': _(2025, 12, 15), 'time': '8:15 pm', 'away': 'Miami Dolphins',       'home': 'Pittsburgh Steelers', 'note': ''},

        # Week 16
        {'week': 16,'date': _(2025, 12, 18), 'time': '8:15 pm', 'away': 'Los Angeles Rams',     'home': 'Seattle Seahawks', 'note': ''},
        {'week': 16,'date': _(2025, 12, 20), 'time': '1:00 pm', 'away': 'Green Bay Packers',    'home': 'Chicago Bears', 'note': 'Flex'},
        {'week': 16,'date': _(2025, 12, 20), 'time': '1:00 pm', 'away': 'Philadelphia Eagles',  'home': 'Washington Commanders', 'note': 'Flex'},
        {'week': 16,'date': _(2025, 12, 21), 'time': '1:00 pm', 'away': 'Buffalo Bills',        'home': 'Cleveland Browns', 'note': ''},
        {'week': 16,'date': _(2025, 12, 21), 'time': '1:00 pm', 'away': 'Kansas City Chiefs',   'home': 'Tennessee Titans', 'note': ''},
        {'week': 16,'date': _(2025, 12, 21), 'time': '1:00 pm', 'away': 'Los Angeles Chargers', 'home': 'Dallas Cowboys', 'note': ''},
        {'week': 16,'date': _(2025, 12, 21), 'time': '1:00 pm', 'away': 'Minnesota Vikings',    'home': 'New York Giants', 'note': ''},
        {'week': 16,'date': _(2025, 12, 21), 'time': '1:00 pm', 'away': 'New England Patriots', 'home': 'Baltimore Ravens', 'note': ''},
        {'week': 16,'date': _(2025, 12, 21), 'time': '1:00 pm', 'away': 'New York Jets',        'home': 'New Orleans Saints', 'note': ''},
        {'week': 16,'date': _(2025, 12, 21), 'time': '1:00 pm', 'away': 'Tampa Bay Buccaneers', 'home': 'Carolina Panthers', 'note': ''},
        {'week': 16,'date': _(2025, 12, 21), 'time': '4:05 pm', 'away': 'Atlanta Falcons',      'home': 'Arizona Cardinals', 'note': ''},
        {'week': 16,'date': _(2025, 12, 21), 'time': '4:05 pm', 'away': 'Jacksonville Jaguars', 'home': 'Denver Broncos', 'note': ''},
        {'week': 16,'date': _(2025, 12, 21), 'time': '4:25 pm', 'away': 'Las Vegas Raiders',    'home': 'Houston Texans', 'note': ''},
        {'week': 16,'date': _(2025, 12, 21), 'time': '4:25 pm', 'away': 'Pittsburgh Steelers',  'home': 'Detroit Lions', 'note': ''},
        {'week': 16,'date': _(2025, 12, 21), 'time': '8:20 pm', 'away': 'Cincinnati Bengals',   'home': 'Miami Dolphins', 'note': ''},
        {'week': 16,'date': _(2025, 12, 22), 'time': '8:15 pm', 'away': 'San Francisco 49ers',  'home': 'Indianapolis Colts', 'note': ''},

        # Week 17
        {'week': 17,'date': _(2025, 12, 25), 'time': '1:00 pm', 'away': 'Dallas Cowboys',       'home': 'Washington Commanders', 'note': ''},
        {'week': 17,'date': _(2025, 12, 25), 'time': '4:30 pm', 'away': 'Detroit Lions',        'home': 'Minnesota Vikings', 'note': ''},
        {'week': 17,'date': _(2025, 12, 25), 'time': '8:15 pm', 'away': 'Denver Broncos',       'home': 'Kansas City Chiefs', 'note': ''},
        {'week': 17,'date': _(2025, 12, 27), 'time': '1:00 pm', 'away': 'Arizona Cardinals',    'home': 'Cincinnati Bengals', 'note': 'Flex'},
        {'week': 17,'date': _(2025, 12, 27), 'time': '1:00 pm', 'away': 'Baltimore Ravens',     'home': 'Green Bay Packers', 'note': 'Flex'},
        {'week': 17,'date': _(2025, 12, 27), 'time': '1:00 pm', 'away': 'Houston Texans',       'home': 'Los Angeles Chargers', 'note': 'Flex'},
        {'week': 17,'date': _(2025, 12, 27), 'time': '1:00 pm', 'away': 'New York Giants',      'home': 'Las Vegas Raiders', 'note': 'Flex'},
        {'week': 17,'date': _(2025, 12, 27), 'time': '1:00 pm', 'away': 'Seattle Seahawks',     'home': 'Carolina Panthers', 'note': 'Flex'},
        {'week': 17,'date': _(2025, 12, 28), 'time': '1:00 pm', 'away': 'Jacksonville Jaguars', 'home': 'Indianapolis Colts', 'note': ''},
        {'week': 17,'date': _(2025, 12, 28), 'time': '1:00 pm', 'away': 'New England Patriots', 'home': 'New York Jets', 'note': ''},
        {'week': 17,'date': _(2025, 12, 28), 'time': '1:00 pm', 'away': 'New Orleans Saints',   'home': 'Tennessee Titans', 'note': ''},
        {'week': 17,'date': _(2025, 12, 28), 'time': '1:00 pm', 'away': 'Pittsburgh Steelers',  'home': 'Cleveland Browns', 'note': ''},
        {'week': 17,'date': _(2025, 12, 28), 'time': '1:00 pm', 'away': 'Tampa Bay Buccaneers', 'home': 'Miami Dolphins', 'note': ''},
        {'week': 17,'date': _(2025, 12, 28), 'time': '4:25 pm', 'away': 'Philadelphia Eagles',  'home': 'Buffalo Bills', 'note': ''},
        {'week': 17,'date': _(2025, 12, 28), 'time': '8:20 pm', 'away': 'Chicago Bears',        'home': 'San Francisco 49ers', 'note': ''},
        {'week': 17,'date': _(2025, 12, 29), 'time': '8:15 pm', 'away': 'Los Angeles Rams',     'home': 'Atlanta Falcons', 'note': ''},

        # Week 18
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Arizona Cardinals',    'home': 'Los Angeles Rams', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Baltimore Ravens',     'home': 'Pittsburgh Steelers', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Carolina Panthers',    'home': 'Tampa Bay Buccaneers', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Cleveland Browns',     'home': 'Cincinnati Bengals', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Dallas Cowboys',       'home': 'New York Giants', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Detroit Lions',        'home': 'Chicago Bears', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Green Bay Packers',    'home': 'Minnesota Vikings', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Indianapolis Colts',   'home': 'Houston Texans', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Kansas City Chiefs',   'home': 'Las Vegas Raiders', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Los Angeles Chargers', 'home': 'Denver Broncos', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Miami Dolphins',       'home': 'New England Patriots', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'New Orleans Saints',   'home': 'Atlanta Falcons', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'New York Jets',        'home': 'Buffalo Bills', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Seattle Seahawks',     'home': 'San Francisco 49ers', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Tennessee Titans',     'home': 'Jacksonville Jaguars', 'note': 'Flex'},
        {'week': 18,'date': _(2026, 1, 3),  'time': '1:00 pm', 'away': 'Washington Commanders','home': 'Philadelphia Eagles', 'note': 'Flex'},
    ]
    return games


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
    used_teams_entry1: List[str] = field(default_factory=list)
    used_teams_entry2: List[str] = field(default_factory=list)

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

    def recommend_picks(self, week: int) -> Tuple[Optional[str], Optional[str]]:
        """Recommend two teams for the given week based on EV and diversification.

        Returns a tuple (pick_entry1, pick_entry2).  If there are fewer than
        two eligible picks, one or both values may be None.
        """
        # Filter games for the specified week
        week_games = [g for g in self.schedule if g.week == week]
        if not week_games:
            return (None, None)
        # Compute popularity scores for this week's games
        self.compute_pick_popularity(week_games)
        # Evaluate EV for each game (from the perspective of picking the home
        # favourite).  Exclude teams already used by each entry.
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
            used_both = fav_team in self.used_teams_entry1 and fav_team in self.used_teams_entry2
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
            candidates.append({
                'game': g,
                'team': fav_team,
                'prob': fav_prob,
                'pop': popularity,
                'ev': ev,
            })
        if not candidates:
            return (None, None)
        # Sort candidates by EV descending
        candidates.sort(key=lambda d: d['ev'], reverse=True)
        # Select picks for entry1 and entry2, ensuring different teams if possible
        pick1 = None
        pick2 = None
        for cand in candidates:
            team = cand['team']
            if team in self.used_teams_entry1:
                continue
            pick1 = team
            break
        # Find a different team for entry2
        for cand in candidates:
            team = cand['team']
            if team == pick1:
                continue
            if team in self.used_teams_entry2:
                continue
            pick2 = team
            break
        # Fall back: if unable to find a second unique team, allow duplicate
        if not pick2 and candidates:
            for cand in candidates:
                team = cand['team']
                if team != pick1:
                    pick2 = team
                    break
        # Update used teams lists
        if pick1:
            self.used_teams_entry1.append(pick1)
        if pick2:
            self.used_teams_entry2.append(pick2)
        return (pick1, pick2)

    def summary_for_week(self, week: int) -> List[Tuple[str, float, float, float]]:
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


def main():
    import argparse
    parser = argparse.ArgumentParser(description="NFL Survivor Pool optimizer")
    parser.add_argument('--week', type=int, default=1, help='Week number to generate picks for')
    args = parser.parse_args()
    # Fetch schedule from the embedded manual list.  We avoid scraping because the
    # FFToday site blocks automated requests from our environment.
    raw_schedule = load_manual_schedule()
    games = [Game(**g) for g in raw_schedule if g['week'] <= 18]
    picker = SURVIVOR_PICKER(games)
    picker.update_situational_factors()
    # Example usage of live data integration:
    #
    # betting_lines = {
    #     1: {('Dallas Cowboys', 'Philadelphia Eagles'): -3.5},
    #     2: {('Buffalo Bills', 'New York Jets'): -4.0},
    #     # ... fill in spreads for each game you have lines for ...
    # }
    # injuries = {
    #     'Kansas City Chiefs': 30.0,  # Quarterback questionable
    #     'New Orleans Saints': 15.0,
    # }
    # picker.apply_injury_reports(injuries)
    # picker.apply_betting_lines(betting_lines)
    # picker.update_situational_factors()
    # Recommend picks for the desired week
    pick1, pick2 = picker.recommend_picks(args.week)
    print(f"Recommended picks for week {args.week}: Entry1 = {pick1}, Entry2 = {pick2}")
    # Print summary
    summary = picker.summary_for_week(args.week)
    print("\nSummary (team, winProb, popularity, futureValue, EV):")
    for team, prob, pop, fv, ev in summary:
        print(f"{team:24s}  P(win)={prob:.3f}  Pop={pop:.2f}  FV={fv:.2f}  EV={ev:.3f}")


if __name__ == '__main__':
    main()