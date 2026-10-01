import argparse
import re
import time
from pathlib import Path

import pandas as pd

from box_score import fetch_traditional_box_score
from replay_box_score import (
    build_replay_box_score,
)


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

DEFAULT_PROCESSED_DIR = (
    ROOT_DIR
    / "data"
    / "processed"
)

DEFAULT_OUTPUT_DIR = (
    ROOT_DIR
    / "results"
    / "replay_box_score_validation"
)


STAT_COLUMNS = [
    "PTS",
    "REB",
    "AST",
    "STL",
    "BLK",
    "TO",
    "FGM",
    "FGA",
    "3PM",
    "3PA",
    "FTM",
    "FTA",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Validate Courtvision's replay/live "
            "box-score reconstruction against "
            "official completed NBA box scores."
        )
    )

    parser.add_argument(
        "--count",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DEFAULT_PROCESSED_DIR,
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )

    parser.add_argument(
        "--sleep",
        type=float,
        default=0.6,
        help=(
            "Delay between official NBA API "
            "box-score requests."
        ),
    )

    return parser.parse_args()


def canonical_name(
    value,
):
    if value is None:
        return ""

    value = str(
        value
    ).strip()

    value = re.sub(
        r"^[A-Za-z]\.\s+",
        "",
        value,
    )

    value = (
        value
        .lower()
        .replace(
            "’",
            "'",
        )
    )

    value = re.sub(
        r"[^a-z0-9'\-\s]",
        "",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    return value


def surname_key(
    value,
):
    """
    Match PBP names such as:
      Antetokounmpo
      Porter Jr.
      G. Antetokounmpo

    against official full names such as:
      Giannis Antetokounmpo
      Kevin Porter Jr.
    """
    value = canonical_name(
        value
    )

    if not value:
        return ""

    tokens = value.split()

    suffixes = {
        "jr",
        "sr",
        "ii",
        "iii",
        "iv",
        "v",
    }

    if (
        len(tokens) >= 2
        and tokens[-1]
        in suffixes
    ):
        return (
            tokens[-2]
            + " "
            + tokens[-1]
        )

    return tokens[-1]


def parse_shooting_line(
    value,
):
    value = str(
        value
    ).strip()

    match = re.fullmatch(
        r"(\d+)-(\d+)",
        value,
    )

    if match is None:
        raise ValueError(
            f"Unexpected shooting line: {value!r}"
        )

    return (
        int(
            match.group(1)
        ),
        int(
            match.group(2)
        ),
    )


def replay_to_numeric(
    replay_df,
):
    rows = []

    for _, row in (
        replay_df.iterrows()
    ):
        fgm, fga = (
            parse_shooting_line(
                row["FG"]
            )
        )

        three_pm, three_pa = (
            parse_shooting_line(
                row["3PT"]
            )
        )

        ftm, fta = (
            parse_shooting_line(
                row["FT"]
            )
        )

        person_id = pd.to_numeric(
            row.get(
                "PersonId",
                None,
            ),
            errors="coerce",
        )

        rows.append(
            {
                "teamTricode":
                    str(
                        row["Team"]
                    ),

                "personId":
                    (
                        None
                        if pd.isna(
                            person_id
                        )
                        else int(
                            person_id
                        )
                    ),

                "displayName":
                    str(
                        row["Player"]
                    ),

                "PTS":
                    int(
                        row["PTS"]
                    ),

                "REB":
                    int(
                        row["REB"]
                    ),

                "AST":
                    int(
                        row["AST"]
                    ),

                "STL":
                    int(
                        row["STL"]
                    ),

                "BLK":
                    int(
                        row["BLK"]
                    ),

                "TO":
                    int(
                        row["TO"]
                    ),

                "FGM":
                    fgm,

                "FGA":
                    fga,

                "3PM":
                    three_pm,

                "3PA":
                    three_pa,

                "FTM":
                    ftm,

                "FTA":
                    fta,
            }
        )

    return pd.DataFrame(
        rows
    )



def official_to_numeric(
    players,
):
    mappings = {
        "PTS":
            "points",

        "REB":
            "reboundsTotal",

        "AST":
            "assists",

        "STL":
            "steals",

        "BLK":
            "blocks",

        "TO":
            "turnovers",

        "FGM":
            "fieldGoalsMade",

        "FGA":
            "fieldGoalsAttempted",

        "3PM":
            "threePointersMade",

        "3PA":
            "threePointersAttempted",

        "FTM":
            "freeThrowsMade",

        "FTA":
            "freeThrowsAttempted",
    }

    rows = []

    for _, row in (
        players.iterrows()
    ):
        first_name = str(
            row.get(
                "firstName",
                "",
            )
            or ""
        ).strip()

        family_name = str(
            row.get(
                "familyName",
                "",
            )
            or ""
        ).strip()

        full_name = (
            f"{first_name} "
            f"{family_name}"
        ).strip()

        output = {
            "teamTricode":
                str(
                    row[
                        "teamTricode"
                    ]
                ),

            "personId":
                int(
                    row[
                        "personId"
                    ]
                ),

            "displayName":
                full_name,
        }

        for stat, column in (
            mappings.items()
        ):
            value = pd.to_numeric(
                row.get(
                    column,
                    0,
                ),
                errors="coerce",
            )

            output[
                stat
            ] = (
                0
                if pd.isna(
                    value
                )
                else int(
                    round(
                        float(
                            value
                        )
                    )
                )
            )

        rows.append(
            output
        )

    official = pd.DataFrame(
        rows
    )

    if official.empty:
        return official

    compared_total = (
        official[
            STAT_COLUMNS
        ]
        .abs()
        .sum(
            axis=1
        )
    )

    return (
        official.loc[
            compared_total > 0
        ]
        .reset_index(
            drop=True
        )
    )



def select_games(
    processed_dir,
    count,
):
    candidates = sorted(
        path.stem
        for path
        in processed_dir.glob(
            "*.csv"
        )
        if re.fullmatch(
            r"002\d{7}",
            path.stem,
        )
    )

    if len(
        candidates
    ) < count:
        raise RuntimeError(
            f"Only {len(candidates)} regular-season "
            f"processed games found; requested {count}."
        )

    if count == 1:
        return [
            candidates[
                len(candidates)
                // 2
            ]
        ]

    indices = []

    for index in range(
        count
    ):
        position = round(
            index
            * (
                len(candidates)
                - 1
            )
            / (
                count
                - 1
            )
        )

        indices.append(
            position
        )

    return [
        candidates[
            index
        ]
        for index
        in indices
    ]


def detect_ambiguous_keys(
    df,
):
    if df.empty:
        return set()

    counts = (
        df.groupby(
            [
                "teamTricode",
                "matchKey",
            ]
        )[
            "displayName"
        ]
        .nunique()
    )

    return set(
        key
        for key, count
        in counts.items()
        if count > 1
    )


def fetch_traditional_box_score_with_retry(
    game_id,
    attempts=3,
    base_delay=1.5,
):
    last_error = None

    for attempt in range(
        1,
        attempts + 1,
    ):
        try:
            return (
                fetch_traditional_box_score(
                    game_id
                )
            )

        except Exception as error:
            last_error = error

            if attempt >= attempts:
                break

            delay = (
                base_delay
                * attempt
            )

            print(
                f"retry {attempt}/{attempts - 1} "
                f"after {delay:.1f}s",
                end=" ",
                flush=True,
            )

            time.sleep(
                delay
            )

    raise last_error


def validate_game(
    game_id,
    processed_dir,
):
    path = (
        processed_dir
        / f"{game_id}.csv"
    )

    pbp = pd.read_csv(
        path,
        dtype={
            "gameId":
                str,
        },
    )

    replay = (
        build_replay_box_score(
            pbp
        )
    )

    replay_numeric = (
        replay_to_numeric(
            replay
        )
    )

    (
        official_players,
        _,
    ) = fetch_traditional_box_score_with_retry(
        game_id
    )

    official_numeric = (
        official_to_numeric(
            official_players
        )
    )

    comparisons = []
    unmatched = []

    official_lookup = {
        (
            str(
                row[
                    "teamTricode"
                ]
            ),
            int(
                row[
                    "personId"
                ]
            ),
        ):
            row

        for _, row
        in official_numeric.iterrows()
    }

    matched_official = set()

    for _, replay_row in (
        replay_numeric.iterrows()
    ):
        person_id = (
            replay_row[
                "personId"
            ]
        )

        if pd.isna(
            person_id
        ):
            unmatched.append(
                {
                    "gameId":
                        game_id,

                    "side":
                        "replay",

                    "team":
                        replay_row[
                            "teamTricode"
                        ],

                    "player":
                        replay_row[
                            "displayName"
                        ],

                    "personId":
                        "",

                    "reason":
                        "missing_person_id",
                }
            )

            continue

        key = (
            str(
                replay_row[
                    "teamTricode"
                ]
            ),
            int(
                person_id
            ),
        )

        official_row = (
            official_lookup.get(
                key
            )
        )

        if official_row is None:
            unmatched.append(
                {
                    "gameId":
                        game_id,

                    "side":
                        "replay",

                    "team":
                        replay_row[
                            "teamTricode"
                        ],

                    "player":
                        replay_row[
                            "displayName"
                        ],

                    "personId":
                        int(
                            person_id
                        ),

                    "reason":
                        "person_id_not_found",
                }
            )

            continue

        matched_official.add(
            key
        )

        for stat in (
            STAT_COLUMNS
        ):
            replay_value = int(
                replay_row[
                    stat
                ]
            )

            official_value = int(
                official_row[
                    stat
                ]
            )

            comparisons.append(
                {
                    "gameId":
                        game_id,

                    "team":
                        replay_row[
                            "teamTricode"
                        ],

                    "personId":
                        int(
                            person_id
                        ),

                    "replayPlayer":
                        replay_row[
                            "displayName"
                        ],

                    "officialPlayer":
                        official_row[
                            "displayName"
                        ],

                    "stat":
                        stat,

                    "replayValue":
                        replay_value,

                    "officialValue":
                        official_value,

                    "difference":
                        (
                            replay_value
                            - official_value
                        ),

                    "exactMatch":
                        (
                            replay_value
                            == official_value
                        ),
                }
            )

    for _, row in (
        official_numeric.iterrows()
    ):
        key = (
            str(
                row[
                    "teamTricode"
                ]
            ),
            int(
                row[
                    "personId"
                ]
            ),
        )

        if key in matched_official:
            continue

        unmatched.append(
            {
                "gameId":
                    game_id,

                "side":
                    "official",

                "team":
                    row[
                        "teamTricode"
                    ],

                "player":
                    row[
                        "displayName"
                    ],

                "personId":
                    int(
                        row[
                            "personId"
                        ]
                    ),

                "reason":
                    "not_matched",
            }
        )

    return (
        pd.DataFrame(
            comparisons
        ),
        pd.DataFrame(
            unmatched
        ),
    )



def main():
    args = parse_args()

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    games = select_games(
        args.processed_dir,
        args.count,
    )

    print(
        "Replay Box Score Validation"
    )

    print(
        f"Games: {len(games)}"
    )

    print()

    all_comparisons = []
    all_unmatched = []
    failures = []

    for index, game_id in enumerate(
        games,
        start=1,
    ):
        print(
            f"[{index:02d}/{len(games):02d}] "
            f"{game_id}",
            end=" ",
            flush=True,
        )

        try:
            (
                comparisons,
                unmatched,
            ) = validate_game(
                game_id,
                args.processed_dir,
            )

            all_comparisons.append(
                comparisons
            )

            if not unmatched.empty:
                all_unmatched.append(
                    unmatched
                )

            mismatch_count = int(
                (
                    ~comparisons[
                        "exactMatch"
                    ]
                ).sum()
            )

            print(
                f"| comparisons={len(comparisons)} "
                f"| mismatches={mismatch_count} "
                f"| unmatched={len(unmatched)}"
            )

        except Exception as error:
            failures.append(
                {
                    "gameId":
                        game_id,

                    "error":
                        str(
                            error
                        ),
                }
            )

            print(
                f"| ERROR: {error}"
            )

        time.sleep(
            args.sleep
        )

    if all_comparisons:
        comparison_df = pd.concat(
            all_comparisons,
            ignore_index=True,
        )

    else:
        comparison_df = pd.DataFrame()

    if all_unmatched:
        unmatched_df = pd.concat(
            all_unmatched,
            ignore_index=True,
        )

    else:
        unmatched_df = pd.DataFrame(
            columns=[
                "gameId",
                "side",
                "team",
                "player",
                "matchKey",
                "reason",
            ]
        )

    failures_df = pd.DataFrame(
        failures
    )

    comparison_path = (
        args.output_dir
        / "player_stat_comparisons.csv"
    )

    mismatch_path = (
        args.output_dir
        / "mismatches.csv"
    )

    unmatched_path = (
        args.output_dir
        / "unmatched_players.csv"
    )

    failure_path = (
        args.output_dir
        / "game_failures.csv"
    )

    comparison_df.to_csv(
        comparison_path,
        index=False,
    )

    mismatch_df = (
        comparison_df.loc[
            ~comparison_df[
                "exactMatch"
            ]
        ]
        .copy()
        if not comparison_df.empty
        else comparison_df
    )

    mismatch_df.to_csv(
        mismatch_path,
        index=False,
    )

    unmatched_df.to_csv(
        unmatched_path,
        index=False,
    )

    failures_df.to_csv(
        failure_path,
        index=False,
    )

    print()
    print(
        "Exact-match rate by statistic"
    )

    summary_rows = []

    if not comparison_df.empty:
        for stat in (
            STAT_COLUMNS
        ):
            rows = (
                comparison_df.loc[
                    comparison_df[
                        "stat"
                    ]
                    == stat
                ]
            )

            exact = int(
                rows[
                    "exactMatch"
                ].sum()
            )

            total = len(
                rows
            )

            rate = (
                exact
                / total
                if total
                else 0.0
            )

            summary_rows.append(
                {
                    "stat":
                        stat,

                    "exact":
                        exact,

                    "total":
                        total,

                    "exactMatchRate":
                        rate,
                }
            )

            print(
                f"{stat:>3s}: "
                f"{exact:4d}/{total:4d} "
                f"({rate:6.2%})"
            )

    summary_df = pd.DataFrame(
        summary_rows
    )

    summary_path = (
        args.output_dir
        / "stat_summary.csv"
    )

    summary_df.to_csv(
        summary_path,
        index=False,
    )

    print()
    print(
        "Overall"
    )

    if not comparison_df.empty:
        overall_exact = int(
            comparison_df[
                "exactMatch"
            ].sum()
        )

        overall_total = len(
            comparison_df
        )

        overall_rate = (
            overall_exact
            / overall_total
        )

        print(
            f"Exact stat cells: "
            f"{overall_exact}/{overall_total} "
            f"({overall_rate:.2%})"
        )

    print(
        "Unmatched player rows:",
        len(
            unmatched_df
        ),
    )

    print(
        "Game failures:",
        len(
            failures_df
        ),
    )

    print()
    print(
        "Saved:"
    )

    for path in [
        summary_path,
        mismatch_path,
        unmatched_path,
        comparison_path,
        failure_path,
    ]:
        print(
            f"  {path}"
        )


if __name__ == "__main__":
    main()
