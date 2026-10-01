import argparse
import re
import time
from pathlib import Path

import pandas as pd

from nba_api.stats.endpoints import (
    boxscoretraditionalv3,
)

from live_stints import build_live_stints


PROCESSED_DIR = Path(
    "data/processed"
)

RESULTS_DIR = Path(
    "results"
)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--games",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=0.75,
    )

    return parser.parse_args()


def parse_official_minutes(
    value,
):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    text = str(
        value
    ).strip()

    if not text:
        return None

    iso = re.fullmatch(
        r"PT(?:(\d+)H)?"
        r"(?:(\d+)M)?"
        r"(?:(\d+(?:\.\d+)?)S)?",
        text,
    )

    if iso is not None:
        hours = int(
            iso.group(1)
            or 0
        )

        minutes = int(
            iso.group(2)
            or 0
        )

        seconds = float(
            iso.group(3)
            or 0
        )

        return (
            hours * 60
            + minutes
            + seconds / 60.0
        )

    clock = re.fullmatch(
        r"(\d+):(\d+(?:\.\d+)?)",
        text,
    )

    if clock is not None:
        return (
            int(
                clock.group(1)
            )
            + float(
                clock.group(2)
            )
            / 60.0
        )

    try:
        return float(
            text
        )
    except ValueError:
        return None


def fetch_official_box(
    game_id,
):
    last_error = None

    for attempt in range(
        3
    ):
        try:
            endpoint = (
                boxscoretraditionalv3
                .BoxScoreTraditionalV3(
                    game_id=game_id,
                    timeout=60,
                )
            )

            frames = (
                endpoint
                .get_data_frames()
            )

            if not frames:
                raise RuntimeError(
                    "NBA box-score endpoint "
                    "returned no tables."
                )

            df = (
                frames[0]
                .copy()
            )

            required = {
                "personId",
                "minutes",
                "plusMinusPoints",
            }

            missing = (
                required
                - set(
                    df.columns
                )
            )

            if missing:
                raise RuntimeError(
                    "Official box score missing "
                    f"{sorted(missing)}"
                )

            return df

        except Exception as error:
            last_error = error

            if attempt < 2:
                time.sleep(
                    2.0
                    * (
                        attempt + 1
                    )
                )

    raise RuntimeError(
        f"Official box fetch failed: "
        f"{last_error}"
    )


def inspect_game(
    path,
):
    try:
        df = pd.read_csv(
            path,
            dtype={
                "gameId":
                    str,
            },
        )

    except Exception:
        return None

    if df.empty:
        return None

    periods = pd.to_numeric(
        df.get(
            "period"
        ),
        errors="coerce",
    )

    max_period = int(
        periods.max()
    )

    descriptions = (
        df.get(
            "description",
            pd.Series(
                dtype=str
            ),
        )
        .fillna("")
        .astype(str)
        .str.upper()
    )

    has_ejection = (
        descriptions
        .str.contains(
            "EJECTION",
            regex=False,
        )
        .any()
    )

    has_flagrant = (
        descriptions
        .str.contains(
            "FLAGRANT",
            regex=False,
        )
        .any()
    )

    has_double_tech = (
        descriptions
        .str.contains(
            "DOUBLE.TECHNICAL",
            regex=False,
        )
        .any()
    )

    edge_score = (
        (100 if max_period > 4 else 0)
        + (30 if has_ejection else 0)
        + (20 if has_flagrant else 0)
        + (
            10
            if has_double_tech
            else 0
        )
    )

    return {
        "path":
            path,

        "game_id":
            path.stem,

        "max_period":
            max_period,

        "edge_score":
            edge_score,

        "overtime":
            max_period > 4,

        "ejection":
            has_ejection,

        "flagrant":
            has_flagrant,
    }


def select_games(
    count,
):
    candidates = []

    for path in sorted(
        PROCESSED_DIR.glob(
            "*.csv"
        )
    ):
        result = inspect_game(
            path
        )

        if result is not None:
            candidates.append(
                result
            )

    candidates.sort(
        key=lambda row: (
            -row[
                "edge_score"
            ],
            row[
                "game_id"
            ],
        )
    )

    return candidates[
        :count
    ]


