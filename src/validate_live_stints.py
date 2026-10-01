import re
import time

import pandas as pd

from nba_api.stats.endpoints import (
    boxscoretraditionalv3,
)

from live_stints import (
    build_live_stints,
)


GAME_ID = "0022501188"

CHECKPOINTS = [
    (
        "End Q1",
        720.0,
    ),
    (
        "Halftime",
        1440.0,
    ),
    (
        "End Q3",
        2160.0,
    ),
    (
        "6:00 Q4",
        2520.0,
    ),
    (
        "End regulation",
        2880.0,
    ),
]


def truncate_game(
    df,
    cutoff,
):
    return (
        df.loc[
            pd.to_numeric(
                df[
                    "elapsedGameTime"
                ],
                errors="coerce",
            )
            <= cutoff
        ]
        .copy()
        .reset_index(
            drop=True
        )
    )


def parse_official_minutes(
    value,
):
    if value is None:
        return 0.0

    try:
        if value != value:
            return 0.0
    except Exception:
        pass

    text = str(
        value
    ).strip()

    if not text:
        return 0.0

    match = re.fullmatch(
        r"PT(?:(\d+)M)?"
        r"(\d+(?:\.\d+)?)S",
        text,
    )

    if match is not None:
        minutes = int(
            match.group(1)
            or 0
        )

        seconds = float(
            match.group(2)
        )

        return (
            minutes
            + seconds
            / 60.0
        )

    match = re.fullmatch(
        r"(\d+):(\d+(?:\.\d+)?)",
        text,
    )

    if match is not None:
        return (
            int(
                match.group(1)
            )
            + float(
                match.group(2)
            )
            / 60.0
        )

    try:
        return float(
            text
        )

    except ValueError as error:
        raise ValueError(
            f"Unexpected official minutes "
            f"value: {value!r}"
        ) from error


def fetch_official_box(
    game_id,
    attempts=3,
):
    last_error = None

    for attempt in range(
        1,
        attempts + 1,
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
                    "Traditional box-score "
                    "endpoint returned no tables."
                )

            return frames[0]

        except Exception as error:
            last_error = error

            if attempt < attempts:
                time.sleep(
                    1.5
                    * attempt
                )

    raise last_error


def main():
    path = (
        f"data/processed/"
        f"{GAME_ID}.csv"
    )

    full_df = pd.read_csv(
        path,
        dtype={
            "gameId": str,
        },
    )

    print(
        "Live Stint Validation"
    )

    print(
        "Game:",
        GAME_ID,
    )

    print()

    for (
        label,
        cutoff,
    ) in CHECKPOINTS:
        replay_df = (
            truncate_game(
                full_df,
                cutoff,
            )
        )

        result = (
            build_live_stints(
                replay_df
            )
        )

        expected = float(
            result[
                "expected_team_seconds"
            ]
        )

        home_seconds = float(
            result[
                "team_seconds"
            ][
                result[
                    "home_team"
                ]
            ]
        )

        away_seconds = float(
            result[
                "team_seconds"
            ][
                result[
                    "away_team"
                ]
            ]
        )

        home_pass = (
            abs(
                home_seconds
                - expected
            )
            <= 1e-6
        )

        away_pass = (
            abs(
                away_seconds
                - expected
            )
            <= 1e-6
        )

        if not (
            home_pass
            and away_pass
        ):
            raise RuntimeError(
                f"{label}: team-second "
                f"accounting failed."
            )

        players = (
            result[
                "players"
            ]
        )

        if (
            players[
                "Seconds"
            ]
            < -1e-9
        ).any():
            raise RuntimeError(
                f"{label}: negative player "
                f"seconds detected."
            )

        print(
            f"{label:<16} "
            f"| players={len(players):2d} "
            f"| subs={len(result['substitutions']):2d} "
            f"| team_seconds={expected:.1f} "
            f"| accounting=PASS"
        )

    print()
    print(
        "Fetching official final box score..."
    )

    official = (
        fetch_official_box(
            GAME_ID
        )
    )

    final = (
        build_live_stints(
            truncate_game(
                full_df,
                2880.0,
            )
        )
    )[
        "players"
    ].copy()

    required = {
        "personId",
        "minutes",
        "plusMinusPoints",
    }

    missing = (
        required
        - set(
            official.columns
        )
    )

    if missing:
        raise RuntimeError(
            "Official box score is missing "
            f"expected columns: {sorted(missing)}\n"
            f"Available: {official.columns.tolist()}"
        )

    official = (
        official.loc[
            pd.to_numeric(
                official[
                    "personId"
                ],
                errors="coerce",
            )
            .notna()
        ]
        .copy()
    )

    official[
        "PersonId"
    ] = pd.to_numeric(
        official[
            "personId"
        ],
        errors="raise",
    ).astype(int)

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

    official[
        "OfficialPlusMinus"
    ] = pd.to_numeric(
        official[
            "plusMinusPoints"
        ],
        errors="coerce",
    )

    comparison = (
        final.merge(
            official[
                [
                    "PersonId",
                    "OfficialMinutes",
                    "OfficialPlusMinus",
                ]
            ],
            on="PersonId",
            how="inner",
            validate="one_to_one",
        )
    )

    comparison[
        "MinuteErrorSeconds"
    ] = (
        (
            comparison[
                "Minutes"
            ]
            - comparison[
                "OfficialMinutes"
            ]
        )
        .abs()
        * 60.0
    )

    comparison[
        "PlusMinusMatch"
    ] = (
        comparison[
            "PlusMinus"
        ]
        == comparison[
            "OfficialPlusMinus"
        ]
    )

    minute_pass = (
        comparison[
            "MinuteErrorSeconds"
        ]
        <= 2.0
    )

    plus_minus_pass = (
        comparison[
            "PlusMinusMatch"
        ]
    )

    print()
    print(
        "Final official comparison"
    )

    print(
        "Players compared:",
        len(
            comparison
        ),
    )

    print(
        "Minutes within 2 sec:",
        (
            f"{minute_pass.sum()}/"
            f"{len(comparison)}"
        ),
    )

    print(
        "Plus/minus exact:",
        (
            f"{plus_minus_pass.sum()}/"
            f"{len(comparison)}"
        ),
    )

    failures = (
        comparison.loc[
            ~(
                minute_pass
                & plus_minus_pass
            ),
            [
                "Team",
                "Player",
                "Minutes",
                "OfficialMinutes",
                "MinuteErrorSeconds",
                "PlusMinus",
                "OfficialPlusMinus",
            ],
        ]
        .copy()
    )

    if not failures.empty:
        print()
        print(
            failures.to_string(
                index=False
            )
        )

        raise RuntimeError(
            "Final stint validation did not "
            "match the official box score."
        )

    print()
    print(
        "✓ Live stint validation passed."
    )


if __name__ == "__main__":
    main()
