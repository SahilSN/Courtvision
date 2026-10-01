import re
import sys

import pandas as pd

from replay_box_score import (
    build_player_aliases,
    resolve_description_player,
    get_full_player_name,
)


def clean_text(value):
    if value is None:
        return ""

    try:
        if value != value:
            return ""
    except Exception:
        pass

    return str(value).strip()


def clean_person_id(value):
    try:
        value = int(value)

        if value > 0:
            return value

    except (
        TypeError,
        ValueError,
    ):
        pass

    return None


def parse_substitution(
    row,
    alias_to_ids,
):
    description = clean_text(
        row.get(
            "description",
            "",
        )
    )

    match = re.match(
        r"^SUB:\s+(.+?)\s+FOR\s+(.+?)$",
        description,
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    incoming_alias = (
        match.group(1)
        .strip()
    )

    outgoing_alias = (
        match.group(2)
        .strip()
    )

    team = clean_text(
        row.get(
            "teamTricode",
            "",
        )
    )

    outgoing_id = (
        clean_person_id(
            row.get(
                "personId",
                None,
            )
        )
    )

    if outgoing_id is None:
        outgoing_id = (
            resolve_description_player(
                team,
                outgoing_alias,
                alias_to_ids,
            )
        )

    incoming_id = (
        resolve_description_player(
            team,
            incoming_alias,
            alias_to_ids,
        )
    )

    return {
        "team":
            team,

        "incoming_id":
            incoming_id,

        "incoming_alias":
            incoming_alias,

        "outgoing_id":
            outgoing_id,

        "outgoing_alias":
            outgoing_alias,
    }


def display_player(
    person_id,
    fallback,
):
    if person_id is None:
        return (
            f"{fallback} [UNRESOLVED]"
        )

    return (
        get_full_player_name(
            person_id
        )
        or fallback
        or str(person_id)
    )


def infer_period_starters(
    period_df,
    team,
    alias_to_ids,
):
    team_df = (
        period_df.loc[
            period_df[
                "teamTricode"
            ].astype(str)
            == team
        ]
        .copy()
        .reset_index(drop=True)
    )

    first_sub_role = {}
    observed_before_in = set()
    player_fallbacks = {}
    unresolved_subs = []

    entered = set()

    for _, row in team_df.iterrows():
        action_type = clean_text(
            row.get(
                "actionType",
                "",
            )
        )

        person_id = clean_person_id(
            row.get(
                "personId",
                None,
            )
        )

        player_name = clean_text(
            row.get(
                "playerName",
                "",
            )
        )

        if (
            person_id is not None
            and player_name
        ):
            player_fallbacks[
                person_id
            ] = player_name

        if action_type == "Substitution":
            parsed = parse_substitution(
                row,
                alias_to_ids,
            )

            if parsed is None:
                continue

            incoming_id = parsed[
                "incoming_id"
            ]

            outgoing_id = parsed[
                "outgoing_id"
            ]

            if (
                incoming_id is None
                or outgoing_id is None
            ):
                unresolved_subs.append(
                    parsed
                )

            if outgoing_id is not None:
                first_sub_role.setdefault(
                    outgoing_id,
                    "OUT",
                )

            if incoming_id is not None:
                first_sub_role.setdefault(
                    incoming_id,
                    "IN",
                )

                entered.add(
                    incoming_id
                )

            continue

        if (
            person_id is not None
            and person_id not in entered
        ):
            observed_before_in.add(
                person_id
            )

    starters = {
        person_id
        for person_id, role
        in first_sub_role.items()
        if role == "OUT"
    }

    starters.update(
        observed_before_in
    )

    return {
        "starters":
            starters,

        "first_sub_role":
            first_sub_role,

        "observed_before_in":
            observed_before_in,

        "fallbacks":
            player_fallbacks,

        "unresolved_subs":
            unresolved_subs,
    }


def main():
    game_id = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "0022501188"
    )

    path = (
        f"data/processed/{game_id}.csv"
    )

    df = pd.read_csv(
        path,
        dtype={
            "gameId": str,
        },
    )

    (
        alias_to_ids,
        _,
    ) = build_player_aliases(
        df
    )

    teams = [
        team
        for team
        in df[
            "teamTricode"
        ]
        .astype(str)
        .unique()
        .tolist()
        if (
            team
            and team != "nan"
        )
    ]

    periods = sorted(
        pd.to_numeric(
            df[
                "period"
            ],
            errors="coerce",
        )
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )

    print(
        f"Period Starter Diagnostic — {game_id}"
    )

    print()

    all_pass = True

    for period in periods:
        period_df = (
            df.loc[
                pd.to_numeric(
                    df[
                        "period"
                    ],
                    errors="coerce",
                )
                == period
            ]
            .copy()
        )

        for team in teams:
            result = (
                infer_period_starters(
                    period_df,
                    team,
                    alias_to_ids,
                )
            )

            starters = (
                result[
                    "starters"
                ]
            )

            names = [
                display_player(
                    person_id,
                    result[
                        "fallbacks"
                    ].get(
                        person_id,
                        "",
                    ),
                )
                for person_id
                in sorted(
                    starters
                )
            ]

            status = (
                "PASS"
                if len(starters) == 5
                else "FAIL"
            )

            if status == "FAIL":
                all_pass = False

            print(
                f"Q{period} {team}: "
                f"{len(starters)} starters "
                f"[{status}]"
            )

            for name in names:
                print(
                    f"  - {name}"
                )

            if (
                result[
                    "unresolved_subs"
                ]
            ):
                print(
                    "  unresolved substitutions:"
                )

                for substitution in (
                    result[
                        "unresolved_subs"
                    ]
                ):
                    print(
                        "   ",
                        substitution,
                    )

            print()

    if not all_pass:
        raise RuntimeError(
            "At least one team-period did not "
            "resolve to exactly five starters."
        )

    print(
        "✓ Every team-period resolved to exactly five starters."
    )


if __name__ == "__main__":
    main()