def validate_game(
    game,
):
    game_id = (
        game[
            "game_id"
        ]
    )

    game_df = pd.read_csv(
        game[
            "path"
        ],
        dtype={
            "gameId":
                str,
        },
    )

    stint_result = (
        build_live_stints(
            game_df
        )
    )

    reconstructed = (
        stint_result[
            "players"
        ][
            [
                "Team",
                "PersonId",
                "Player",
                "Minutes",
                "PlusMinus",
            ]
        ]
        .copy()
    )

    reconstructed[
        "PersonId"
    ] = pd.to_numeric(
        reconstructed[
            "PersonId"
        ],
        errors="coerce",
    )

    reconstructed = (
        reconstructed
        .dropna(
            subset=[
                "PersonId",
            ]
        )
        .copy()
    )

    reconstructed[
        "PersonId"
    ] = (
        reconstructed[
            "PersonId"
        ]
        .astype(int)
    )

    official = (
        fetch_official_box(
            game_id
        )
    )

    official[
        "OfficialMinutes"
    ] = (
        official[
            "minutes"
        ]
        .apply(
            parse_official_minutes
        )
    )

    official = (
        official.loc[
            official[
                "OfficialMinutes"
            ]
            .notna()
            & (
                official[
                    "OfficialMinutes"
                ]
                > 0
            ),
            [
                "personId",
                "OfficialMinutes",
                "plusMinusPoints",
            ],
        ]
        .copy()
        .rename(
            columns={
                "personId":
                    "PersonId",

                "plusMinusPoints":
                    "OfficialPlusMinus",
            }
        )
    )

    official[
        "PersonId"
    ] = pd.to_numeric(
        official[
            "PersonId"
        ],
        errors="coerce",
    )

    official = (
        official
        .dropna(
            subset=[
                "PersonId",
            ]
        )
        .copy()
    )

    official[
        "PersonId"
    ] = (
        official[
            "PersonId"
        ]
        .astype(int)
    )

    merged = (
        reconstructed
        .merge(
            official,
            on="PersonId",
            how="outer",
            indicator=True,
        )
    )

    missing_identity = (
        merged[
            "_merge"
        ]
        != "both"
    )

    compared = (
        merged.loc[
            ~missing_identity
        ]
        .copy()
    )

    compared[
        "MinuteErrorSeconds"
    ] = (
        (
            compared[
                "Minutes"
            ]
            - compared[
                "OfficialMinutes"
            ]
        )
        .abs()
        * 60.0
    )

    compared[
        "MinutePass"
    ] = (
        compared[
            "MinuteErrorSeconds"
        ]
        <= 2.0
    )

    compared[
        "PlusMinusPass"
    ] = (
        pd.to_numeric(
            compared[
                "PlusMinus"
            ],
            errors="coerce",
        )
        == pd.to_numeric(
            compared[
                "OfficialPlusMinus"
            ],
            errors="coerce",
        )
    )

    identity_pass = (
        not missing_identity.any()
    )

    minutes_pass = (
        identity_pass
        and compared[
            "MinutePass"
        ].all()
    )

    plus_minus_pass = (
        identity_pass
        and compared[
            "PlusMinusPass"
        ].all()
    )

    return {
        "gameId":
            game_id,

        "maxPeriod":
            game[
                "max_period"
            ],

        "overtime":
            game[
                "overtime"
            ],

        "ejection":
            game[
                "ejection"
            ],

        "flagrant":
            game[
                "flagrant"
            ],

        "reconstructedPlayers":
            len(
                reconstructed
            ),

        "officialPlayers":
            len(
                official
            ),

        "playersCompared":
            len(
                compared
            ),

        "identityPass":
            bool(
                identity_pass
            ),

        "minutesPass":
            bool(
                minutes_pass
            ),

        "plusMinusPass":
            bool(
                plus_minus_pass
            ),

        "maxMinuteErrorSeconds":
            (
                float(
                    compared[
                        "MinuteErrorSeconds"
                    ].max()
                )
                if not compared.empty
                else None
            ),

        "minuteMismatches":
            int(
                (
                    ~compared[
                        "MinutePass"
                    ]
                ).sum()
            ),

        "plusMinusMismatches":
            int(
                (
                    ~compared[
                        "PlusMinusPass"
                    ]
                ).sum()
            ),

        "PASS":
            bool(
                identity_pass
                and minutes_pass
                and plus_minus_pass
            ),
    }


