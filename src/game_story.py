from __future__ import annotations

import pandas as pd


def _safe_float(value, default=0.0):
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default=0):
    try:
        if pd.isna(value):
            return default
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _safe_text(value, default=""):
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default
    except Exception:
        pass

    return str(value).strip()


def _period_label(period):
    period = _safe_int(
        period,
        default=1,
    )

    if period <= 4:
        return f"Q{period}"

    if period == 5:
        return "OT"

    return f"{period - 4}OT"


def _clock_label(clock):
    text = _safe_text(clock)

    if text.startswith("PT"):
        text = text[2:]

        if "M" in text:
            minutes, seconds = (
                text.split(
                    "M",
                    1,
                )
            )

            seconds = (
                seconds
                .replace(
                    "S",
                    "",
                )
            )

            try:
                second_value = float(
                    seconds
                )

                if second_value.is_integer():
                    seconds = (
                        f"{int(second_value):02d}"
                    )

                else:
                    seconds = (
                        f"{second_value:04.1f}"
                    )

                return (
                    f"{int(minutes)}:"
                    f"{seconds}"
                )

            except ValueError:
                pass

    return text


def _window_label(explanation):
    start = (
        f"{_period_label(explanation.get('startPeriod'))} "
        f"{_clock_label(explanation.get('startClock'))}"
    )

    end = (
        f"{_period_label(explanation.get('endPeriod'))} "
        f"{_clock_label(explanation.get('endClock'))}"
    )

    return f"{start}–{end}"


def _final_live_row(game_df):
    df = game_df.copy()

    if "isTerminalState" in df.columns:
        non_terminal = df[
            df["isTerminalState"] == False
        ].copy()

        if not non_terminal.empty:
            df = non_terminal

    if "elapsedGameTime" in df.columns:
        df = df.sort_values(
            "elapsedGameTime",
            kind="mergesort",
        )

    if df.empty:
        return None

    return df.iloc[-1]


def _final_score(
    game_df,
    home_team,
    away_team,
):
    row = _final_live_row(
        game_df
    )

    if row is None:
        return None

    home_score = _safe_int(
        row.get(
            "scoreHome"
        )
    )

    away_score = _safe_int(
        row.get(
            "scoreAway"
        )
    )

    if home_score > away_score:
        winner = home_team
        loser = away_team
        winner_score = home_score
        loser_score = away_score

    elif away_score > home_score:
        winner = away_team
        loser = home_team
        winner_score = away_score
        loser_score = home_score

    else:
        winner = None
        loser = None
        winner_score = home_score
        loser_score = away_score

    return {
        "homeScore":
            home_score,

        "awayScore":
            away_score,

        "winner":
            winner,

        "loser":
            loser,

        "winnerScore":
            winner_score,

        "loserScore":
            loser_score,

        "margin":
            abs(
                home_score
                - away_score
            ),
    }


def _team_wp(
    game_df,
    team,
    home_team,
):
    df = game_df.copy()

    if "isTerminalState" in df.columns:
        df = df[
            df["isTerminalState"] == False
        ].copy()

    values = pd.to_numeric(
        df["winProbability"],
        errors="coerce",
    )

    if team == home_team:
        return values

    return 1.0 - values


def _game_shape_description(
    game_df,
    winner,
    home_team,
):
    wp = (
        _team_wp(
            game_df=game_df,
            team=winner,
            home_team=home_team,
        )
        .dropna()
    )

    if wp.empty:
        return (
            f"{winner} ultimately created "
            "the separation needed to win."
        )

    mean_wp = float(
        wp.mean()
    )

    minimum_wp = float(
        wp.min()
    )

    below_50 = float(
        (wp < 0.50).mean()
    )

    above_70 = float(
        (wp >= 0.70).mean()
    )

    if (
        minimum_wp <= 0.25
        and below_50 >= 0.25
    ):
        return (
            f"{winner} spent meaningful time on the wrong "
            "side of the game before mounting a comeback."
        )

    if (
        mean_wp >= 0.70
        and above_70 >= 0.45
    ):
        return (
            f"{winner} controlled most of the game and "
            "rarely allowed the result to become uncertain."
        )

    if (
        0.42 <= mean_wp <= 0.68
    ):
        return (
            "The game stayed competitive for long stretches "
            f"before {winner} finally created separation."
        )

    return (
        f"{winner} gradually took control and built "
        "enough separation to finish the job."
    )



