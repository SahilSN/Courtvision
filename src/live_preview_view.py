"""Preview-only presentation contract. No HTTP, discovery, model loads or timers."""

import plotly.graph_objects as go
import streamlit as st
import base64
from html import escape
from pathlib import Path
from datetime import datetime, timezone
from nba_api.stats.static import teams
from replay_collection import clock_label
from live_game_state import presentation_state


def scoreboard_html(result, home_label, away_label):
    """Local logos and escaped text only; no external assets or inferred final state."""
    row=result.predictions.iloc[-1]
    status=presentation_state(result)
    status_color={'Live':'#64D9A6','Delayed':'#FFBE32','Final':'#C1CCDD'}.get(status,'#49A4FF')
    context=result.pregame_context
    registry={team['id']:team for team in teams.get_teams()}
    cards=[]
    for side,label,color in (('away',away_label,'#FFBE32'),('home',home_label,'#49A4FF')):
        team=registry.get(context[side+'TeamId'],{})
        abbreviation=team.get('abbreviation','')
        path=Path(__file__).resolve().parents[1]/'dashboard/assets/logos'/f'{abbreviation.lower()}.svg'
        logo=(f'<img alt="{escape(label,quote=True)} logo" src="data:image/svg+xml;base64,{base64.b64encode(path.read_bytes()).decode()}"/>' if path.exists() else '')
        wins,losses=context[side+'PreGameWins'],context[side+'PreGameLosses']
        probability=float(row.winProbability) if side=='home' else 1-float(row.winProbability)
        score=int(row.scoreHome if side=='home' else row.scoreAway)
        cards.append(f'<div class="cv-team" style="--team:{color}">{logo}<div class="cv-code">{escape(label)}</div>'
                     f'<div class="cv-name">{escape(team.get("full_name",label))}</div><div class="cv-record">Pregame record {wins}–{losses}</div>'
                     f'<div class="cv-score">{score}</div><div class="cv-prob">{probability:.1%}<span>'
                     f'{"model at last event" if status=="Final" else "win probability"}</span></div></div>')
    period=int(row.period)
    phase=f'Q{period}' if period<=4 else f'OT{period-4}'
    phase_text='Game complete' if status=='Final' else f'{phase} · {clock_label(row.clock)}'
    return ('<style>.cv-board{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;padding:22px 16px;'
            'border:1px solid #303746;border-radius:22px;background:linear-gradient(135deg,#182130,#10151e);margin:14px 0 24px;color:#f3f5fa}'
            '.cv-team{text-align:center;min-width:0}.cv-team img{height:58px;width:58px;object-fit:contain}.cv-code{font-size:23px;font-weight:750;letter-spacing:2px}'
            '.cv-name,.cv-record{font-size:12px;color:#aab4c5;margin:4px 0}.cv-score{font-size:58px;font-weight:750;line-height:1.25;font-variant-numeric:tabular-nums}'
            '.cv-prob{font-size:18px;font-weight:700;color:var(--team)}.cv-prob span{display:block;font-size:11px;color:#b0bbce;font-weight:400}'
            '.cv-phase{text-align:center;color:#b7c2d4;font-size:12px;letter-spacing:1px}.cv-badge{display:inline-block;padding:6px 12px;border:1px solid #526078;border-radius:20px;color:#e1eaff;font-size:11px;font-weight:700;letter-spacing:1.5px}'
            '.cv-clock{display:block;font-size:15px;color:#fff;margin:12px 0}'
            '@media(max-width:500px){.cv-board{gap:6px;padding:20px 8px}.cv-score{font-size:43px}.cv-team img{width:48px;height:48px}.cv-name{font-size:10px}.cv-code{font-size:20px}.cv-clock{font-size:17px}}</style>'
            f'<section class="cv-board" aria-label="Game snapshot scoreboard">{cards[0]}<div class="cv-phase">'
            f'<span class="cv-badge" style="color:{status_color};border-color:{status_color}">{status.upper()}</span>'
            f'<span class="cv-clock">{escape(phase_text)}</span></div>{cards[1]}</section>')


def verification_label(snapshot):
    """Acquisition time, explicitly not the source's last-play timestamp."""
    age = max(0, float(snapshot.age_seconds))
    try:
        verified = datetime.fromisoformat(snapshot.verified_at)
        if verified.tzinfo is None:
            raise ValueError('Timezone required')
        stamp = verified.astimezone(timezone.utc).strftime('%H:%M:%S UTC')
        return f'Last verified at {stamp} · {age:.0f}s old at the last refresh. Not the age of the last play.'
    except (AttributeError, TypeError, ValueError):
        return f'Verified snapshot acquired {age:.0f}s before the last refresh. Not the age of the last play.'


