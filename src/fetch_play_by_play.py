import os
import pandas as pd

from nba_api.stats.static import teams
from nba_api.stats.endpoints import leaguegamefinder
from nba_api.stats.library.parameters import Season, SeasonType
from nba_api.stats.endpoints import playbyplayv3


def make_df():
    # Get the Pacers team_id
    nba_teams = teams.get_teams()

    pacers = [
        team for team in nba_teams
        if team["abbreviation"] == "IND"
    ][0]

    pacers_id = pacers["id"]

    print(f"pacers_id: {pacers_id}")


    # Find Pacers games
    gamefinder = leaguegamefinder.LeagueGameFinder(
        team_id_nullable=pacers_id,
        season_nullable=Season.default,
        season_type_nullable=SeasonType.regular,
        timeout=60,
    )

    games_dict = gamefinder.get_normalized_dict()
    games = games_dict["LeagueGameFinderResults"]

    game = games[0]

    game_id = game["GAME_ID"]
    game_matchup = game["MATCHUP"]

    print(
        f"Searching through {len(games)} game(s) "
        f"for the game_id of {game_id} where {game_matchup}"
    )


    pbp = playbyplayv3.PlayByPlayV3(
        game_id=game_id,
        timeout=60,
    )

    df = pbp.get_data_frames()[0]

    os.makedirs("data/raw", exist_ok=True)

    output_path = f"data/raw/{game_id}.csv"
    df.to_csv(output_path, index=False)

    print(f"Saved raw play-by-play to {output_path}")

    return df


def print_df(df):
    print(df.head())
    print("\nColumns:")
    print(df.columns.tolist())

    print(df.shape)

    print("\nAction types:")
    print(df["actionType"].value_counts(dropna=False))

    print("\nSubtypes:")
    print(df["subType"].value_counts(dropna=False))

    print("\nMissing values:")
    print(df.isna().sum())

    print("\nSample events:")
    print(
        df[
            [
                "period",
                "clock",
                "teamTricode",
                "playerName",
                "description",
                "actionType",
                "subType",
                "scoreHome",
                "scoreAway",
            ]
        ].head(30).to_string(index=False)
    )

    for event_type in [
        "Made Shot",
        "Missed Shot",
        "Rebound",
        "Turnover",
        "Foul",
        "Substitution",
        "Timeout",
    ]:
        print(f"\n--- {event_type} ---")
        print(
            df[df["actionType"] == event_type][
                ["clock", "playerName", "description", "subType"]
            ].head()
        )

    print(
        df[
            [
                "actionNumber",
                "actionId",
                "period",
                "clock",
                "teamTricode",
                "playerName",
                "description",
                "actionType",
                "subType",
                "scoreHome",
                "scoreAway",
            ]
        ].head(50).to_string(index=False)
    )

    counts = df["actionNumber"].value_counts()

    repeated_action_numbers = counts[counts > 1].index

    repeated = df[df["actionNumber"].isin(repeated_action_numbers)]

    print(
        repeated[
            [
                "actionNumber",
                "actionId",
                "clock",
                "teamTricode",
                "description",
                "actionType",
            ]
        ].head(50).to_string(index=False)
    )

    print("Rows:", len(df))
    print("Unique actionNumbers:", df["actionNumber"].nunique())
    print("Unique actionIds:", df["actionId"].nunique())

make_df()