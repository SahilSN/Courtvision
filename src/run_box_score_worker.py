from __future__ import annotations

import argparse
import json
import pickle
import traceback
from pathlib import Path

from nba_api.stats.endpoints import commonteamroster

from box_score import fetch_box_score


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

BOX_CACHE_VERSION = "v1"
POSITION_CACHE_VERSION = "v1"

BOX_CACHE_DIR = (
    ROOT_DIR
    / "data"
    / "cache"
    / "box_score"
    / BOX_CACHE_VERSION
)

POSITION_CACHE_DIR = (
    ROOT_DIR
    / "data"
    / "cache"
    / "positions"
    / POSITION_CACHE_VERSION
)

RUNTIME_DIR = (
    ROOT_DIR
    / "results"
    / ".runtime"
    / "box_score"
)


def normalize_position(value):
    if value is None:
        return "—"

    try:
        if value != value:
            return "—"
    except Exception:
        pass

    position = str(value).strip()

    aliases = {
        "Guard": "G",
        "Forward": "F",
        "Center": "C",
        "Guard-Forward": "G-F",
        "Forward-Guard": "F-G",
        "Forward-Center": "F-C",
        "Center-Forward": "C-F",
    }

    return aliases.get(
        position,
        position or "—",
    )


def status_path(game_id):
    return (
        RUNTIME_DIR
        / f"{game_id}.json"
    )


def write_status(
    game_id,
    payload,
):
    RUNTIME_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = status_path(
        game_id
    )

    temp = path.with_suffix(
        ".json.tmp"
    )

    temp.write_text(
        json.dumps(
            payload,
            indent=2,
        )
    )

    temp.replace(
        path
    )


def save_pickle(
    path,
    payload,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temp.open(
        "wb"
    ) as handle:
        pickle.dump(
            payload,
            handle,
            protocol=pickle.HIGHEST_PROTOCOL,
        )

    temp.replace(
        path
    )


def cache_team_positions(
    team_id,
    season,
):
    cache_path = (
        POSITION_CACHE_DIR
        / f"{season}_{int(team_id)}.pkl"
    )

    if cache_path.exists():
        return

    endpoint = (
        commonteamroster
        .CommonTeamRoster(
            team_id=int(team_id),
            season=season,
            timeout=60,
        )
    )

    frames = (
        endpoint.get_data_frames()
    )

    positions = {}

    if frames:
        roster = frames[0]

        for _, row in roster.iterrows():
            player_id = row.get(
                "PLAYER_ID"
            )

            if (
                player_id is None
                or player_id != player_id
            ):
                continue

            positions[
                int(player_id)
            ] = normalize_position(
                row.get(
                    "POSITION"
                )
            )

    save_pickle(
        cache_path,
        {
            "cache_version":
                POSITION_CACHE_VERSION,

            "team_id":
                int(team_id),

            "season":
                season,

            "positions":
                positions,
        },
    )


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "game_id",
    )

    parser.add_argument(
        "--season",
        required=True,
    )

    return parser.parse_args()


def main():
    args = parse_args()

    game_id = str(
        args.game_id
    )

    write_status(
        game_id,
        {
            "state":
                "running",

            "game_id":
                game_id,

            "season":
                args.season,
        },
    )

    try:
        box_score = fetch_box_score(
            game_id
        )

        # Cache complete historical box score.
        save_pickle(
            BOX_CACHE_DIR
            / f"{game_id}.pkl",
            {
                "cache_version":
                    BOX_CACHE_VERSION,

                "game_id":
                    game_id,

                "box_score":
                    box_score,
            },
        )

        # The box score itself is now complete.
        #
        # Do not block completion on CommonTeamRoster.
        # Position enrichment is supplemental and must never
        # delay the historical box-score result.

        write_status(
            game_id,
            {
                "state":
                    "completed",

                "game_id":
                    game_id,

                "season":
                    args.season,
            },
        )

    except Exception as error:
        write_status(
            game_id,
            {
                "state":
                    "failed",

                "game_id":
                    game_id,

                "season":
                    args.season,

                "error":
                    str(error),

                "traceback":
                    traceback.format_exc(),
            },
        )

        raise


if __name__ == "__main__":
    main()
