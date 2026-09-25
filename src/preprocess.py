import pandas as pd

# from fetch_play_by_play import make_df


def parse_clock(clock, period_length):
    minutes_remaining = int(clock[2:4])
    seconds_remaining = float(clock[5:10])

    remaining = minutes_remaining * 60 + seconds_remaining

    return period_length - remaining


def fill_scores(df):
    df["scoreHome"] = df["scoreHome"].ffill().fillna(0).astype(int)
    df["scoreAway"] = df["scoreAway"].ffill().fillna(0).astype(int)

    df["homeScoreDiff"] = df['scoreHome'] - df["scoreAway"]

    return df


def add_elapsed_game_time(df):
    for index, row in df.iterrows():
        period = row.period

        if 1 <= period <= 4:
            df.at[index, "elapsedGameTime"] = (
                720 * (period - 1)
                + parse_clock(row.clock, 720)
            )
        else:
            overtime_period = period - 5

            df.at[index, "elapsedGameTime"] = (
                2880
                + 300 * overtime_period
                + parse_clock(row.clock, 300)
            )

    return df

df = pd.read_csv("data/raw/0022501188.csv")

df = add_elapsed_game_time(df)
df = fill_scores(df)

df.to_csv("data/processed/0022501188.csv", index=False)

print(
    df[
        [
            "period",
            "clock",
            "actionType",
            "scoreHome",
            "scoreAway",
            "homeScoreDiff"
        ]
    ].head(30).to_string(index=False)
)

print(df.isna().sum())
df.to_csv("data/processed/0022501188.csv", index=False)