def main():
    args = parse_args()

    games = select_games(
        args.games
    )

    if not games:
        raise RuntimeError(
            "No processed games found."
        )

    print(
        "Live Stint Batch Validation"
    )

    print(
        "Games selected:",
        len(
            games
        ),
    )

    print()

    rows = []

    for index, game in enumerate(
        games,
        start=1,
    ):
        game_id = (
            game[
                "game_id"
            ]
        )

        try:
            result = validate_game(
                game
            )

            rows.append(
                result
            )

            status = (
                "PASS"
                if result[
                    "PASS"
                ]
                else "FAIL"
            )

            print(
                f"[{index:02d}/{len(games):02d}] "
                f"{game_id} | "
                f"P{result['maxPeriod']} | "
                f"players={result['playersCompared']} | "
                f"MIN bad={result['minuteMismatches']} | "
                f"+/- bad={result['plusMinusMismatches']} | "
                f"{status}"
            )

        except Exception as error:
            rows.append(
                {
                    "gameId":
                        game_id,

                    "maxPeriod":
                        game[
                            "max_period"
                        ],

                    "overtime":
                        game[
                            "overtime"
                        ],

                    "ejection":
                        game[
                            "ejection"
                        ],

                    "flagrant":
                        game[
                            "flagrant"
                        ],

                    "PASS":
                        False,

                    "error":
                        str(
                            error
                        ),
                }
            )

            print(
                f"[{index:02d}/{len(games):02d}] "
                f"{game_id} | ERROR | "
                f"{error}"
            )

        time.sleep(
            args.sleep
        )

    results = pd.DataFrame(
        rows
    )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        RESULTS_DIR
        / "live_stints_batch_validation.csv"
    )

    results.to_csv(
        output_path,
        index=False,
    )

    passed = int(
        results[
            "PASS"
        ]
        .fillna(False)
        .sum()
    )

    total = len(
        results
    )

    print()
    print(
        "=" * 72
    )

    print(
        f"Games passed: {passed}/{total}"
    )

    if (
        "minutesPass"
        in results.columns
    ):
        print(
            "Minutes exact/tolerance passes:",
            int(
                results[
                    "minutesPass"
                ]
                .fillna(False)
                .sum()
            ),
            "/",
            total,
        )

    if (
        "plusMinusPass"
        in results.columns
    ):
        print(
            "Plus/minus exact passes:",
            int(
                results[
                    "plusMinusPass"
                ]
                .fillna(False)
                .sum()
            ),
            "/",
            total,
        )

    print(
        "Saved:",
        output_path,
    )

    failures = (
        results.loc[
            ~results[
                "PASS"
            ].fillna(
                False
            )
        ]
    )

    if not failures.empty:
        print()
        print(
            "Failures:"
        )

        columns = [
            column
            for column
            in [
                "gameId",
                "maxPeriod",
                "overtime",
                "ejection",
                "flagrant",
                "minuteMismatches",
                "plusMinusMismatches",
                "error",
            ]
            if column
            in failures.columns
        ]

        print(
            failures[
                columns
            ]
            .to_string(
                index=False
            )
        )

        raise RuntimeError(
            "Batch stint validation "
            "found failures."
        )

    print()
    print(
        "✓ All selected games passed "
        "live stint validation."
    )


if __name__ == "__main__":
    main()
