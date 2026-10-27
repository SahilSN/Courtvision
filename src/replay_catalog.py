"""Offline completed-game catalog. No Live context, feeds, pickle or inference."""

from datetime import date
from hashlib import sha256
import io
import json
from pathlib import Path
import re

import pandas as pd
from nba_api.stats.static import teams

from live_artifacts import read_json, write_json
from published_replay import load_replay
from season_config import CURRENT_SEASON

ROOT = Path(__file__).resolve().parents[1]
INDEX = 'results/replay_catalog/index_v1.json'
MAX_REPLAY_BYTES = 8_000_000
TEAM_CODES = {team['abbreviation'] for team in teams.get_teams()}


def season_year(season):
    if not re.fullmatch(r'20\d{2}-\d{2}', str(season)):
        raise ValueError('Invalid season')
    year = int(season[:4])
    if season != f'{year}-{(year+1)%100:02d}' or season > CURRENT_SEASON:
        raise ValueError('Invalid season range')
    return year


def valid_identity(game_id, season, day):
    year=season_year(season)
    if not re.fullmatch(r'002'+season[2:4]+r'\d{5}', str(game_id)):
        raise ValueError('Wrong regular-season game ID')
    day = date.fromisoformat(day)
    end=date(year+1,11,1) if season=='2019-20' else date(year+1,7,1)
    if not date(year,7,1) <= day < end or day > date.today():
        raise ValueError('Invalid completed-game date')


def artifact_path(root, entry):
    valid_identity(entry['gameId'],entry['season'],entry['date'])
    folders={'pilot':'results/replay_pilot','catalog':'results/replay_catalog/games'}
    if entry['collection']=='pilot':
        from replay_collection import GAME_IDS
        if entry['gameId'] not in GAME_IDS or entry['season']!='2025-26':
            raise ValueError('Only the four reviewed legacy pilot exports use this collection')
    folder=Path(root)/folders[entry['collection']]
    path=folder/f'{entry["gameId"]}.json'
    if (path.is_symlink() or not folder.resolve().is_relative_to(Path(root).resolve())
            or path.resolve().parent != folder.resolve()):
        raise ValueError('Replay paths must remain inside the catalog')
    return path


def read_index(root=ROOT):
    source=read_json(Path(root)/INDEX)
    if source.get('schemaVersion')!=1 or not isinstance(source.get('games'),list) or len(source['games'])>20000:
        raise ValueError('Invalid replay index')
    entries={}
    for item in source['games']:
        artifact_path(root,item)
        if (item['gameId'] in entries or item['home'] not in TEAM_CODES or item['away'] not in TEAM_CODES
                or item['home']==item['away'] or not re.fullmatch(r'[a-f0-9]{64}',item['sha256'])):
            raise ValueError('Invalid replay index identity')
        entries[item['gameId']]=item
    return entries


def load_catalog_replay(entry, root=ROOT):
    path=artifact_path(root,entry)
    with path.open('rb') as stream:
        raw=stream.read(MAX_REPLAY_BYTES+1)
    if len(raw)>MAX_REPLAY_BYTES or sha256(raw).hexdigest()!=entry['sha256']:
        raise ValueError('Replay artifact changed or exceeds size limit')
    # Decode the exact bytes whose digest was checked; avoid a second file read.
    data,timeline=load_replay(io.StringIO(raw.decode('utf-8')))
    if (data['gameId']!=entry['gameId'] or data['season']!=entry['season'] or data['date']!=entry['date']
            or data['home']['tricode']!=entry['home'] or data['away']['tricode']!=entry['away']):
        raise ValueError('Replay and index disagree')
    if entry['collection']=='catalog' and (data.get('completed') is not True or data.get('seasonType')!='Regular Season'):
        raise ValueError('Only explicitly completed regular-season exports are admitted')
    for field in ('elapsedGameTime','period','scoreHome','scoreAway','winProbability'):
        values=pd.to_numeric(timeline[field],errors='raise')
        if not values.map(lambda value: float('-inf')<float(value)<float('inf')).all():
            raise ValueError('Nonfinite replay')
    if (timeline.elapsedGameTime.min()<0 or timeline.period.min()<1 or timeline.period.max()<4
            or data['home']['score']==data['away']['score']):
        raise ValueError('Invalid full-game replay')
    if any(not data[field] for field in ('turningPoints','playerImpact','boxScore')):
        raise ValueError('Missing replay panels')
    if set(row['teamTricode'] for row in data['boxScore'])!={entry['home'],entry['away']}:
        raise ValueError('Wrong replay box teams')
    if any(type(data[side]['score']) is not int or data[side]['score']<0 for side in ('home','away')):
        raise ValueError('Invalid final scores')
    return data,timeline


