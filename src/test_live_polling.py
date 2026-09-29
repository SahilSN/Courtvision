import argparse
import time
from datetime import datetime

from live_analysis import (
    fetch_live_play_by_play,
)


def summarize_last_action(
    df,
):
    if df.empty:
        return None

    row = (
        df.iloc[-1]
    )

    return {
        "rows":
            len(df),

        "action_id":
            row.get(
                "actionId",
                row.get(
                    "actionNumber",
                None,
            ),
        ),

        "period":
            row.get(
                "period"
            ),

        "clock":
            row.get(
                "clock"
            ),

        "score_home":
            row.get(
                "scoreHome"
            ),

        "score_away":
            row.get(
                "scoreAway"
            ),

        "description":
            row.get(
                "description"
            ),
    }


def signature(
    summary,
):
    if summary is None:
        return None

    return (
        summary[
            "rows"
        ],
        summary[
            "action_id"
        ],
        summary[
            "period"
        ],
        summary[
            "clock"
        ],
        summary[
            "score_home"
        ],
        summary[
            "score_away"
        ],
    )


def main():
    parser = (
        argparse.ArgumentParser()
    )

    parser.add_argument(
        "game_id"
    )

    parser.add_argument(
        "--interval",
        type=float,
        default=15.0,
    )

    parser.add_argument(
        "--max-polls",
        type=int,
        default=40,
    )

    args = (
        parser.parse_args()
    )

    previous_signature = (
        None
    )

    print(
        "Courtvision "
        "live polling test"
    )

    print(
        "Game:",
        args.game_id,
    )

    print(
        "Interval:",
        args.interval,
        "seconds",
    )

    print()

    for poll_number in range(
        1,
        args.max_polls + 1,
    ):
        timestamp = (
            datetime.now()
            .strftime(
                "%H:%M:%S"
            )
        )

        try:
            df = (
                fetch_live_play_by_play(
                    args.game_id
                )
            )

            summary = (
                summarize_last_action(
                    df
                )
            )

            current_signature = (
                signature(
                    summary
                )
            )

            changed = (
                current_signature
                != previous_signature
            )

            status = (
                "UPDATE"
                if changed
                else "no change"
            )

            print(
                f"[{timestamp}] "
                f"poll "
                f"{poll_number:02d} | "
                f"{status}"
            )

            if (
                summary
                is not None
            ):
                print(
                    "  "
                    f"rows="
                    f"{summary['rows']} "
                    "| "
                    f"Q"
                    f"{summary['period']} "
                    f"{summary['clock']} "
                    "| "
                    f"{summary['score_away']}"
                    "-"
                    f"{summary['score_home']}"
                )

                print(
                    "  "
                    f"{summary['description']}"
                )

            previous_signature = (
                current_signature
            )

        except Exception as error:
            print(
                f"[{timestamp}] "
                "ERROR | "
                f"{error}"
            )

        if (
            poll_number
            < args.max_polls
        ):
            time.sleep(
                args.interval
            )


if __name__ == "__main__":
    main()