def _winner_margin(
    row,
    winner,
    home_team,
):
    home_score = _safe_int(
        row.get(
            "scoreHome"
        )
    )

    away_score = _safe_int(
        row.get(
            "scoreAway"
        )
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


def _is_durable_winner_run(
    game_df,
    explanation,
    winner,
    home_team,
):
    """
    A decisive run must:

    1. belong to the eventual winner,
    2. end in Q4 or overtime,
    3. leave the winner ahead,
    4. never have that lead erased afterward.

    "Erased" means the game later becomes tied or the
    eventual winner falls behind.
    """

    if explanation.get(
        "team"
    ) != winner:
        return False

    end_period = _safe_int(
        explanation.get(
            "endPeriod"
        )
    )

    if end_period < 4:
        return False

    end_elapsed = _safe_float(
        explanation.get(
            "endElapsed"
        ),
        default=-1.0,
    )

    if end_elapsed < 0:
        return False

    after_margin = _safe_int(
        explanation.get(
            "afterMargin"
        )
    )

    # The run must actually leave the eventual winner ahead.
    if after_margin <= 0:
        return False

    timeline = game_df.copy()

    if "isTerminalState" in timeline.columns:
        timeline = timeline[
            timeline[
                "isTerminalState"
            ]
            == False
        ].copy()

    timeline[
        "elapsedGameTime"
    ] = pd.to_numeric(
        timeline[
            "elapsedGameTime"
        ],
        errors="coerce",
    )

    later = (
        timeline[
            timeline[
                "elapsedGameTime"
            ]
            > end_elapsed
        ]
        .copy()
    )

    # If the run reaches the final observable state while the
    # winner is ahead, there is no later opportunity to erase it.
    if later.empty:
        return True

    later_margins = (
        later.apply(
            lambda row:
                _winner_margin(
                    row=row,
                    winner=winner,
                    home_team=home_team,
                ),
            axis=1,
        )
    )

    if later_margins.empty:
        return True

    # Durable separation means the opponent never even gets
    # back to a tie after this run.
    return bool(
        (
            later_margins
            > 0
        )
        .all()
    )


def _select_decisive_run(
    game_df,
    explanations,
    winner,
    home_team,
):
    candidates = [
        explanation
        for explanation
        in explanations
        if _is_durable_winner_run(
            game_df=game_df,
            explanation=explanation,
            winner=winner,
            home_team=home_team,
        )
    ]

    if not candidates:
        return None

    # Among genuinely durable late-game runs, use the strongest
    # contextual run rather than simply the latest one.
    return max(
        candidates,
        key=lambda item:
            _safe_float(
                item.get(
                    "contextScore"
                )
            ),
    )


def _best_explanation(
    explanations,
    team=None,
):
    if not explanations:
        return None

    candidates = explanations

    if team is not None:
        candidates = [
            explanation
            for explanation
            in explanations
            if explanation.get(
                "team"
            )
            == team
        ]

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda item:
            _safe_float(
                item.get(
                    "contextScore"
                )
            ),
    )


