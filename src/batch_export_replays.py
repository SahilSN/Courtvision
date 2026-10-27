"""Bounded, resumable export of existing trusted local replay caches. No acquisition."""

import argparse
from datetime import datetime, timezone
import fcntl
from pathlib import Path
import re
import time

from live_artifacts import read_json, write_json
from prepare_replay_catalog import prepare
from replay_catalog import ROOT, load_catalog_replay, read_index, season_year


def inventory(cache_root):
    rows=[]
    for path in (Path(cache_root)/'data/cache/analysis/v1_v7').glob('*_top3.pkl'):
        match=re.fullmatch(r'(20\d{2}-\d{2})_(002\d{7})_top3.pkl',path.name)
        if match:
            try:season_year(match[1])
            except ValueError:continue
            if match[2][3:5]!=match[1][2:4]:
                continue
            rows.append((match[1],match[2]))
    return sorted(rows,reverse=True)


def inputs(cache_root,season,gid):
    root=Path(cache_root).resolve()
    paths=[root/f'data/cache/analysis/v1_v7/{season}_{gid}_top3.pkl',
           root/f'data/cache/box_score/v1/{gid}.pkl',root/f'results/player_wpa_v3_{gid}_summary.csv']
    signature=[];missing=[]
    for name,path in zip(('analysis','box','impact'),paths):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('Cache symlinks outside the trusted inventory are not allowed')
        try:
            stat=path.stat();signature.append([stat.st_size,stat.st_mtime_ns])
        except FileNotFoundError:
            signature.append(None);missing.append(name)
    return signature,missing


def run_batch(root,cache_root,limit=20,max_seconds=60,retry_blocked=False,clock=time.monotonic):
    if not 1<=limit<=100 or not 1<=max_seconds<=300:
        raise ValueError('Use 1–100 attempts and a 1–300 second between-game budget')
    root=Path(root);cache_root=Path(cache_root)
    runtime=root/'results/.runtime/replay-export'
    runtime.mkdir(parents=True,exist_ok=True)
    with (runtime/'batch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        path=runtime/'status.json'
        try: previous=read_json(path)
        except (OSError,ValueError,TypeError): previous={}
        saved=previous.get('games',{})
        if not isinstance(saved,dict):saved={}
        available=inventory(cache_root)
        if len(available)>10000:raise ValueError('Inventory exceeds bounded ledger capacity')
        indexed=read_index(root)  # Invalid published index requires explicit repair, never reset it.
        started=clock()
        report=dict(schemaVersion=1,startedAt=datetime.now(timezone.utc).isoformat(),
                    scope='existing-trusted-final-analysis-caches-only',inventory=len(available),attempted=0,
                    exported=0,alreadyPrepared=0,blocked=0,pending=0,games={})

        def checkpoint():
            report['checkedAt']=datetime.now(timezone.utc).isoformat()
            write_json(path,report)

        for season,gid in available:
            key=f'{season}:{gid}'
            old=saved.get(key,{})
            if not isinstance(old,dict):old={}
            if clock()-started>=max_seconds:
                report['games'][key]=old or {'status':'pending'}
                report['pending']+=1;continue
            if gid in indexed:
                try:
                    load_catalog_replay(indexed[gid],root)
                    report['games'][key]={'status':'prepared'};report['alreadyPrepared']+=1
                except (OSError,ValueError,KeyError,TypeError,IndexError) as error:
                    report['games'][key]={'status':'published_invalid','errorType':type(error).__name__}
                    report['blocked']+=1
                checkpoint();continue
            try:
                signature,missing=inputs(cache_root,season,gid)
            except (OSError,ValueError) as error:
                report['games'][key]={'status':'unsafe_inputs','errorType':type(error).__name__}
                report['blocked']+=1;checkpoint();continue
            if missing:
                report['games'][key]={'status':'missing_inputs','missing':missing,'signature':signature}
                report['blocked']+=1;checkpoint();continue
            if old.get('status')=='failed' and old.get('signature')==signature and not retry_blocked:
                report['games'][key]=old;report['blocked']+=1;checkpoint();continue
            if report['attempted']>=limit:
                report['games'][key]={'status':'pending','signature':signature}
                report['pending']+=1;continue
            report['attempted']+=1
            report['games'][key]={'status':'exporting','signature':signature};checkpoint()
            try:
                result=prepare(root,cache_root,season,[gid])
                indexed={entry['gameId']:entry for entry in result['games']}
                report['games'][key]={'status':'prepared','signature':signature}
                report['exported']+=1
            except Exception as error:
                # One bad cached game cannot block the remaining independent exports.
                report['games'][key]={'status':'failed','signature':signature,'errorType':type(error).__name__}
                report['blocked']+=1
            checkpoint()
        report['status']='pending' if report['pending'] else 'blocked' if report['blocked'] else 'complete'
        report['finishedAt']=datetime.now(timezone.utc).isoformat()
        checkpoint()
        return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--cache-root',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=20)
    parser.add_argument('--max-seconds',type=int,default=60)
    parser.add_argument('--retry-blocked',action='store_true')
    args=parser.parse_args()
    result=run_batch(args.root,args.cache_root,args.limit,args.max_seconds,args.retry_blocked)
    print({key:value for key,value in result.items() if key!='games'})
