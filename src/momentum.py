from __future__ import annotations

import math

import pandas as pd


# ============================================================
# Momentum configuration
# ============================================================

# A momentum run must contain several state transitions.
MIN_TRANSITIONS = 4

# Avoid calling very long game segments one "run."
MAX_TRANSITIONS = 14

# Candidate time window.
MIN_DURATION_SECONDS = 20
MAX_DURATION_SECONDS = 180

# Minimum net win-probability movement.
MIN_WP_SWING = 0.10

# Exception for especially dramatic probability movement.
STRONG_WP_SWING = 0.15

# Normally require the benefiting team to gain at least
# this many points in scoring margin over the stretch.
MIN_SCORE_MARGIN_SWING = 2

# Used to suppress near-duplicate overlapping windows.
MAX_OVERLAP_FRACTION = 0.35


# ============================================================
# Helpers
# ============================================================

def _safe_float(
    value,
    default=0.0,
):
    try:
        if pd.isna(
            value
        ):
            return default

        return float(
            value
        )

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
        if pd.isna(
            value
        ):
            return default

        return int(
            round(
                float(
                    value
                )
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def _normalize_probability(
    value,
):
    value = _safe_float(
        value,
        default=0.5,
    )

    # Defensive support in case a future caller supplies
    # percentages rather than probabilities.
    if value > 1.5:
        value = (
            value / 100.0
        )

    return min(
        1.0,
        max(
            0.0,
            value,
        ),
    )


def _interval_overlap_fraction(
    first,
    second,
):
    """
    Measure overlap relative to the shorter interval.

    1.0 = one candidate is essentially contained
          inside the other.
    """

    first_start = float(
        first[
            "startElapsed"
        ]
    )

    first_end = float(
        first[
            "endElapsed"
        ]
    )

    second_start = float(
        second[
            "startElapsed"
        ]
    )

    second_end = float(
        second[
            "endElapsed"
        ]
    )

    overlap = max(
        0.0,
        min(
            first_end,
            second_end,
        )
        - max(
            first_start,
            second_start,
        ),
    )

    first_duration = max(
        1.0,
        first_end
        - first_start,
    )

    second_duration = max(
        1.0,
        second_end
        - second_start,
    )

    return (
        overlap
        / min(
            first_duration,
            second_duration,
        )
    )


# ============================================================
# Candidate construction
# ============================================================

def _make_candidate(
    df,
    start_index,
    end_index,
    home_team,
    away_team,
):
    start = (
        df.iloc[
            start_index
        ]
    )

    end = (
        df.iloc[
            end_index
        ]
    )

    start_elapsed = (
        _safe_float(
            start[
                "elapsedGameTime"
            ]
        )
    )

    end_elapsed = (
        _safe_float(
            end[
                "elapsedGameTime"
            ]
        )
    )

    duration = (
        end_elapsed
        - start_elapsed
    )

    transitions = (
        end_index
        - start_index
    )

    home_before = (
        _normalize_probability(
            start[
                "winProbability"
            ]
        )
    )

    home_after = (
        _normalize_probability(
            end[
                "winProbability"
            ]
        )
    )

    home_delta = (
        home_after
        - home_before
    )

    if abs(
        home_delta
    ) < 1e-12:
        return None

    home_score_before = (
        _safe_int(
            start.get(
                "scoreHome",
                0,
            )
        )
    )

    home_score_after = (
        _safe_int(
            end.get(
                "scoreHome",
                0,
            )
        )
    )

    away_score_before = (
        _safe_int(
            start.get(
                "scoreAway",
                0,
            )
        )
    )

    away_score_after = (
        _safe_int(
            end.get(
                "scoreAway",
                0,
            )
        )
    )

    home_points = (
        home_score_after
        - home_score_before
    )

    away_points = (
        away_score_after
        - away_score_before
    )

    home_margin_swing = (
        home_points
        - away_points
    )

    if home_delta > 0:
        beneficiary = (
            home_team
        )

        opponent = (
            away_team
        )

        before_probability = (
            home_before
        )

        after_probability = (
            home_after
        )

        beneficiary_points = (
            home_points
        )

        opponent_points = (
            away_points
        )

        score_margin_swing = (
            home_margin_swing
        )

    else:
        beneficiary = (
            away_team
        )

        opponent = (
            home_team
        )

        before_probability = (
            1.0
            - home_before
        )

        after_probability = (
            1.0
            - home_after
        )

        beneficiary_points = (
            away_points
        )

        opponent_points = (
            home_points
        )

        score_margin_swing = (
            -home_margin_swing
        )

    probability_swing = (
        after_probability
        - before_probability
    )

    # The benefiting team's probability should always
    # increase in our team-relative representation.
    if probability_swing <= 0:
        return None

    # Most momentum stretches should include an actual
    # scoring-margin gain. Exception: allow unusually
    # dramatic model movement even when scoring margin
    # is flat.
    if (
        score_margin_swing
        < MIN_SCORE_MARGIN_SWING
        and probability_swing
        < STRONG_WP_SWING
    ):
        return None

    # Ranking is primarily driven by WP movement.
    # Scoring margin is only a modest tiebreaker.
    # Rank primarily by WP movement and scoring-margin
    # gain. Mildly penalize unnecessarily long windows so
    # the detector prefers the compact core of a run rather
    # than extending it simply to collect more transitions.
    excess_duration = max(
        0.0,
        duration - 90.0,
    )

    momentum_score = (
        probability_swing
        * 100.0
        + max(
            0,
            score_margin_swing,
        )
        * 0.50
        - (
            excess_duration
            / 60.0
        )
        * 0.75
    )

    return {
        "beneficiaryTeam":
            beneficiary,

        "opponentTeam":
            opponent,

        "startIndex":
            int(
                start_index
            ),

        "endIndex":
            int(
                end_index
            ),

        "startElapsed":
            start_elapsed,

        "endElapsed":
            end_elapsed,

        "durationSeconds":
            duration,

        "transitions":
            transitions,

        "startPeriod":
            _safe_int(
                start.get(
                    "period",
                    1,
                ),
                default=1,
            ),

        "endPeriod":
            _safe_int(
                end.get(
                    "period",
                    1,
                ),
                default=1,
            ),

        "startClock":
            str(
                start.get(
                    "clock",
                    "",
                )
            ),

        "endClock":
            str(
                end.get(
                    "clock",
                    "",
                )
            ),

        "winProbabilityBefore":
            before_probability,

        "winProbabilityAfter":
            after_probability,

        "winProbabilitySwing":
            probability_swing,

        "winProbabilitySwingPoints":
            probability_swing
            * 100.0,

        "beneficiaryPoints":
            beneficiary_points,

        "opponentPoints":
            opponent_points,

        "scoreMarginSwing":
            score_margin_swing,

        "homeScoreBefore":
            home_score_before,

        "homeScoreAfter":
            home_score_after,

        "awayScoreBefore":
            away_score_before,

        "awayScoreAfter":
            away_score_after,

        "momentumScore":
            momentum_score,
    }


# ============================================================
# Candidate generation
# ============================================================

def generate_momentum_candidates(
    game_df,
    home_team,
    away_team,
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

    required = [
        "elapsedGameTime",
        "winProbability",
    ]

    df = (
        df.dropna(
            subset=required
        )
        .sort_values(
            "elapsedGameTime",
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )

    if len(
        df
    ) < (
        MIN_TRANSITIONS + 1
    ):
        return (
            df,
            []
        )

    candidates = []

    for start_index in range(
        len(df)
    ):
        max_end = min(
            len(df) - 1,
            start_index
            + MAX_TRANSITIONS,
        )

        for end_index in range(
            start_index
            + MIN_TRANSITIONS,
            max_end + 1,
        ):
            start_elapsed = (
                _safe_float(
                    df.iloc[
                        start_index
                    ][
                        "elapsedGameTime"
                    ]
                )
            )

            end_elapsed = (
                _safe_float(
                    df.iloc[
                        end_index
                    ][
                        "elapsedGameTime"
                    ]
                )
            )

            duration = (
                end_elapsed
                - start_elapsed
            )

            if (
                duration
                < MIN_DURATION_SECONDS
            ):
                continue

            if (
                duration
                > MAX_DURATION_SECONDS
            ):
                break

            candidate = (
                _make_candidate(
                    df,
                    start_index,
                    end_index,
                    home_team,
                    away_team,
                )
            )

            if candidate is None:
                continue

            if (
                candidate[
                    "winProbabilitySwing"
                ]
                < MIN_WP_SWING
            ):
                continue

            candidates.append(
                candidate
            )

    return (
        df,
        candidates,
    )


# ============================================================
# Deduplication
# ============================================================

def select_distinct_runs(
    candidates,
    top_k=3,
):
    """
    Greedy non-maximum suppression.

    Large/high-value windows are considered first.
    Near-duplicates that substantially overlap an
    already selected run for the same team are removed.
    """

    ordered = sorted(
        candidates,
        key=lambda row: (
            row[
                "momentumScore"
            ],
            row[
                "winProbabilitySwing"
            ],
        ),
        reverse=True,
    )

    selected = []

    for candidate in ordered:
        same_team_selected = [
            run
            for run in selected
            if (
                run[
                    "beneficiaryTeam"
                ]
                == candidate[
                    "beneficiaryTeam"
                ]
            )
        ]

        duplicate = any(
            (
                _interval_overlap_fraction(
                    candidate,
                    existing,
                )
                > MAX_OVERLAP_FRACTION
            )
            for existing
            in same_team_selected
        )

        if duplicate:
            continue

        selected.append(
            candidate
        )

        home_count = sum(
            run[
                "beneficiaryTeam"
            ]
            == candidate[
                "beneficiaryTeam"
            ]
            for run
            in selected
        )

        # Continue because we still need runs for
        # the opposing team too.
        if home_count > top_k:
            selected.pop()

    return selected


# ============================================================
# Public API
# ============================================================

def detect_momentum_runs(
    game_df,
    home_team,
    away_team,
    top_k=3,
):
    """
    Detect distinct multi-play stretches in which one
    team's modeled chance of winning rises substantially.

    Returns team-relative runs. Positive swing always
    means the listed beneficiary improved its own chance
    of winning.
    """

    (
        timeline,
        candidates,
    ) = (
        generate_momentum_candidates(
            game_df,
            home_team,
            away_team,
        )
    )

    selected = (
        select_distinct_runs(
            candidates,
            top_k=top_k,
        )
    )

    home_runs = [
        run
        for run in selected
        if (
            run[
                "beneficiaryTeam"
            ]
            == home_team
        )
    ][:top_k]

    away_runs = [
        run
        for run in selected
        if (
            run[
                "beneficiaryTeam"
            ]
            == away_team
        )
    ][:top_k]

    all_runs = sorted(
        (
            home_runs
            + away_runs
        ),
        key=lambda row: (
            row[
                "momentumScore"
            ]
        ),
        reverse=True,
    )

    return {
        "home_team":
            home_team,

        "away_team":
            away_team,

        "home_runs":
            home_runs,

        "away_runs":
            away_runs,

        "all_runs":
            all_runs,

        "candidate_count":
            len(
                candidates
            ),

        "timeline_rows":
            len(
                timeline
            ),
    }
