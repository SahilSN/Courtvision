from __future__ import annotations

import re

import pandas as pd


# ============================================================
# General helpers
# ============================================================

def _safe_float(
    value,
    default=0.0,
):
    try:
        if pd.isna(value):
            return default

        return float(value)

    except (
        TypeError,
        ValueError,
    ):
        return default


def _safe_int(
    value,
    default=0,
):
    try:
        if pd.isna(value):
            return default

        return int(
            round(
                float(value)
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def _safe_text(
    value,
    default="",
):
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    return str(value).strip()


def format_period_label(
    period,
):
    period = _safe_int(
        period,
        default=1,
    )

    if period <= 4:
        return (
            f"Q{period}"
        )

    if period == 5:
        return "OT"

    return (
        f"{period - 4}OT"
    )


def format_clock(
    clock,
):
    text = _safe_text(
        clock
    )

    match = re.fullmatch(
        r"PT(?:(\d+)M)?(\d+(?:\.\d+)?)S",
        text,
    )

    if match is None:
        return text

    minutes = int(
        match.group(1)
        or 0
    )

    seconds = float(
        match.group(2)
    )

    if abs(
        seconds
        - round(seconds)
    ) < 1e-6:
        return (
            f"{minutes}:"
            f"{int(round(seconds)):02d}"
        )

    return (
        f"{minutes}:"
        f"{seconds:04.1f}"
    )


# ============================================================
# Score context
# ============================================================

def _team_margin(
    home_score,
    away_score,
    beneficiary_is_home,
):
    home_score = _safe_int(
        home_score
    )

    away_score = _safe_int(
        away_score
    )

    if beneficiary_is_home:
        return (
            home_score
            - away_score
        )

    return (
        away_score
        - home_score
    )


def describe_margin_change(
    before_margin,
    after_margin,
):
    """
    Describe the score-state transition from the benefiting
    team's perspective.
    """

    before_margin = _safe_int(
        before_margin
    )

    after_margin = _safe_int(
        after_margin
    )

    if (
        before_margin < 0
        and after_margin > 0
    ):
        return (
            f"turning a "
            f"{abs(before_margin)}-point deficit "
            f"into a {after_margin}-point lead"
        )

    if (
        before_margin < 0
        and after_margin == 0
    ):
        return (
            f"erasing a "
            f"{abs(before_margin)}-point deficit "
            f"to tie the game"
        )

    if (
        before_margin == 0
        and after_margin > 0
    ):
        return (
            f"breaking a tie and building a "
            f"{after_margin}-point lead"
        )

    if (
        before_margin > 0
        and after_margin > before_margin
    ):
        return (
            f"extending the lead from "
            f"{before_margin} to {after_margin} points"
        )

    if (
        before_margin < 0
        and after_margin < 0
        and after_margin > before_margin
    ):
        return (
            f"cutting the deficit from "
            f"{abs(before_margin)} to "
            f"{abs(after_margin)} points"
        )

    if (
        before_margin > 0
        and after_margin == 0
    ):
        return (
            f"giving up a "
            f"{before_margin}-point lead "
            f"before returning to a tie"
        )

    if (
        before_margin == after_margin
    ):
        if after_margin > 0:
            return (
                f"maintaining a "
                f"{after_margin}-point lead"
            )

        if after_margin < 0:
            return (
                f"remaining "
                f"{abs(after_margin)} points behind"
            )

        return (
            "leaving the score tied"
        )

    if after_margin > 0:
        return (
            f"finishing the stretch with a "
            f"{after_margin}-point lead"
        )

    if after_margin < 0:
        return (
            f"finishing the stretch "
            f"{abs(after_margin)} points behind"
        )

    return (
        "finishing the stretch tied"
    )


# ============================================================
# Timeline helpers
# ============================================================

def _prepare_timeline(
    game_df,
):
    df = (
        game_df.copy()
    )

    if (
        "isTerminalState"
        in df.columns
    ):
        df = (
            df[
                df[
                    "isTerminalState"
                ]
                == False
            ]
            .copy()
        )

    df = (
        df
        .sort_values(
            "elapsedGameTime",
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    df[
        "_previousHomeWP"
    ] = (
        df[
            "winProbability"
        ]
        .shift(1)
    )

    df[
        "_homeWPChange"
    ] = (
        df[
            "winProbability"
        ]
        - df[
            "_previousHomeWP"
        ]
    )

    df[
        "_previousHomeScore"
    ] = (
        pd.to_numeric(
            df[
                "scoreHome"
            ],
            errors="coerce",
        )
        .shift(1)
    )

    df[
        "_previousHomeScore"
    ] = (
        df[
            "_previousHomeScore"
        ]
        .where(
            df[
                "_previousHomeScore"
            ]
            .notna(),
            pd.to_numeric(
                df[
                    "scoreHome"
                ],
                errors="coerce",
            ),
        )
    )

    df[
        "_previousAwayScore"
    ] = (
        pd.to_numeric(
            df[
                "scoreAway"
            ],
            errors="coerce",
        )
        .shift(1)
    )

    df[
        "_previousAwayScore"
    ] = (
        df[
            "_previousAwayScore"
        ]
        .where(
            df[
                "_previousAwayScore"
            ]
            .notna(),
            pd.to_numeric(
                df[
                    "scoreAway"
                ],
                errors="coerce",
            ),
        )
    )

    df[
        "_homePoints"
    ] = (
        df[
            "scoreHome"
        ]
        - df[
            "_previousHomeScore"
        ]
    )

    df[
        "_awayPoints"
    ] = (
        df[
            "scoreAway"
        ]
        - df[
            "_previousAwayScore"
        ]
    )

    return df


def _run_rows(
    timeline,
    run,
):
    start = _safe_float(
        run[
            "startElapsed"
        ]
    )

    end = _safe_float(
        run[
            "endElapsed"
        ]
    )

    return (
        timeline[
            (
                timeline[
                    "elapsedGameTime"
                ]
                >= start
            )
            &
            (
                timeline[
                    "elapsedGameTime"
                ]
                <= end
            )
        ]
        .copy()
    )


# ============================================================
# Player context
# ============================================================

def leading_run_scorer(
    timeline,
    run,
    home_team,
):
    """
    Determine which player scored the most points during
    the run using observed score changes.

    This is deliberately descriptive rather than a claim
    about causal impact.
    """

    rows = (
        _run_rows(
            timeline,
            run,
        )
    )

    if rows.empty:
        return None

    beneficiary = (
        run[
            "beneficiaryTeam"
        ]
    )

    beneficiary_is_home = (
        beneficiary
        == home_team
    )

    totals = {}

    for _, row in (
        rows.iterrows()
    ):
        if beneficiary_is_home:
            points = _safe_int(
                row[
                    "_homePoints"
                ]
            )

        else:
            points = _safe_int(
                row[
                    "_awayPoints"
                ]
            )

        if points <= 0:
            continue

        row_team = (
            _safe_text(
                row.get(
                    "teamTricode"
                )
            )
        )

        if (
            row_team
            and row_team
            != beneficiary
        ):
            continue

        player = (
            _safe_text(
                row.get(
                    "playerName"
                )
            )
        )

        if not player:
            continue

        totals[
            player
        ] = (
            totals.get(
                player,
                0,
            )
            + points
        )

    if not totals:
        return None

    player, points = max(
        totals.items(),
        key=lambda item:
            (
                item[1],
                item[0],
            ),
    )

    return {
        "player":
            player,

        "points":
            points,
    }


def biggest_run_play(
    timeline,
    run,
    home_team,
):
    """
    Find the largest adjacent observed WP movement benefiting
    the run's team within the detected window.
    """

    rows = (
        _run_rows(
            timeline,
            run,
        )
    )

    if rows.empty:
        return None

    beneficiary = (
        run[
            "beneficiaryTeam"
        ]
    )

    beneficiary_is_home = (
        beneficiary
        == home_team
    )

    if beneficiary_is_home:
        rows[
            "_teamWPChange"
        ] = (
            rows[
                "_homeWPChange"
            ]
        )

    else:
        rows[
            "_teamWPChange"
        ] = (
            -rows[
                "_homeWPChange"
            ]
        )

    valid = (
        rows.dropna(
            subset=[
                "_teamWPChange",
            ]
        )
    )

    if valid.empty:
        return None

    row = (
        valid.loc[
            valid[
                "_teamWPChange"
            ]
            .idxmax()
        ]
    )

    change = (
        _safe_float(
            row[
                "_teamWPChange"
            ]
        )
    )

    if change <= 0:
        return None

    return {
        "change":
            change,

        "changePoints":
            change
            * 100.0,

        "period":
            _safe_int(
                row.get(
                    "period"
                )
            ),

        "clock":
            _safe_text(
                row.get(
                    "clock"
                )
            ),

        "player":
            _safe_text(
                row.get(
                    "playerName"
                )
            ),

        "description":
            _safe_text(
                row.get(
                    "description"
                )
            ),
    }


def team_wpa_leader(
    player_summary,
    team,
):
    if (
        player_summary is None
        or len(
            player_summary
        )
        == 0
    ):
        return None

    df = (
        player_summary.copy()
    )

    required = [
        "player",
        "team",
        "net_wpa_pp",
    ]

    if not all(
        column in df.columns
        for column in required
    ):
        return None

    team_df = (
        df[
            df[
                "team"
            ]
            == team
        ]
        .copy()
    )

    if team_df.empty:
        return None

    row = (
        team_df
        .sort_values(
            "net_wpa_pp",
            ascending=False,
        )
        .iloc[
            0
        ]
    )

    return {
        "player":
            _safe_text(
                row[
                    "player"
                ]
            ),

        "netWPA":
            _safe_float(
                row[
                    "net_wpa_pp"
                ]
            ),
    }


# ============================================================
# Explanation construction
# ============================================================


def build_contextual_headline(
    team,
    team_points,
    opponent_points,
    before_margin,
    after_margin,
):
    run_text = (
        f"{team_points}–{opponent_points} run"
    )

    # Trailing -> leading
    if (
        before_margin < 0
        and after_margin > 0
    ):
        verb = (
            "flipped the game"
        )

    # Tied -> leading
    elif (
        before_margin == 0
        and after_margin > 0
    ):
        verb = (
            "broke the tie"
        )

    # Still trailing, but significantly closer
    elif (
        before_margin < 0
        and after_margin <= 0
        and after_margin > before_margin
    ):
        verb = (
            "surged back"
        )

    # Already ahead and increased advantage
    elif (
        before_margin > 0
        and after_margin > before_margin
    ):
        verb = (
            "pulled away"
        )

    # Generic but still accurate fallback
    else:
        verb = (
            "made a major push"
        )

    return (
        f"{team} {verb} "
        f"with a {run_text}"
    )


def build_run_explanation(
    timeline,
    run,
    home_team,
    away_team,
    player_summary=None,
):
    beneficiary = (
        run[
            "beneficiaryTeam"
        ]
    )

    opponent = (
        run[
            "opponentTeam"
        ]
    )

    beneficiary_is_home = (
        beneficiary
        == home_team
    )

    start_home = _safe_int(
        run[
            "homeScoreBefore"
        ]
    )

    start_away = _safe_int(
        run[
            "awayScoreBefore"
        ]
    )

    end_home = _safe_int(
        run[
            "homeScoreAfter"
        ]
    )

    end_away = _safe_int(
        run[
            "awayScoreAfter"
        ]
    )

    before_margin = (
        _team_margin(
            start_home,
            start_away,
            beneficiary_is_home,
        )
    )

    after_margin = (
        _team_margin(
            end_home,
            end_away,
            beneficiary_is_home,
        )
    )

    margin_description = (
        describe_margin_change(
            before_margin,
            after_margin,
        )
    )

    start_label = (
        f"{format_period_label(run['startPeriod'])} "
        f"{format_clock(run['startClock'])}"
    )

    end_label = (
        f"{format_period_label(run['endPeriod'])} "
        f"{format_clock(run['endClock'])}"
    )

    wp_swing = (
        _safe_float(
            run[
                "winProbabilitySwingPoints"
            ]
        )
    )

    beneficiary_points = (
        _safe_int(
            run[
                "beneficiaryPoints"
            ]
        )
    )

    opponent_points = (
        _safe_int(
            run[
                "opponentPoints"
            ]
        )
    )

    scorer = (
        leading_run_scorer(
            timeline,
            run,
            home_team,
        )
    )

    key_play = (
        biggest_run_play(
            timeline,
            run,
            home_team,
        )
    )

    wpa_leader = (
        team_wpa_leader(
            player_summary,
            beneficiary,
        )
    )

    headline = (
        build_contextual_headline(
            team=beneficiary,
            team_points=beneficiary_points,
            opponent_points=opponent_points,
            before_margin=before_margin,
            after_margin=after_margin,
        )
    )

    summary = (
        f"From {start_label} to {end_label}, "
        f"{beneficiary} outscored {opponent} "
        f"{beneficiary_points}–{opponent_points} "
        f"and raised its win probability "
        f"by {wp_swing:.1f} points, "
        f"{margin_description}."
    )

    details = []

    if scorer is not None:
        details.append(
            f"{scorer['player']} scored "
            f"{scorer['points']} points "
            f"during the stretch."
        )

    if (
        key_play is not None
        and key_play[
            "changePoints"
        ]
        >= 1.0
    ):
        description = (
            key_play[
                "description"
            ]
        )

        player = (
            key_play[
                "player"
            ]
        )

        play_text = None

        if description:
            play_text = description

        elif player:
            play_text = (
                f"a play by {player}"
            )

        if play_text:
            details.append(
                f"The largest single-play shift "
                f"inside the run came on "
                f"{play_text}, adding "
                f"{key_play['changePoints']:.1f} "
                f"percentage points."
            )

    if wpa_leader is not None:
        details.append(
            f"Across the full game, "
            f"{wpa_leader['player']} led "
            f"{beneficiary} with "
            f"{wpa_leader['netWPA']:+.1f} "
            f"points of player WPA."
        )

    context_weight = (
        wp_swing
    )

    # Give late-game runs additional narrative priority.
    end_period = _safe_int(
        run[
            "endPeriod"
        ]
    )

    if end_period >= 4:
        context_weight += 5.0

    # Lead flips are especially meaningful.
    if (
        before_margin < 0
        and after_margin > 0
    ):
        context_weight += 7.5

    elif (
        before_margin <= 0
        and after_margin > 0
    ):
        context_weight += 4.0

    return {
        "team":
            beneficiary,

        "opponent":
            opponent,

        "headline":
            headline,

        "summary":
            summary,

        "details":
            details,

        "winProbabilitySwingPoints":
            wp_swing,

        "startPeriod":
            run[
                "startPeriod"
            ],

        "startClock":
            run[
                "startClock"
            ],

        "endPeriod":
            run[
                "endPeriod"
            ],

        "endClock":
            run[
                "endClock"
            ],

        "contextScore":
            context_weight,
    }


def build_contextual_explanations(
    game_df,
    momentum_result,
    home_team,
    away_team,
    player_summary=None,
    top_k=4,
):
    """
    Build deterministic, evidence-backed explanations of
    the game's most important multi-play swings.
    """

    timeline = (
        _prepare_timeline(
            game_df
        )
    )

    runs = (
        momentum_result.get(
            "all_runs",
            [],
        )
    )

    explanations = []

    for run in runs:
        explanations.append(
            build_run_explanation(
                timeline=timeline,
                run=run,
                home_team=home_team,
                away_team=away_team,
                player_summary=player_summary,
            )
        )

    explanations = sorted(
        explanations,
        key=lambda row:
            row[
                "contextScore"
            ],
        reverse=True,
    )

    return (
        explanations[
            :top_k
        ]
    )
