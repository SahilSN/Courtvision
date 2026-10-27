"""Explicit ESPN scoring events, accepted only with full box/header agreement."""
import re


def reconciled_scores(plays,rows,header,groups,team_map,athlete_map):
    """Return per-event scores or None. Never infer points from score deltas."""
    totals={'home':0,'away':0};scorers={};scores=[]
    try:
        if not plays or len(plays)!=len(rows):return None
        for play,row in zip(plays,rows):
            if type(play.get('scoringPlay')) is not bool:return None
            if play['scoringPlay']:
                points=play.get('scoreValue');team=str(play['team']['id'])
                if type(points) is not int or points not in (1,2,3) or team not in team_map:return None
                if row['actionType'] not in ('Made Shot','Free Throw') or re.search(r'\bmiss(?:es|ed)?\b',row['description'],re.I):return None
                person=row['personId']
                if not person:return None
                side=team_map[team]['side'];totals[side]+=points
                key=(team,person);scorers[key]=scorers.get(key,0)+points
            scores.append((totals['home'],totals['away']))
        expected={c['homeAway']:int(c['score']) for c in header['competitions'][0]['competitors']}
        if totals!=expected or set(expected)!={'home','away'}:return None
        seen_teams=set();seen_people=set();box_scorers={}
        for group in groups:
            team=str(group['team']['id'])
            if team not in team_map or team in seen_teams:return None
            seen_teams.add(team);stats,=group['statistics'];labels=stats['labels']
            if labels.count('PTS')!=1 or len(stats['totals'])!=len(labels):return None
            index=labels.index('PTS');team_points=0
            for athlete in stats['athletes']:
                if type(athlete['didNotPlay']) is not bool:return None
                if athlete['didNotPlay']:continue
                if len(athlete['stats'])!=len(labels):return None
                value=athlete['stats'][index]
                if not isinstance(value,str) or not value.isdigit():return None
                person=athlete_map[str(athlete['athlete']['id'])]['nba_person_id']
                if not person or person in seen_people:return None
                seen_people.add(person);points=int(value);team_points+=points
                if points:box_scorers[(team,person)]=points
            reported=stats['totals'][index]
            if not isinstance(reported,str) or not reported.isdigit():return None
            if int(reported)!=team_points or team_points!=totals[team_map[team]['side']]:return None
        if seen_teams!=set(team_map) or box_scorers!=scorers:return None
        return scores
    except (KeyError,TypeError,ValueError,IndexError):
        return None
