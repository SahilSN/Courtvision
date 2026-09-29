import argparse
import re

import matplotlib.pyplot as plt
import pandas as pd

from analysis import analyze_game


# -------------------------
# Configuration
# -------------------------

PROCESSED_DATA_DIR = "data/processed"


# -------------------------
# CLI arguments
# -------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Generate Courtvision win probability "
            "analysis for an NBA game."
        )
    )

    parser.add_argument(
        "game_id",
        type=int,
        help=(
            "NBA game ID, for example "
            "22401197 or 0022401197."
        ),
    )

    return parser.parse_args()


# -------------------------
# Game ID formatting
# -------------------------

def normalize_game_id(game_id):
    return str(game_id).zfill(10)


# -------------------------
# Clock formatting
# -------------------------

def format_clock(clock):
    match = re.fullmatch(
        r"PT(\d+)M(\d+(?:\.\d+)?)S",
        clock,
    )

    if match is None:
        return clock

    minutes = int(
        match.group(1)
    )

    seconds = int(
        float(
            match.group(2)
        )
    )

    return (
        f"{minutes}:"
        f"{seconds:02d}"
    )


# -------------------------
# Attach play-by-play details
# -------------------------

def add_play_by_play_details(
    game_df,
    game_id,
):
    nba_game_id = (
        normalize_game_id(
            game_id
        )
    )

    processed_path = (
        f"{PROCESSED_DATA_DIR}/"
        f"{nba_game_id}.csv"
    )

    processed_df = pd.read_csv(
        processed_path,
        dtype={
            "gameId": str,
        },
    )

    processed_df = (
        processed_df
        .dropna(
            subset=[
                "homePossession"
            ]
        )
        .reset_index(drop=True)
    )

    game_df = (
        game_df
        .reset_index(drop=True)
    )

    if (
        len(processed_df)
        != len(game_df)
    ):
        raise ValueError(
            f"Row mismatch for game "
            f"{nba_game_id}: "
            f"{len(game_df)} prediction rows "
            f"vs "
            f"{len(processed_df)} "
            f"processed rows."
        )

    detail_columns = [
        "period",
        "clock",
        "teamTricode",
        "actionType",
        "description",
    ]

    for column in detail_columns:
        game_df[column] = (
            processed_df[column]
        )

    return game_df


# -------------------------
# Print turning points
# -------------------------

def print_turning_points(
    home_swings,
    away_swings,
):
    print(
        "\nBiggest home-team swings:"
    )

    for _, row in (
        home_swings.iterrows()
    ):
        before = (
            row[
                "previousWinProbability"
            ]
            * 100
        )

        after = (
            row[
                "winProbability"
            ]
            * 100
        )

        change = (
            row[
                "probabilityChange"
            ]
            * 100
        )

        clock = format_clock(
            row["clock"]
        )

        print(
            f"Q{int(row['period'])} "
            f"{clock} | "
            f"{row['description']}"
        )

        print(
            "  Home win probability: "
            f"{before:.1f}% -> "
            f"{after:.1f}% "
            f"({change:+.1f} pp)"
        )

    print(
        "\nBiggest away-team swings:"
    )

    for _, row in (
        away_swings.iterrows()
    ):
        before = (
            row[
                "previousWinProbability"
            ]
            * 100
        )

        after = (
            row[
                "winProbability"
            ]
            * 100
        )

        change = (
            row[
                "probabilityChange"
            ]
            * 100
        )

        clock = format_clock(
            row["clock"]
        )

        print(
            f"Q{int(row['period'])} "
            f"{clock} | "
            f"{row['description']}"
        )

        print(
            "  Home win probability: "
            f"{before:.1f}% -> "
            f"{after:.1f}% "
            f"({change:+.1f} pp)"
        )


# -------------------------
# Plot game
# -------------------------

