"""Offline build step from trusted local caches; never used by hosted requests."""

import json
import pickle
from pathlib import Path

from player_rating_dataset import load_cached_box_players, load_wpa_summary
from published_replay import PILOT_PATH, load_replay
from nba_api.stats.static import teams
from replay_collection import GAME_IDS, load_collection


def export_game(game_id, season='2025-26', cache_root=None, destination=None):
    root = Path(cache_root) if cache_root is not None else Path(__file__).resolve().parents[1]
    from replay_catalog import valid_identity
    valid_identity(game_id,season,f'{season[:4]}-10-01')
    with (root / f"data/cache/analysis/v1_v7/{season}_{game_id}_top3.pkl").open("rb") as handle:
        cached = pickle.load(handle)
    result = cached["result"]
    if cached["cache_version"] != "v1_v7" or not result["is_final"] or result["game_id"] != game_id:
        raise ValueError("Wrong/nonfinal source cache")
    columns = ["elapsedGameTime", "period", "clock", "scoreHome", "scoreAway", "description", "winProbability"]
    timeline = result["timeline"][columns].copy()
    box = load_cached_box_players(game_id,root/'data/cache/box_score/v1')
    if box is None:
        raise ValueError("Missing offline box score")
    impact = load_wpa_summary(game_id,root/'results')
    if impact is None:
        raise ValueError('Missing offline player impact')
    names = {team["id"]: team["abbreviation"] for team in teams.get_teams()}
    home, away = names[result["home_team_id"]], names[result["away_team_id"]]
    if not box.gameId.astype(str).str.zfill(10).eq(game_id).all():
        raise ValueError("Wrong box-score identity")
    swings = []
    for side in ("home", "away"):
        for _, row in result[f"{side}_swings"].iterrows():
            swings.append({"Side": home if side == "home" else away, "Period": int(row.period),
                           "Clock": row.clock, "Play": row.description,
                           "Home probability change (pp)": round(float(row.probabilityChange) * 100, 2)})
    valid_identity(game_id,season,str(result['game_date']))
    data = {"schemaVersion": 1, "model": "Frozen V7", "gameId": game_id, "season": season,
            'completed':True,'seasonType':'Regular Season',
            "date": result["game_date"], "home": {"tricode": home, "score": result["final_home_score"]},
            "away": {"tricode": away, "score": result["final_away_score"]},
            "timeline": json.loads(timeline.to_json(orient="records", double_precision=15)),
            "turningPoints": swings,
            "playerImpact": json.loads(impact[["playerName", "teamTricode", "events", "netWPAPoints"]].to_json(orient="records")),
            "boxScore": json.loads(box[["fullName", "teamTricode", "minutesDisplay", "points", "reboundsTotal", "assists", "steals", "blocks", "turnovers"]].to_json(orient="records"))}
    destination = Path(destination) if destination is not None else PILOT_PATH.parent / f"{game_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, allow_nan=False, separators=(",", ":")) + "\n")
    load_replay(temporary)
    temporary.replace(destination)
    print(f"Validated offline replay: {destination} ({destination.stat().st_size:,} bytes)")
    return destination


def main():
    for game_id in GAME_IDS:
        export_game(game_id)
    load_collection()


if __name__ == "__main__":
    main()
