from __future__ import annotations

import argparse
import contextlib
import io
from pathlib import Path

import numpy as np
import pandas as pd

from contextual_explanations import (
    build_contextual_explanations,
)
from game_story import build_game_story
from live_analysis import analyze_live_game
from momentum import detect_momentum_runs
from team_metadata import get_team_metadata


ROOT_DIR = (
    Path(__file__)
    .resolve()
    .parents[1]
)

TRAINING_DIR = (
    ROOT_DIR
    / "data"
    / "training"
)

RESULTS_DIR = (
    ROOT_DIR
    / "results"
)


# ============================================================
# Generic helpers
# ============================================================

def safe_float(
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


def safe_int(
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


def normalize_game_id(
    game_id,
):
    return (
        str(
            int(
                float(game_id)
            )
        )
        .zfill(10)
    )


# ============================================================
# Season sampling
# ============================================================

def load_game_catalog(
    season,
):
    path = (
        TRAINING_DIR
        / f"{season}_training_v4_base.csv"
    )

    if not path.exists():
        raise FileNotFoundError(
            f"Missing season dataset: {path}"
        )

    df = pd.read_csv(
        path,
        usecols=[
            "gameId",
            "gameDate",
        ],
    )

    games = (
        df[
            [
                "gameId",
                "gameDate",
            ]
        ]
        .drop_duplicates(
            subset=[
                "gameId",
            ]
        )
        .copy()
    )

    games[
        "gameDate"
    ] = pd.to_datetime(
        games[
            "gameDate"
        ]
    )

    games = (
        games
        .sort_values(
            [
                "gameDate",
                "gameId",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    games[
        "gameId"
    ] = (
        games[
            "gameId"
        ]
        .apply(
            normalize_game_id
        )
    )

    return games


def select_evenly_spaced_games(
    games,
    sample_size,
):
    if sample_size >= len(games):
        return games.copy()

    indices = np.linspace(
        0,
        len(games) - 1,
        sample_size,
        dtype=int,
    )

    return (
        games
        .iloc[
            indices
        ]
        .reset_index(
            drop=True
        )
    )


# ============================================================
# Optional cached player enrichment
# ============================================================

def load_cached_player_summary(
    game_id,
):
    path = (
        RESULTS_DIR
        / (
            f"player_wpa_v3_"
            f"{game_id}_summary.csv"
        )
    )

    if not path.exists():
        return None

    try:
        df = pd.read_csv(
            path
        )

    except Exception:
        return None

    required = {
        "player",
        "team",
        "net_wpa_pp",
    }

    if not required.issubset(
        df.columns
    ):
        return None

    return df


# ============================================================
# Timeline truth
# ============================================================

def non_terminal_timeline(
    timeline,
):
    df = timeline.copy()

    if "isTerminalState" in df.columns:
        valid = (
            df[
                df[
                    "isTerminalState"
                ]
                == False
            ]
            .copy()
        )

        if not valid.empty:
            df = valid

    df[
        "elapsedGameTime"
    ] = pd.to_numeric(
        df[
            "elapsedGameTime"
        ],
        errors="coerce",
    )

    return (
        df
        .sort_values(
            "elapsedGameTime",
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )


def expected_final_result(
    timeline,
    home_team,
    away_team,
):
    df = (
        non_terminal_timeline(
            timeline
        )
    )

    if df.empty:
        return None

    row = (
        df.iloc[-1]
    )

    home_score = safe_int(
        row[
            "scoreHome"
        ]
    )

    away_score = safe_int(
        row[
            "scoreAway"
        ]
    )

    if home_score > away_score:
        return {
            "winner":
                home_team,

            "loser":
                away_team,

            "winnerScore":
                home_score,

            "loserScore":
                away_score,
        }

    if away_score > home_score:
        return {
            "winner":
                away_team,

            "loser":
                home_team,

            "winnerScore":
                away_score,

            "loserScore":
                home_score,
        }

    return {
        "winner":
            None,

        "loser":
            None,

        "winnerScore":
            home_score,

        "loserScore":
            away_score,
    }


def winner_margin(
    row,
    winner,
    home_team,
):
    home_score = safe_int(
        row[
            "scoreHome"
        ]
    )

    away_score = safe_int(
        row[
            "scoreAway"
        ]
    )

    if winner == home_team:
        return (
            home_score
            - away_score
        )

    return (
        away_score
        - home_score
    )


# ============================================================
# Independent decisive-run verification
# ============================================================

def independently_durable(
    timeline,
    explanation,
    winner,
    home_team,
):
    if explanation is None:
        return False

    if explanation.get(
        "team"
    ) != winner:
        return False

    if safe_int(
        explanation.get(
            "endPeriod"
        )
    ) < 4:
        return False

    if safe_int(
        explanation.get(
            "afterMargin"
        )
    ) <= 0:
        return False

    end_elapsed = safe_float(
        explanation.get(
            "endElapsed"
        ),
        default=-1.0,
    )

    if end_elapsed < 0:
        return False

    df = (
        non_terminal_timeline(
            timeline
        )
    )

    later = (
        df[
            df[
                "elapsedGameTime"
            ]
            > end_elapsed
        ]
        .copy()
    )

    if later.empty:
        return True

    margins = (
        later.apply(
            lambda row:
                winner_margin(
                    row=row,
                    winner=winner,
                    home_team=home_team,
                ),
            axis=1,
        )
    )

    return bool(
        (
            margins
            > 0
        )
        .all()
    )


def all_independent_decisive_candidates(
    timeline,
    explanations,
    winner,
    home_team,
):
    return [
        explanation
        for explanation
        in explanations
        if independently_durable(
            timeline=timeline,
            explanation=explanation,
            winner=winner,
            home_team=home_team,
        )
    ]


# ============================================================
# Structural validation
# ============================================================

def metric_map(
    story,
):
    return {
        str(
            metric.get(
                "label"
            )
        ):
            metric.get(
                "value"
            )
        for metric
        in story.get(
            "metrics",
            []
        )
    }


def section_map(
    story,
):
    return {
        str(
            section.get(
                "label"
            )
        ):
            section.get(
                "text"
            )
        for section
        in story.get(
            "sections",
            []
        )
    }


def validate_story(
    game_id,
    timeline,
    story,
    explanations,
    home_team,
    away_team,
):
    expected = (
        expected_final_result(
            timeline=timeline,
            home_team=home_team,
            away_team=away_team,
        )
    )

    if expected is None:
        raise RuntimeError(
            "No final game state available."
        )

    winner = (
        expected[
            "winner"
        ]
    )

    story_winner = (
        story.get(
            "winner"
        )
    )

    story_loser = (
        story.get(
            "loser"
        )
    )

    final_score = (
        story.get(
            "finalScore",
            {},
        )
    )

    winner_pass = (
        story_winner
        == winner
    )

    loser_pass = (
        story_loser
        ==
        expected[
            "loser"
        ]
    )

    score_pass = (
        safe_int(
            final_score.get(
                "winnerScore"
            )
        )
        ==
        expected[
            "winnerScore"
        ]
        and
        safe_int(
            final_score.get(
                "loserScore"
            )
        )
        ==
        expected[
            "loserScore"
        ]
    )

    decisive = (
        story.get(
            "decisiveExplanation"
        )
    )

    independent_candidates = (
        all_independent_decisive_candidates(
            timeline=timeline,
            explanations=explanations,
            winner=winner,
            home_team=home_team,
        )
        if winner is not None
        else []
    )

    expected_decisive = (
        max(
            independent_candidates,
            key=lambda item:
                safe_float(
                    item.get(
                        "contextScore"
                    )
                ),
        )
        if independent_candidates
        else None
    )

    if decisive is None:
        decisive_presence_pass = (
            expected_decisive
            is None
        )

        decisive_durable_pass = True

    else:
        decisive_presence_pass = (
            expected_decisive
            is not None
        )

        decisive_durable_pass = (
            independently_durable(
                timeline=timeline,
                explanation=decisive,
                winner=winner,
                home_team=home_team,
            )
        )

    if (
        decisive is not None
        and expected_decisive is not None
    ):
        decisive_selection_pass = all(
            [
                decisive.get(
                    "team"
                )
                ==
                expected_decisive.get(
                    "team"
                ),

                abs(
                    safe_float(
                        decisive.get(
                            "startElapsed"
                        )
                    )
                    -
                    safe_float(
                        expected_decisive.get(
                            "startElapsed"
                        )
                    )
                )
                <= 1e-8,

                abs(
                    safe_float(
                        decisive.get(
                            "endElapsed"
                        )
                    )
                    -
                    safe_float(
                        expected_decisive.get(
                            "endElapsed"
                        )
                    )
                )
                <= 1e-8,
            ]
        )

    else:
        decisive_selection_pass = (
            decisive is None
            and expected_decisive is None
        )

    metrics = (
        metric_map(
            story
        )
    )

    sections = (
        section_map(
            story
        )
    )

    primary = (
        story.get(
            "primaryExplanation"
        )
    )

    if primary is None:
        metric_label_pass = (
            len(
                metrics
            )
            == 0
        )

    elif decisive is not None:
        metric_label_pass = (
            "Decisive run"
            in metrics
            and "Biggest run"
            not in metrics
        )

    else:
        metric_label_pass = (
            "Biggest run"
            in metrics
            and "Decisive run"
            not in metrics
        )

    if decisive is not None:
        section_label_pass = (
            "Decisive stretch"
            in sections
        )

    elif primary is not None:
        expected_label = (
            f"Biggest {winner} surge"
        )

        section_label_pass = (
            expected_label
            in sections
        )

    else:
        section_label_pass = True

    subtitle = str(
        story.get(
            "subtitle",
            ""
        )
    ).lower()

    if decisive is not None:
        subtitle_pass = (
            "decisive"
            in subtitle
        )

    else:
        subtitle_pass = (
            "decisive"
            not in subtitle
        )

    lead = str(
        story.get(
            "lead",
            ""
        )
    )

    lead_pass = (
        bool(
            lead.strip()
        )
        and (
            winner is None
            or winner in lead
        )
    )

    structural_pass = all(
        [
            winner_pass,
            loser_pass,
            score_pass,
            decisive_presence_pass,
            decisive_durable_pass,
            decisive_selection_pass,
            metric_label_pass,
            section_label_pass,
            subtitle_pass,
            lead_pass,
        ]
    )

    return {
        "gameId":
            game_id,

        "winner":
            winner,

        "loser":
            expected[
                "loser"
            ],

        "winnerScore":
            expected[
                "winnerScore"
            ],

        "loserScore":
            expected[
                "loserScore"
            ],

        "explanationCount":
            len(
                explanations
            ),

        "independentDecisiveCandidates":
            len(
                independent_candidates
            ),

        "hasDecisiveRun":
            decisive
            is not None,

        "winnerPass":
            winner_pass,

        "loserPass":
            loser_pass,

        "scorePass":
            score_pass,

        "decisivePresencePass":
            decisive_presence_pass,

        "decisiveDurablePass":
            decisive_durable_pass,

        "decisiveSelectionPass":
            decisive_selection_pass,

        "metricLabelPass":
            metric_label_pass,

        "sectionLabelPass":
            section_label_pass,

        "subtitlePass":
            subtitle_pass,

        "leadPass":
            lead_pass,

        "structuralPass":
            structural_pass,

        "lead":
            story.get(
                "lead"
            ),

        "subtitle":
            story.get(
                "subtitle"
            ),
    }


# ============================================================
# Per-game pipeline
# ============================================================

def validate_game(
    game_id,
    game_date,
    season,
):
    hidden_output = (
        io.StringIO()
    )

    with contextlib.redirect_stdout(
        hidden_output
    ):
        analysis = (
            analyze_live_game(
                game_id=game_id,
                season=season,
                game_date=game_date,
                top_k=3,
                assume_final=True,
            )
        )

    timeline = (
        analysis[
            "timeline"
        ]
    )

    home_metadata = (
        get_team_metadata(
            analysis[
                "home_team_id"
            ]
        )
    )

    away_metadata = (
        get_team_metadata(
            analysis[
                "away_team_id"
            ]
        )
    )

    home_team = (
        home_metadata[
            "tricode"
        ]
    )

    away_team = (
        away_metadata[
            "tricode"
        ]
    )

    momentum = (
        detect_momentum_runs(
            timeline,
            home_team=home_team,
            away_team=away_team,
            top_k=3,
        )
    )

    player_summary = (
        load_cached_player_summary(
            game_id
        )
    )

    explanations = (
        build_contextual_explanations(
            game_df=timeline,
            momentum_result=momentum,
            home_team=home_team,
            away_team=away_team,
            player_summary=player_summary,
            top_k=4,
        )
    )

    story = (
        build_game_story(
            game_df=timeline,
            explanations=explanations,
            home_team=home_team,
            away_team=away_team,
            player_summary=player_summary,
        )
    )

    if story is None:
        raise RuntimeError(
            "build_game_story() returned None."
        )

    result = (
        validate_story(
            game_id=game_id,
            timeline=timeline,
            story=story,
            explanations=explanations,
            home_team=home_team,
            away_team=away_team,
        )
    )

    result[
        "gameDate"
    ] = (
        game_date
    )

    result[
        "homeTeam"
    ] = (
        home_team
    )

    result[
        "awayTeam"
    ] = (
        away_team
    )

    result[
        "playerContextAvailable"
    ] = (
        player_summary
        is not None
    )

    return result


# ============================================================
# CLI
# ============================================================

def parse_args():
    parser = (
        argparse.ArgumentParser(
            description=(
                "Validate Courtvision Game Story v1."
            )
        )
    )

    parser.add_argument(
        "--season",
        default="2024-25",
    )

    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
    )

    return (
        parser.parse_args()
    )


def main():
    args = (
        parse_args()
    )

    games = (
        load_game_catalog(
            args.season
        )
    )

    sample = (
        select_evenly_spaced_games(
            games,
            args.sample_size,
        )
    )

    print(
        "Courtvision Game Story Validation"
    )

    print(
        "Season:",
        args.season,
    )

    print(
        "Available games:",
        len(games),
    )

    print(
        "Validation sample:",
        len(sample),
    )

    print()

    rows = []
    failures = []

    for index, row in (
        sample.iterrows()
    ):
        game_id = (
            row[
                "gameId"
            ]
        )

        game_date = (
            row[
                "gameDate"
            ]
        )

        print(
            f"[{index + 1}/"
            f"{len(sample)}] "
            f"{game_id} "
            f"{game_date.date()}",
            end=" ... ",
            flush=True,
        )

        try:
            result = (
                validate_game(
                    game_id=game_id,
                    game_date=game_date,
                    season=args.season,
                )
            )

            rows.append(
                result
            )

            if result[
                "structuralPass"
            ]:
                print(
                    "PASS"
                )

            else:
                print(
                    "FAIL"
                )

        except Exception as error:
            print(
                "ERROR"
            )

            failures.append(
                {
                    "gameId":
                        game_id,

                    "gameDate":
                        game_date,

                    "error":
                        str(error),
                }
            )

    results_df = (
        pd.DataFrame(
            rows
        )
    )

    failures_df = (
        pd.DataFrame(
            failures
        )
    )

    RESULTS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    results_path = (
        RESULTS_DIR
        / (
            f"game_story_{args.season}"
            "_validation_games.csv"
        )
    )

    failures_path = (
        RESULTS_DIR
        / (
            f"game_story_{args.season}"
            "_validation_failures.csv"
        )
    )

    results_df.to_csv(
        results_path,
        index=False,
    )

    failures_df.to_csv(
        failures_path,
        index=False,
    )

    print()
    print(
        "=" * 72
    )
    print(
        "Validation Summary"
    )
    print(
        "=" * 72
    )

    print(
        "Attempted:",
        len(sample),
    )

    print(
        "Successful:",
        len(
            results_df
        ),
    )

    print(
        "Failures:",
        len(
            failures_df
        ),
    )

    if not results_df.empty:
        passed = int(
            results_df[
                "structuralPass"
            ].sum()
        )

        print(
            "Structural PASS:",
            passed,
        )

        print(
            "Structural FAIL:",
            len(
                results_df
            )
            - passed,
        )

        print()

        print(
            "Stories with decisive run:",
            int(
                results_df[
                    "hasDecisiveRun"
                ].sum()
            ),
            "/",
            len(
                results_df
            ),
        )

        print(
            "Independent decisive candidates:",
            int(
                results_df[
                    "independentDecisiveCandidates"
                ].sum()
            ),
        )

        print()

        checks = [
            "winnerPass",
            "loserPass",
            "scorePass",
            "decisivePresencePass",
            "decisiveDurablePass",
            "decisiveSelectionPass",
            "metricLabelPass",
            "sectionLabelPass",
            "subtitlePass",
            "leadPass",
            "structuralPass",
        ]

        print(
            "Structural checks"
        )

        for column in checks:
            print(
                f"  {column}: "
                f"{int(results_df[column].sum())}/"
                f"{len(results_df)}"
            )

        print()

        display_columns = [
            "gameId",
            "awayTeam",
            "homeTeam",
            "winner",
            "winnerScore",
            "loserScore",
            "hasDecisiveRun",
            "independentDecisiveCandidates",
            "lead",
            "subtitle",
        ]

        print(
            "Validated stories"
        )

        print(
            results_df[
                display_columns
            ]
            .to_string(
                index=False
            )
        )

    print()

    print(
        "Saved:"
    )

    print(
        " ",
        results_path,
    )

    print(
        " ",
        failures_path,
    )


if __name__ == "__main__":
    main()
