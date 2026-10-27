"""Numeric leaderboard backing data, with display-only formatting in Streamlit."""
import pandas as pd


def leaderboard_display(frame, partial=False):
    table=frame.rename(columns={'Season Value':'Total Season Impact','NBA Value Rank':'NBA Impact Rank'}).copy()
    for column in ('NBA Rank','NBA Impact Rank'):
        table[column]=pd.to_numeric(table[column],errors='raise').astype('Int64')
    for column in ('Rating','Total Season Impact','Reliability'):
        table[column]=pd.to_numeric(table[column],errors='raise')
    table['Reliability']=table['Reliability']*100
    if partial:
        table=table.rename(columns={'NBA Rank':'Sample Rank','NBA Impact Rank':'Sample Impact Rank'})
    return table


def leaderboard_columns():
    import streamlit as st
    ranks={name:st.column_config.NumberColumn(format='#%d',help='Numeric rank; click to sort numerically.')
           for name in ('NBA Rank','NBA Impact Rank','Sample Rank','Sample Impact Rank')}
    return {**ranks,
            'Rating':st.column_config.NumberColumn(format='%.1f',help='Sample-adjusted impact per 36 minutes on a 100-reference rating scale.'),
            'Reliability':st.column_config.NumberColumn(format='%.0f%%'),
            'Total Season Impact':st.column_config.NumberColumn(format='%+.2f',help='Cumulative attributed win-probability impact in the selected season. Not rating points or wins added.')}
