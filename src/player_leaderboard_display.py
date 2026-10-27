"""Compact season leaderboard with numeric sorting and display-only formatting."""
import pandas as pd


def leaderboard_display(frame, partial=False):
    table=frame[['NBA Rank', 'Player', 'Team', 'Games', 'Rating', 'Status']].copy()
    table['NBA Rank']=pd.to_numeric(table['NBA Rank'],errors='raise').astype('Int64')
    for column in ('Games','Rating'):
        table[column]=pd.to_numeric(table[column],errors='raise')
    if partial:
        table=table.rename(columns={'NBA Rank':'Sample Rank'})
    return table


def leaderboard_columns():
    import streamlit as st
    ranks={name:st.column_config.NumberColumn(format='#%d',help='Numeric rank; click to sort numerically.')
           for name in ('NBA Rank','Sample Rank')}
    return {**ranks,
            'Rating':st.column_config.NumberColumn(format='%.1f',help='Sample-adjusted impact per 36 minutes on a 100-reference rating scale.'),
            'Games':st.column_config.NumberColumn(format='%d'),
            'Status':st.column_config.TextColumn(help='Qualified: at least 10 games and 60% sample-size weight. Otherwise provisional.')}
