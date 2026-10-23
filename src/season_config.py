"""Canonical Courtvision current-season configuration."""


CURRENT_SEASON = "2026-27"
CURRENT_SEASON_TYPE = "Regular Season"


def current_season_label():
    return (
        f"{CURRENT_SEASON} "
        f"{CURRENT_SEASON_TYPE}"
    )