def plot_game(
    game_df,
    home_swings,
    away_swings,
    game_id,
):
    fig, ax = plt.subplots(
        figsize=(12, 6)
    )

    # -------------------------
    # Win probability curve
    # -------------------------

    ax.plot(
        game_df[
            "elapsedGameTime"
        ],
        game_df[
            "winProbability"
        ],
        linewidth=2,
        label=(
            "Home win probability"
        ),
    )

    # -------------------------
    # Quarter boundaries
    # -------------------------

    quarter_boundaries = [
        720,
        1440,
        2160,
    ]

    for boundary in (
        quarter_boundaries
    ):
        ax.axvline(
            x=boundary,
            linestyle="--",
            alpha=0.4,
        )

    # -------------------------
    # 50% reference line
    # -------------------------

    ax.axhline(
        y=0.5,
        linestyle="--",
        alpha=0.4,
    )

    # -------------------------
    # Home-team turning points
    # -------------------------

    ax.scatter(
        home_swings[
            "elapsedGameTime"
        ],
        home_swings[
            "winProbability"
        ],
        zorder=5,
        label=(
            "Home-team swing"
        ),
    )

    home_offsets = [
        (10, 25),
        (-65, 25),
        (10, 45),
    ]

    for i, (_, row) in enumerate(
        home_swings.iterrows()
    ):
        clock = format_clock(
            row["clock"]
        )

        change = (
            row[
                "probabilityChange"
            ]
            * 100
        )

        annotation = (
            f"Q{int(row['period'])} "
            f"{clock}\n"
            f"{change:+.1f} pp"
        )

        (
            x_offset,
            y_offset,
        ) = home_offsets[
            i % len(home_offsets)
        ]

        ax.annotate(
            annotation,
            xy=(
                row[
                    "elapsedGameTime"
                ],
                row[
                    "winProbability"
                ],
            ),
            xytext=(
                x_offset,
                y_offset,
            ),
            textcoords=(
                "offset points"
            ),
            fontsize=9,
            ha="center",
            arrowprops={
                "arrowstyle": "->",
                "alpha": 0.6,
            },
        )

    # -------------------------
    # Away-team turning points
    # -------------------------

    ax.scatter(
        away_swings[
            "elapsedGameTime"
        ],
        away_swings[
            "winProbability"
        ],
        zorder=5,
        label=(
            "Away-team swing"
        ),
    )

    away_offsets = [
        (10, -45),
        (15, -35),
        (-55, -45),
    ]

    for i, (_, row) in enumerate(
        away_swings.iterrows()
    ):
        clock = format_clock(
            row["clock"]
        )

        change = (
            row[
                "probabilityChange"
            ]
            * 100
        )

        annotation = (
            f"Q{int(row['period'])} "
            f"{clock}\n"
            f"{change:+.1f} pp"
        )

        (
            x_offset,
            y_offset,
        ) = away_offsets[
            i % len(away_offsets)
        ]

        ax.annotate(
            annotation,
            xy=(
                row[
                    "elapsedGameTime"
                ],
                row[
                    "winProbability"
                ],
            ),
            xytext=(
                x_offset,
                y_offset,
            ),
            textcoords=(
                "offset points"
            ),
            fontsize=9,
            ha="center",
            arrowprops={
                "arrowstyle": "->",
                "alpha": 0.6,
            },
        )

    # -------------------------
    # Axis limits
    # -------------------------

    ax.set_ylim(
        0,
        1,
    )

    max_elapsed = float(
        game_df[
            "elapsedGameTime"
        ].max()
    )

    ax.set_xlim(
        0,
        max(
            2880,
            max_elapsed,
        ),
    )

    # -------------------------
    # Quarter labels
    # -------------------------

    ax.set_xticks(
        [
            0,
            720,
            1440,
            2160,
            2880,
        ]
    )

    ax.set_xticklabels(
        [
            "Start",
            "Q2",
            "Q3",
            "Q4",
            "End",
        ]
    )

    # -------------------------
    # Probability labels
    # -------------------------

    y_ticks = [
        0.0,
        0.2,
        0.4,
        0.5,
        0.6,
        0.8,
        1.0,
    ]

    ax.set_yticks(
        y_ticks
    )

    ax.set_yticklabels(
        [
            f"{int(value * 100)}%"
            for value in y_ticks
        ]
    )

    # -------------------------
    # Labels and title
    # -------------------------

    display_game_id = (
        normalize_game_id(
            game_id
        )
    )

    ax.set_xlabel(
        "Game Progress"
    )

    ax.set_ylabel(
        "Home Win Probability"
    )

    ax.set_title(
        "Courtvision Win Probability — "
        f"Game {display_game_id}"
    )

    # -------------------------
    # Styling
    # -------------------------

    ax.grid(
        axis="y",
        alpha=0.2,
    )

    ax.legend()

    plt.tight_layout()

    plt.show()


# -------------------------
# Main CLI
# -------------------------

def main():
    args = parse_args()

    result = analyze_game(
        game_id=args.game_id,
        add_play_by_play_details_fn=(
            add_play_by_play_details
        ),
        top_k=3,
    )

    game_df = result[
        "timeline"
    ]

    home_swings = result[
        "home_swings"
    ]

    away_swings = result[
        "away_swings"
    ]

    current_probability = result[
        "current_home_win_probability"
    ]

    final_probability = result[
        "final_home_win_probability"
    ]

    print_turning_points(
        home_swings,
        away_swings,
    )

    print(
        "\nLast model home win probability:",
        f"{current_probability:.1%}",
    )

    print(
        "Final known home win probability:",
        f"{final_probability:.1%}",
    )

    print(
        "Final score:",
        f"{result['final_home_score']}"
        " - "
        f"{result['final_away_score']}",
    )

    plot_game(
        game_df,
        home_swings,
        away_swings,
        args.game_id,
    )


if __name__ == "__main__":
    main()