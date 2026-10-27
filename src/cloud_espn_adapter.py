"""Inactive, network-free adapter prototype; never guesses unresolved identities."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from nba_api.stats.static import teams

from espn_live import ESPNLiveFeedError, normalize_espn_play, normalize_name
from live_analysis import apply_current_season_pregame_smoothing
from preprocess import parse_clock, preprocess_live_game
from reviewed_live_players import candidates
from source_score_ledger import reconciled_scores


class ProviderContextUnavailable(ValueError):
    pass


class ScoreSectionsUnreconciled(ProviderContextUnavailable):
    """Well-identified score sections disagree; acquisition may retry, not guess."""


def validate_canonical(game):
    season = game["season"]
    year = int(season[:4])
    if season != f"{year}-{(year + 1) % 100:02d}":
        raise ProviderContextUnavailable("Invalid canonical season")
    if len(game["gameId"]) != 10 or not game["gameId"].isdigit() or not game["gameId"].startswith("002" + season[2:4]):
        raise ProviderContextUnavailable("A verified regular-season NBA game ID is required")
    date.fromisoformat(game["gameDate"])
    if game["homeTeamId"] == game["awayTeamId"]:
        raise ProviderContextUnavailable("Distinct canonical teams are required")


def _normalize_snapshot(event, summary, canonical):
    """Normalize one complete snapshot, not an append-only event stream.

    Canonical input must come from a verified game catalog, not an ESPN-ID cast.
    Only exact unique bundled player names are accepted; missing/ambiguous IDs
    block analysis rather than becoming zero-attributed player impact.
    """
    validate_canonical(canonical)
    header = summary["header"]
    if str(header["id"]) != str(event["id"]):
        raise ProviderContextUnavailable("Scoreboard/summary event mismatch")
    known_teams = {team["id"]: team for team in teams.get_teams()}
    team_map = None
    expected_year = int(canonical["season"][:4]) + 1
    for payload in (event, header):
        if payload["season"]["type"] != 2 or payload["season"]["year"] != expected_year:
            raise ProviderContextUnavailable("Wrong season or non-regular-season event")
        competition = payload["competitions"][0]
        timestamp = datetime.fromisoformat(competition["date"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ProviderContextUnavailable("Provider date needs an explicit timezone")
        eastern_day = timestamp.astimezone(ZoneInfo("America/New_York")).date().isoformat()
        if eastern_day != canonical["gameDate"]:
            raise ProviderContextUnavailable("Canonical game date mismatch")
        mapping = {}
        for side in ("home", "away"):
            matches = [c for c in competition["competitors"] if c["homeAway"] == side]
            if len(matches) != 1:
                raise ProviderContextUnavailable("Ambiguous game sides")
            competitor = matches[0]
            nba_id = int(canonical[f"{side}TeamId"])
            expected = known_teams[nba_id]
            aliases = {normalize_name(expected["full_name"])}
            if nba_id == 1610612746:
                aliases.add(normalize_name("LA Clippers"))  # Explicit team-name alias, not fuzzy matching.
            if normalize_name(competitor["team"]["displayName"]) not in aliases:
                raise ProviderContextUnavailable("Canonical team mismatch")
            mapping[str(competitor["team"]["id"])] = {"team_id": nba_id, "team_tricode": expected["abbreviation"], "side": side}
        if len(mapping) != 2 or (team_map is not None and mapping != team_map):
            raise ProviderContextUnavailable("Scoreboard/summary team mapping mismatch")
        team_map = mapping
    athlete_map, name_map = {}, {}
    for group in summary["boxscore"]["players"]:
        espn_team = str(group["team"]["id"])
        if espn_team not in team_map:
            raise ProviderContextUnavailable("Unknown box-score team")
        for stats in group["statistics"]:
            for record in stats["athletes"]:
                athlete = record["athlete"]
                ids = candidates(athlete['displayName'], canonical['season'], team_map[espn_team]['team_id'], canonical['gameDate'])
                metadata = {"player_name": athlete["displayName"], "nba_person_id": next(iter(ids)) if len(ids) == 1 else None,
                            "nba_team_id": team_map[espn_team]["team_id"], "team_tricode": team_map[espn_team]["team_tricode"]}
                key = str(athlete["id"])
                if key in athlete_map and athlete_map[key] != metadata:
                    raise ProviderContextUnavailable("Conflicting athlete identity")
                athlete_map[key] = metadata
                name_map[(espn_team, normalize_name(athlete["displayName"]))] = metadata
    plays = summary.get("plays") or []
    if not plays:
        raise ProviderContextUnavailable("Play-by-play is not ready")
    sequences = [int(play["sequenceNumber"]) for play in plays]
    if len(set(sequences)) != len(sequences) or len({str(p["id"]) for p in plays}) != len(plays):
        raise ProviderContextUnavailable("Duplicate/ambiguous play sequence")
    # Preserve the provider's published array order. Corrected plays can retain
    # sequence numbers that are NOT chronological (captured fixture covers this).
    # Validate resulting clock order below rather than sorting by sequence ID.
    rows = []
    for number, play in enumerate(plays, 1):
        if any(not str(play.get(field, "")).isdigit() for field in ("homeScore", "awayScore")):
            raise ProviderContextUnavailable("Missing or invalid play scores")
        if play.get("team", {}).get("id") is not None and str(play["team"]["id"]) not in team_map:
            raise ProviderContextUnavailable("Unknown play team")
        for participant in play.get("participants", []):
            metadata = athlete_map.get(str(participant["athlete"]["id"]))
            if metadata is None or metadata["nba_person_id"] is None:
                raise ProviderContextUnavailable("An involved player needs a reviewed identity mapping")
        row = normalize_espn_play(play, number, team_map, athlete_map, name_map)
        period_length = 720 if row["period"] <= 4 else 300
        if row["period"] < 1 or not 0 <= parse_clock(row["clock"], period_length) <= period_length:
            raise ProviderContextUnavailable("Invalid play period or clock")
        if play.get("participants") and not row["personId"]:
            raise ProviderContextUnavailable("Normalized event lost player identity")
        rows.append(row)
    expected={c['homeAway']:int(c['score']) for c in header['competitions'][0]['competitors']}
    used_ledger=False
    if int(rows[-1]['scoreHome'])!=expected['home'] or int(rows[-1]['scoreAway'])!=expected['away']:
        scores=reconciled_scores(plays,rows,header,summary['boxscore']['players'],team_map,athlete_map)
        if scores is None:
            raise ScoreSectionsUnreconciled('Play timeline is not reconciled to the header score')
        used_ledger=True
        for row,(home,away) in zip(rows,scores):
            row['reportedScoreHome'],row['reportedScoreAway']=row['scoreHome'],row['scoreAway']
            row['scoreHome'],row['scoreAway']=home,away
    raw = pd.DataFrame(rows)
    raw["gameId"] = canonical["gameId"]
    timeline = preprocess_live_game(raw)
    if (not timeline.elapsedGameTime.is_monotonic_increasing or
            int(timeline.homeTeamId.iloc[-1]) != canonical["homeTeamId"] or
            int(timeline.awayTeamId.iloc[-1]) != canonical["awayTeamId"]):
        raise ProviderContextUnavailable("Timeline ordering or home/away state mismatch")
    for competitor in header["competitions"][0]["competitors"]:
        column = "scoreHome" if competitor["homeAway"] == "home" else "scoreAway"
        if int(timeline[column].iloc[-1]) != int(competitor["score"]):
            raise ScoreSectionsUnreconciled("Play timeline is not reconciled to the header score")
    if used_ledger:timeline.attrs['scoreSource']='reconciled_scoring_events'
    return timeline


def normalize_snapshot(event, summary, canonical):
    try:
        return _normalize_snapshot(event, summary, canonical)
    except ProviderContextUnavailable:
        raise
    except (ValueError, KeyError, TypeError, IndexError, ESPNLiveFeedError):
        raise ProviderContextUnavailable("Invalid or incomplete provider snapshot") from None


def verified_pregame_context(canonical, history, schedule, *, complete_through, history_season_type):
    """Count strictly earlier calendar dates; require independently verified catalog coverage.

    complete_through is an upstream verification assertion, NOT derived from the
    maximum observed game date. This function cannot certify a partial catalog.
    """
    validate_canonical(canonical)
    day = date.fromisoformat(canonical["gameDate"])
    if history_season_type != "Regular Season" or date.fromisoformat(complete_through) < day - timedelta(days=1):
        raise ProviderContextUnavailable("Prior regular-season coverage is not verified")
    if not history.season.eq(canonical["season"]).all() or not schedule.season.eq(canonical["season"]).all() or not schedule.seasonType.eq("Regular Season").all():
        raise ProviderContextUnavailable("Mixed season context")
    if history.duplicated(["gameId", "team"]).any() or schedule.gameId.duplicated().any() or not history.teamWin.isin([0, 1]).all():
        raise ProviderContextUnavailable("Invalid or duplicate record source")
    prefix = "002" + canonical["season"][2:4]
    if not history.gameId.astype(str).str.startswith(prefix).all() or not schedule.gameId.astype(str).str.startswith(prefix).all():
        raise ProviderContextUnavailable("Non-regular-season game IDs in context")
    before = pd.to_datetime(history.gameDate).dt.date < day
    prior_schedule = schedule.loc[pd.to_datetime(schedule.gameDate).dt.date < day]
    known = {team["id"]: team["abbreviation"] for team in teams.get_teams()}
    context = {"homeTeamId": canonical["homeTeamId"], "awayTeamId": canonical["awayTeamId"]}
    for side in ("home", "away"):
        team_id = canonical[f"{side}TeamId"]
        expected = prior_schedule.loc[prior_schedule.homeTeamId.eq(team_id) | prior_schedule.awayTeamId.eq(team_id)]
        covered = history.loc[before & history.team.eq(known[team_id])]
        if set(expected.gameId) != set(covered.gameId):
            raise ProviderContextUnavailable("Missing or unexpected prior games")
        expected_dates = dict(zip(expected.gameId, pd.to_datetime(expected.gameDate).dt.date))
        if any(expected_dates[row.gameId] != pd.Timestamp(row.gameDate).date() for row in covered.itertuples()):
            raise ProviderContextUnavailable("Prior game dates disagree with verified catalog")
        wins, losses = int(covered.teamWin.sum()), int(len(covered) - covered.teamWin.sum())
        context[f"{side}PreGameWins"], context[f"{side}PreGameLosses"] = wins, losses
        context[f"{side}PreGameWinPct"] = wins / (wins + losses) if wins + losses else 0.5
    context["strengthDifference"] = context["homePreGameWinPct"] - context["awayPreGameWinPct"]
    return apply_current_season_pregame_smoothing(context, canonical["season"], "Regular Season")