def catalog_seasons(root=ROOT):
    seasons={CURRENT_SEASON}
    for path in (Path(root)/'results/season_intelligence').glob('*_team_rating_games_v1.csv'):
        season=path.name[:7]
        if re.fullmatch(r'20\d{2}-\d{2}',season) and season<=CURRENT_SEASON:
            seasons.add(season)
    try:
        seasons.update(item['season'] for item in read_index(root).values())
    except (OSError,ValueError,KeyError,TypeError):
        pass
    return sorted(seasons,reverse=True)


def season_catalog(season, root=ROOT):
    """Merge published completed-game pairs with prepared artifact metadata."""
    path=Path(root)/'results/season_intelligence'/f'{season}_team_rating_games_v1.csv'
    # Validate before constructing a path from a UI selection.
    season_year(season)
    games={}
    if path.exists():
        if path.is_symlink() or path.stat().st_size>8_000_000:
            raise ValueError('Invalid completed-game metadata file')
        frame=pd.read_csv(path,dtype={'gameId':str},usecols=['season','gameDate','gameId','team','opponent','isHome'],nrows=10001)
        if len(frame)>10000:
            raise ValueError('Completed-game metadata exceeds limit')
        for gid,rows in frame.groupby('gameId',sort=False):
            if len(rows)!=2:
                continue
            try:
                home=rows.loc[rows.isHome.eq(1)].iloc[0]
                away=rows.loc[rows.isHome.eq(0)].iloc[0]
                valid_identity(gid,season,str(home.gameDate))
                if (not rows.season.eq(season).all() or home.gameDate!=away.gameDate or
                        home.team!=away.opponent or away.team!=home.opponent or home.team==away.team or
                        home.team not in TEAM_CODES or away.team not in TEAM_CODES):
                    continue
                games[gid]=dict(gameId=gid,season=season,date=str(home.gameDate),home=home.team,away=away.team,
                                availability='Not prepared')
            except (ValueError,TypeError,IndexError):
                continue
    index_error=False
    try:
        entries=read_index(root)
    except (OSError,ValueError,KeyError,TypeError):
        entries={};index_error=True
    for gid,entry in entries.items():
        if entry['season']!=season:
            continue
        if gid in games and any(games[gid][field]!=entry[field] for field in ('date','home','away')):
            continue  # Conflicting published identity never becomes playable.
        games[gid]={**entry,'availability':'Prepared'}
    return sorted(games.values(),key=lambda game:(game['date'],game['gameId']),reverse=True),index_error


def build_index(root=ROOT):
    """Operator build only. Existing legacy pilot artifacts stay unchanged."""
    from replay_collection import GAME_IDS
    entries=[]
    paths=[('pilot',Path(root)/'results/replay_pilot'/f'{gid}.json') for gid in GAME_IDS]
    paths += [('catalog',path) for path in sorted((Path(root)/'results/replay_catalog/games').glob('*.json'))]
    for collection,path in paths:
        with path.open('rb') as stream:
            raw=stream.read(MAX_REPLAY_BYTES+1)
        if len(raw)>MAX_REPLAY_BYTES:
            raise ValueError('Replay too large')
        data=json.loads(raw)
        entry=dict(gameId=data['gameId'],season=data['season'],date=data['date'],home=data['home']['tricode'],
                   away=data['away']['tricode'],collection=collection,sha256=sha256(raw).hexdigest())
        if entry['home'] not in TEAM_CODES or entry['away'] not in TEAM_CODES or entry['home']==entry['away']:
            raise ValueError('Invalid replay teams')
        if path.name!=f'{entry["gameId"]}.json' or any(e['gameId']==entry['gameId'] for e in entries):
            raise ValueError('Duplicate or wrong artifact filename')
        load_catalog_replay(entry,root)
        entries.append(entry)
    result={'schemaVersion':1,'scope':'prepared-completed-regular-season-replays','games':entries}
    # Validate all entries before replacing the index, preserving the old one on failure.
    write_json(Path(root)/INDEX,result)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Build the offline replay index from explicit completed exports.')
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    print(f'Indexed {len(build_index(args.root)["games"])} prepared replays')
