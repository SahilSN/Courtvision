"""Bounded overnight eligibility; never relabel a game's scheduled date."""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

OVERNIGHT_END_HOUR = 6


def eligible_game_date(game_date, now=None):
    """Today, or yesterday strictly before 06:00 Eastern (DST-aware)."""
    now = now or datetime.now(timezone.utc)
    try:
        if now.tzinfo is None:
            return False
        eastern = now.astimezone(ZoneInfo('America/New_York'))
        day = date.fromisoformat(game_date)
        if day.isoformat() != game_date:
            return False
        return (day == eastern.date() or
                (eastern.hour < OVERNIGHT_END_HOUR and
                 day == eastern.date() - timedelta(days=1)))
    except (ValueError, TypeError, OverflowError):
        return False


def overnight_game(game_date, now):
    return game_date != now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