def render_live_analysis(result, home_label='Home', away_label='Away'):
    if result is None:
        st.subheader('Awaiting verified game data')
        st.info('Live analysis temporarily unavailable. Waiting for a verified feed and dated pregame context. No estimate is shown.')
        return
    snapshot = result.snapshot
    if snapshot.timeline.attrs.get('scoreSource')=='reconciled_scoring_events':
        st.caption('Score source: explicit scoring events reconciled with every scorer, team totals and header. Reported cumulative scores are retained for audit.')
    if result.display_state == 'stale_snapshot':
        st.warning('Update delayed — showing the last validated snapshot, not the current game state.')
        limit = float(getattr(snapshot, 'max_age_seconds', 60))
        st.caption(f'On refresh, estimates older than {limit:.0f}s are hidden. Refresh to retry; automatic refresh is optional.')
    elif result.display_state == 'possibly_stalled':
        st.warning('The active feed has not changed recently. Play may be stopped or updates may be delayed.')
    elif result.display_state == 'progress_unknown':
        st.caption('Validated snapshot · feed progress has not been monitored')
    elif result.display_state != 'validated_snapshot':
        st.info('Live analysis unavailable: unrecognized feed state.')
        return
    context = result.pregame_context
    st.markdown(scoreboard_html(result,home_label,away_label),unsafe_allow_html=True)
    st.caption(verification_label(snapshot))
    if presentation_state(result)=='Final':
        st.caption('Final score confirmed by both source sections. Probabilities below are the unchanged model history, not the game outcome.')
    frame = result.predictions
    st.subheader('Win probability')
    st.caption('How the game unfolded · frozen V7')
    figure = go.Figure()
    x = frame['elapsedGameTime'] / 60
    for name, probability, color in ((home_label,frame.winProbability,'#49A4FF'),
                                     (away_label,1-frame.winProbability,'#FFBE32')):
        figure.add_trace(go.Scatter(x=x,y=100*probability,name=name,mode='lines',line=dict(color=color,width=3,dash='solid')))
    maximum=float(x.max())
    ticks=[(0,'Start'),(12,'Q2'),(24,'Q3'),(36,'Q4'),(48,'OT')]+[(48+5*i,f'{i+1}OT') for i in range(1,10)]
    ticks=[(value,label) for value,label in ticks if value<maximum]
    for value,_ in ticks[1:]:
        figure.add_vline(x=value,line_width=1,line_color='#303b4c')
    figure.add_hline(y=50,line_width=1,line_color='#556073')
    figure.update_traces(hovertemplate='%{y:.1f}%<extra>%{fullData.name}</extra>')
    figure.update_layout(template='plotly_dark',height=390,margin=dict(l=10,r=10,t=45,b=35),hovermode='x unified',
                         yaxis=dict(title=None,range=[0,100],ticksuffix='%',gridcolor='#283140'),
                         xaxis=dict(title=None,range=[0,max(1,maximum)],tickfont=dict(size=11),tickvals=[v for v,_ in ticks],ticktext=[label for _,label in ticks]),
                         legend=dict(orientation='h',y=1.03,yanchor='bottom',x=0),paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(figure,width='stretch',config={'displayModeBar':False,'scrollZoom':False})
    st.caption(f'{home_label} {float(frame.winProbability.iloc[-1]):.1%} · {away_label} {1-float(frame.winProbability.iloc[-1]):.1%} at the latest validated event.')
    box_tab,details_tab=st.tabs(['Box score','About the data'])
    with details_tab:
        st.caption(f'Snapshot acquisition age: {snapshot.age_seconds:.0f}s. This is not the age of the last play.')
        if snapshot.unchanged_seconds is not None:
            st.caption(f'Observed unchanged for {snapshot.unchanged_seconds:.0f}s; not proof of a feed outage.')
        st.write('ESPN traditional statistics · frozen V7 probabilities. Advanced metrics are unavailable; missing values are not zeros.')
    with box_tab:
        st.caption('Traditional stats · DNPs are explicit · missing MIN is unavailable, not zero · swipe tables for more columns')
    players = snapshot.box['players']
    for side,label in (('away',away_label),('home',home_label)):
        with box_tab:
            st.markdown(f'**{label}**')
        selected = players.loc[players.teamId.eq(context[side+'TeamId'])].copy()
        selected['Status'] = selected.didNotPlay.map({True:'DNP',False:'Played'})
        mapping={'fullName':'Player','minutesDisplay':'MIN','points':'PTS','reboundsTotal':'REB','assists':'AST',
                 'steals':'STL','blocks':'BLK','turnovers':'TO','plusMinusPoints':'+/-'}
        table=selected.reindex(columns=['fullName','Status',*[key for key in mapping if key!='fullName']]).rename(columns=mapping)
        with box_tab:
            st.dataframe(table,hide_index=True,width='stretch',column_config={'PTS':st.column_config.NumberColumn(format='%d'),
                'REB':st.column_config.NumberColumn(format='%d'),'AST':st.column_config.NumberColumn(format='%d')})
