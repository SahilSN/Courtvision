import argparse

import pandas as pd

from nba_api.stats.endpoints import (
    playbyplayv3,
)

from espn_live import (
    fetch_espn_live_play_by_play,
)

from preprocess import (
    preprocess_live_game,
)


def period_end_snapshot(
    df,
    period,
):
    periods = pd.to_numeric(
        df[
            "period"
        ],
        errors="coerce",
    )

    available = (
        df.loc[
            periods
            == int(
                period
            )
        ]
    )

    if available.empty:
        return None

    row = (
        available.iloc[-1]
    )

    return (
        int(
            row[
                "scoreAway"
            ]
        ),
        int(
            row[
                "scoreHome"
            ]
        ),
    )


def main():
    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "--game-id",
        default="0012600009",
    )

    parser.add_argument(
        "--game-date",
        default="2026-10-03",
    )

    parser.add_argument(
        "--season",
        default="2026-27",
    )

    args = (
        parser.parse_args()
    )

    game_id = str(
        args.game_id
    ).zfill(
        10
    )

    espn_raw = (
        fetch_espn_live_play_by_play(
            game_id=game_id,
            game_date=(
                args.game_date
            ),
            season=(
                args.season
            ),
            timeout=30,
        )
    )

    nba_raw = (
        playbyplayv3
        .PlayByPlayV3(
            game_id=game_id,
            timeout=30,
        )
        .get_data_frames()[0]
        .copy()
    )

    espn = (
        preprocess_live_game(
            espn_raw
        )
    )

    nba = (
        preprocess_live_game(
            nba_raw
        )
    )

    print(
        "Courtvision ESPN Live Validation"
    )

    print(
        "Game:",
        game_id,
    )

    print()
    print(
        "Raw rows:"
    )
    print(
        "  ESPN:",
        len(
            espn_raw
        ),
    )
    print(
        "  NBA: ",
        len(
            nba_raw
        ),
    )

    print()
    print(
        "Processed rows:"
    )
    print(
        "  ESPN:",
        len(
            espn
        ),
    )
    print(
        "  NBA: ",
        len(
            nba
        ),
    )

    espn_final = (
        int(
            espn[
                "scoreAway"
            ].iloc[-1]
        ),
        int(
            espn[
                "scoreHome"
            ].iloc[-1]
        ),
    )

    nba_final = (
        int(
            nba[
                "scoreAway"
            ].iloc[-1]
        ),
        int(
            nba[
                "scoreHome"
            ].iloc[-1]
        ),
    )

    print()
    print(
        "Final score "
        "(away, home):"
    )
    print(
        "  ESPN:",
        espn_final,
    )
    print(
        "  NBA: ",
        nba_final,
    )

    espn_teams = (
        int(
            espn[
                "awayTeamId"
            ].iloc[0]
        ),
        int(
            espn[
                "homeTeamId"
            ].iloc[0]
        ),
    )

    nba_teams = (
        int(
            nba[
                "awayTeamId"
            ].iloc[0]
        ),
        int(
            nba[
                "homeTeamId"
            ].iloc[0]
        ),
    )

    print()
    print(
        "Team IDs "
        "(away, home):"
    )
    print(
        "  ESPN:",
        espn_teams,
    )
    print(
        "  NBA: ",
        nba_teams,
    )

    print()
    print(
        "Quarter-boundary scores:"
    )

    boundaries = [
        (
            "Q1",
            1,
        ),
        (
            "Half",
            2,
        ),
        (
            "Q3",
            3,
        ),
        (
            "Reg",
            4,
        ),
    ]

    boundary_pass = True

    for label, period in boundaries:
        espn_score = (
            period_end_snapshot(
                espn,
                period,
            )
        )

        nba_score = (
            period_end_snapshot(
                nba,
                period,
            )
        )

        match = (
            espn_score
            == nba_score
        )

        boundary_pass = (
            boundary_pass
            and match
        )

        print(
            f"  {label:<4}",
            "ESPN",
            espn_score,
            "| NBA",
            nba_score,
            "|",
            (
                "PASS"
                if match
                else "FAIL"
            ),
        )

    named_rows = (
        espn_raw.loc[
            espn_raw[
                "playerName"
            ]
            .astype(str)
            .str.strip()
            != ""
        ]
    )

    unresolved = (
        named_rows.loc[
            pd.to_numeric(
                named_rows[
                    "personId"
                ],
                errors="coerce",
            )
            .fillna(
                0
            )
            <= 0
        ]
    )

    substitutions = (
        espn_raw.loc[
            espn_raw[
                "actionType"
            ]
            == "Substitution"
        ]
    )

    malformed_subs = (
        substitutions.loc[
            ~substitutions[
                "description"
            ]
            .astype(str)
            .str.match(
                r"^SUB:\s+.+\s+FOR\s+.+$",
                case=False,
                na=False,
            )
        ]
    )

    print()
    print(
        "Player mapping:"
    )
    print(
        "  Named rows:",
        len(
            named_rows
        ),
    )
    print(
        "  Unresolved named rows:",
        len(
            unresolved
        ),
    )

    print()
    print(
        "Substitutions:"
    )
    print(
        "  Total:",
        len(
            substitutions
        ),
    )
    print(
        "  Malformed:",
        len(
            malformed_subs
        ),
    )

    print()
    print(
        "ESPN normalized "
        "action types:"
    )

    print(
        espn_raw[
            "actionType"
        ]
        .value_counts()
        .to_string()
    )

    passed = (
        espn_final
        == nba_final
        and espn_teams
        == nba_teams
        and boundary_pass
        and len(
            malformed_subs
        )
        == 0
    )

    print()
    print(
        "RESULT:",
        (
            "PASS"
            if passed
            else "FAIL"
        ),
    )


if __name__ == "__main__":
    main()
