from __future__ import annotations

import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from player_impact import (
    analyze_player_impact,
    load_model,
    load_season_data,
)


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

RESULTS_DIR = (
    ROOT_DIR
    / "results"
)

RUNTIME_DIR = (
    RESULTS_DIR
    / ".runtime"
    / "player_impact"
)

REQUEST_DIR = (
    RUNTIME_DIR
    / "requests"
)

SERVICE_STATUS_PATH = (
    RUNTIME_DIR
    / "service.json"
)


def now_iso():
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def write_json_atomic(
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

    temp.write_text(
        json.dumps(
            payload,
            indent=2,
        )
    )

    temp.replace(
        path
    )


def game_status_path(
    game_id,
):
    return (
        RUNTIME_DIR
        / f"{game_id}.json"
    )


def summary_path(
    game_id,
):
    return (
        RESULTS_DIR
        / (
            f"player_wpa_v3_"
            f"{game_id}_summary.csv"
        )
    )


def main():
    RUNTIME_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    REQUEST_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    pid = os.getpid()

    write_json_atomic(
        SERVICE_STATUS_PATH,
        {
            "state":
                "warming",

            "pid":
                pid,

            "started_at":
                now_iso(),
        },
    )

    # --------------------------------------------------------
    # Frozen V7 artifacts stay resident for the lifetime
    # of this service.
    # --------------------------------------------------------

    model, scaler, device = (
        load_model()
    )

    # Season frames are loaded lazily and then retained.
    season_cache = {}

    write_json_atomic(
        SERVICE_STATUS_PATH,
        {
            "state":
                "ready",

            "pid":
                pid,

            "device":
                str(device),

            "started_at":
                now_iso(),
        },
    )

    while True:
        requests = sorted(
            REQUEST_DIR.glob(
                "*.json"
            ),
            key=lambda path:
                path.stat().st_mtime,
        )

        if not requests:
            time.sleep(
                0.10
            )
            continue

        request_path = (
            requests[0]
        )

        try:
            request = json.loads(
                request_path.read_text()
            )

            game_id = str(
                request[
                    "game_id"
                ]
            )

            season = str(
                request[
                    "season"
                ]
            )

            top_k = int(
                request.get(
                    "top_k",
                    10,
                )
            )

            force = bool(
                request.get(
                    "force",
                    False,
                )
            )

            # Another render/process may have completed this
            # game before the queued request was reached.
            if (
                summary_path(
                    game_id
                ).exists()
                and not force
            ):
                write_json_atomic(
                    game_status_path(
                        game_id
                    ),
                    {
                        "state":
                            "completed",

                        "pid":
                            pid,

                        "game_id":
                            game_id,

                        "season":
                            season,

                        "finished_at":
                            now_iso(),
                    },
                )

                request_path.unlink(
                    missing_ok=True
                )

                continue

            write_json_atomic(
                game_status_path(
                    game_id
                ),
                {
                    "state":
                        "running",

                    "pid":
                        pid,

                    "game_id":
                        game_id,

                    "season":
                        season,

                    "started_at":
                        now_iso(),
                },
            )

            if season not in season_cache:
                season_cache[
                    season
                ] = (
                    load_season_data(
                        season
                    )
                )

            analyze_player_impact(
                game_id=game_id,
                season=season,
                top_k=top_k,
                season_df=(
                    season_cache[
                        season
                    ]
                ),
                model=model,
                scaler=scaler,
                device=device,
            )

            if not summary_path(
                game_id
            ).exists():
                raise RuntimeError(
                    "Player-impact analysis completed "
                    "without producing the expected "
                    "summary CSV."
                )

            write_json_atomic(
                game_status_path(
                    game_id
                ),
                {
                    "state":
                        "completed",

                    "pid":
                        pid,

                    "game_id":
                        game_id,

                    "season":
                        season,

                    "finished_at":
                        now_iso(),
                },
            )

        except Exception as error:
            game_id = str(
                request.get(
                    "game_id",
                    "unknown",
                )
                if "request" in locals()
                else "unknown"
            )

            if game_id != "unknown":
                write_json_atomic(
                    game_status_path(
                        game_id
                    ),
                    {
                        "state":
                            "failed",

                        "pid":
                            pid,

                        "game_id":
                            game_id,

                        "finished_at":
                            now_iso(),

                        "error":
                            str(error),

                        "traceback":
                            traceback.format_exc(),
                    },
                )

        finally:
            request_path.unlink(
                missing_ok=True
            )


if __name__ == "__main__":
    main()
