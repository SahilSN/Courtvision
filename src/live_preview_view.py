"""Preview-only presentation contract. No HTTP, discovery, model loads or timers."""

import plotly.graph_objects as go
import streamlit as st


def render_live_analysis(result, home_label='Home', away_label='Away'):
    st.subheader('Win probability')
    if result is None:
        st.info('Live analysis unavailable. A verified feed and dated pregame context are required. No estimate is shown.')
        return
    snapshot = result.snapshot
    if result.display_state == 'stale_snapshot':
        st.warning('Feed refresh failed or is delayed. Showing the last validated snapshot—not the current game state.')
    elif result.display_state == 'possibly_stalled':
        st.warning('The active feed has not changed recently. Play may be stopped or updates may be delayed.')
    elif result.display_state == 'progress_unknown':
        st.info('Snapshot validated; feed progress has not been monitored.')
    elif result.display_state != 'validated_snapshot':
        st.info('Live analysis unavailable: unrecognized feed state.')
        return
    st.caption(f'Snapshot acquisition age: {snapshot.age_seconds:.0f}s. This is not the age of the last play.')
    if snapshot.unchanged_seconds is not None:
        st.caption(f'Observed unchanged for {snapshot.unchanged_seconds:.0f}s; not proof of a feed outage.')
    context = result.pregame_context
    st.caption(f"Pregame regular-season records · {away_label}: {context['awayPreGameWins']}–{context['awayPreGameLosses']} · "
               f"{home_label}: {context['homePreGameWins']}–{context['homePreGameLosses']}")
    frame = result.predictions
    last = frame.iloc[-1]
    columns = st.columns(2)
    columns[0].metric(away_label, f"{int(last.scoreAway)}")
    columns[1].metric(home_label, f"{int(last.scoreHome)}")
    figure = go.Figure()
    x = frame['elapsedGameTime'] / 60
    for name, probability, color in ((home_label,frame.winProbability,'#49A4FF'),
                                     (away_label,1-frame.winProbability,'#FFBE32')):
        figure.add_trace(go.Scatter(x=x,y=100*probability,name=name,mode='lines',line=dict(color=color,width=3,dash='solid')))
    figure.update_layout(template='plotly_dark',height=370,margin=dict(l=10,r=10,t=45,b=40),
                         yaxis=dict(title='Win probability (%)',range=[0,100]),xaxis_title='Elapsed game minutes',
                         legend=dict(orientation='h',y=1.03,yanchor='bottom',x=0),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(figure,use_container_width=True)
    st.subheader('Traditional box score')
    st.caption('ESPN traditional statistics. Advanced metrics are unavailable; missing values are not zeros.')
    players = snapshot.box['players']
    for side,label in (('away',away_label),('home',home_label)):
        st.markdown(f'**{label}**')
        selected = players.loc[players.teamId.eq(context[side+'TeamId'])].copy()
        selected['Status'] = selected.didNotPlay.map({True:'DNP',False:'Played'})
        mapping={'fullName':'Player','minutesDisplay':'MIN','points':'PTS','reboundsTotal':'REB','assists':'AST',
                 'steals':'STL','blocks':'BLK','turnovers':'TO','plusMinusPoints':'+/-'}
        table=selected.reindex(columns=[*mapping,'Status']).rename(columns=mapping)
        st.dataframe(table,hide_index=True,use_container_width=True)
