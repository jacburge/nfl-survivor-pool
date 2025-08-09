"""
INJURIES is a dictionary mapping team names to Elo penalties (positive numbers).
These penalties represent the estimated impact of injuries for each team in Elo points.

How to use:
- Assign a higher penalty for more impactful injuries (e.g., starting QB out = 50+ points).
- Moderate penalty for key skill players (RB/WR/TE) or multiple starters out (15–30 points).
- Lower penalty for less impactful injuries (OL, DL, secondary, etc.) or minor injuries (5–10 points).
- If no significant injuries, omit the team or set penalty to 0.

Examples:
INJURIES = {
    "Buffalo Bills": 50,   # Starting QB out
    "Dallas Cowboys": 20,  # Top RB out
    "San Francisco 49ers": 10,  # Two starting OL out
    # Add more teams as needed
}

Update this file each week with the latest injury news.
"""

INJURIES = {
    # Example:
    # "Buffalo Bills": 50,
    # "Dallas Cowboys": 20,
}