def _top_player(
    player_summary,
    team,
):
    if (
        player_summary is None
        or not isinstance(
            player_summary,
            pd.DataFrame,
        )
        or player_summary.empty
    ):
        return None

    required = {
        "player",
        "team",
        "net_wpa_pp",
    }

    if not required.issubset(
        player_summary.columns
    ):
        return None

    team_df = (
        player_summary[
            player_summary[
                "team"
            ]
            == team
        ]
        .copy()
    )

    if team_df.empty:
        return None

    team_df[
        "net_wpa_pp"
    ] = pd.to_numeric(
        team_df[
            "net_wpa_pp"
        ],
        errors="coerce",
    )

    team_df = (
        team_df.dropna(
            subset=[
                "net_wpa_pp",
            ]
        )
    )

    if team_df.empty:
        return None

    row = (
        team_df
        .sort_values(
            "net_wpa_pp",
            ascending=False,
        )
        .iloc[0]
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


def _run_sentence(
    explanation,
    lead_in,
):
    team = explanation[
        "team"
    ]

    opponent = explanation[
        "opponent"
    ]

    team_points = _safe_int(
        explanation.get(
            "beneficiaryPoints"
        )
    )

    opponent_points = _safe_int(
        explanation.get(
            "opponentPoints"
        )
    )

    swing = _safe_float(
        explanation.get(
            "winProbabilitySwingPoints"
        )
    )

    margin_text = _safe_text(
        explanation.get(
            "marginDescription"
        )
    )

    window = _window_label(
        explanation
    )

    sentence = (
        f"{lead_in} {window}, {team} went on a "
        f"{team_points}–{opponent_points} run against "
        f"{opponent}, increasing its win probability by "
        f"{swing:.1f} points"
    )

    if margin_text:
        sentence += (
            f" and {margin_text}"
        )

    return sentence + "."



def _decisive_run_sentence(
    explanation,
):
    team = explanation[
        "team"
    ]

    opponent = explanation[
        "opponent"
    ]

    team_points = _safe_int(
        explanation.get(
            "beneficiaryPoints"
        )
    )

    opponent_points = _safe_int(
        explanation.get(
            "opponentPoints"
        )
    )

    swing = _safe_float(
        explanation.get(
            "winProbabilitySwingPoints"
        )
    )

    margin_text = _safe_text(
        explanation.get(
            "marginDescription"
        )
    )

    period = _period_label(
        explanation.get(
            "startPeriod"
        )
    )

    clock = _clock_label(
        explanation.get(
            "startClock"
        )
    )

    sentence = (
        f"With {clock} remaining in {period}, "
        f"{team} went on a "
        f"{team_points}–{opponent_points} run "
        f"against {opponent}, increasing its win probability "
        f"by {swing:.1f} points"
    )

    if margin_text:
        sentence += (
            f" and {margin_text}"
        )

    return sentence + "."


def build_game_story(
    game_df,
    explanations,
    home_team,
    away_team,
    player_summary=None,
):
    score = _final_score(
        game_df=game_df,
        home_team=home_team,
        away_team=away_team,
    )

    if score is None:
        return None

    winner = score[
        "winner"
    ]

    loser = score[
        "loser"
    ]

    if winner is None:
        return {
            "winner":
                None,

            "lead":
                (
                    f"{away_team} and {home_team} are tied "
                    f"{score['awayScore']}–"
                    f"{score['homeScore']} in the "
                    "available game state."
                ),

            "subtitle":
                "No winner is available yet.",

            "metrics":
                [],

            "sections":
                [],
        }

    winner_explanations = [
        explanation
        for explanation
        in explanations
        if explanation.get(
            "team"
        ) == winner
    ]

    decisive = (
        _select_decisive_run(
            game_df=game_df,
            explanations=winner_explanations,
            winner=winner,
            home_team=home_team,
        )
    )

    biggest_winner_run = (
        _best_explanation(
            explanations,
            team=winner,
        )
    )

    primary = (
        decisive
        if decisive is not None
        else biggest_winner_run
    )

    response = _best_explanation(
        explanations,
        team=loser,
    )

    margin = score[
        "margin"
    ]

    lead = (
        f"{winner} defeated {loser} "
        f"{score['winnerScore']}–"
        f"{score['loserScore']}."
    )

    shape = (
        _game_shape_description(
            game_df=game_df,
            winner=winner,
            home_team=home_team,
        )
    )

    if decisive is not None:
        decisive_period = _safe_int(
            decisive.get(
                "endPeriod"
            )
        )

        if decisive_period == 4:
            decisive_stage = (
                "fourth-quarter"
            )
        else:
            decisive_stage = (
                "overtime"
            )

        subtitle = (
            f"{winner} created the separation it needed "
            f"with a decisive {decisive_stage} run."
        )

    elif margin >= 15:
        subtitle = (
            f"{winner} eventually turned the game "
            "into a comfortable final margin."
        )

    elif margin <= 5:
        subtitle = (
            f"{winner} survived a close finish."
        )

    else:
        subtitle = (
            f"{winner} finished ahead after a game "
            "with multiple meaningful swings."
        )

    metrics = []

    if primary is not None:
        primary_metric_label = (
            "Decisive run"
            if decisive is not None
            else "Biggest run"
        )

        metrics = [
            {
                "label":
                    primary_metric_label,

                "value":
                    (
                        f"{_safe_int(primary.get('beneficiaryPoints'))}"
                        f"–"
                        f"{_safe_int(primary.get('opponentPoints'))}"
                    ),
            },
            {
                "label":
                    "Win probability",

                "value":
                    (
                        f"+{_safe_float(primary.get('winProbabilitySwingPoints')):.1f} pp"
                    ),
            },
            {
                "label":
                    "Key window",

                "value":
                    _window_label(
                        primary
                    ),
            },
        ]

    sections = [
        {
            "label":
                "Game flow",

            "text":
                shape,
        }
    ]

    if response is not None:
        sections.append(
            {
                "label":
                    f"{loser} response",

                "text":
                    _run_sentence(
                        response,
                        lead_in=(
                            f"{loser}'s strongest answer came from"
                        ),
                    ),
            }
        )

    if primary is not None:
        if decisive is not None:
            section_label = (
                "Decisive stretch"
            )

            section_text = (
                _decisive_run_sentence(
                    primary
                )
            )

        else:
            section_label = (
                f"Biggest {winner} surge"
            )

            section_text = (
                _run_sentence(
                    primary,
                    lead_in=(
                        f"{winner}'s largest momentum "
                        "swing came from"
                    ),
                )
            )

        sections.append(
            {
                "label":
                    section_label,

                "text":
                    section_text,
            }
        )

    winner_player = _top_player(
        player_summary,
        winner,
    )

    loser_player = _top_player(
        player_summary,
        loser,
    )

    player_parts = []

    if winner_player is not None:
        player_parts.append(
            f"{winner_player['player']} led {winner} "
            f"with {winner_player['netWPA']:+.1f} "
            "Courtvision WPA points"
        )

    if loser_player is not None:
        player_parts.append(
            f"{loser_player['player']} posted {loser}'s "
            f"strongest mark at "
            f"{loser_player['netWPA']:+.1f}"
        )

    if player_parts:
        sections.append(
            {
                "label":
                    "Key contributors",

                "text":
                    ". ".join(
                        player_parts
                    )
                    + ".",
            }
        )

    return {
        "winner":
            winner,

        "loser":
            loser,

        "lead":
            lead,

        "subtitle":
            subtitle,

        "metrics":
            metrics,

        "sections":
            sections,

        "primaryExplanation":
            primary,

        "decisiveExplanation":
            decisive,

        "biggestWinnerRun":
            biggest_winner_run,

        "responseExplanation":
            response,

        "finalScore":
            score,
    }
