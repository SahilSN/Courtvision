"""Operator-only export from trusted local final analysis caches. No network/model jobs."""

import argparse
from pathlib import Path
import tempfile

from export_replay_pilot import export_game
from replay_catalog import ROOT, build_index


def prepare(root, cache_root, season, game_ids):
    if not 1<=len(game_ids)<=20 or len(set(game_ids))!=len(game_ids):
        raise ValueError('Select 1–20 distinct completed games')
    root=Path(root)
    target=root/'results/replay_catalog/games'
    target.mkdir(parents=True,exist_ok=True)
    # Validate every export before exposing any. Failed batches retain the index.
    with tempfile.TemporaryDirectory(prefix='replay-export-') as directory:
        staged=[]
        for gid in game_ids:
            path=export_game(gid,season,cache_root,Path(directory)/f'{gid}.json')
            destination=target/path.name
            if destination.exists() and destination.read_bytes()!=path.read_bytes():
                raise ValueError('Existing replay differs; refusing to replace published history')
            staged.append((path,destination))
        for path,destination in staged:
            if not destination.exists():
                # Atomically publish a complete file, even across temporary volumes.
                temporary=destination.with_suffix('.json.tmp')
                temporary.write_bytes(path.read_bytes())
                temporary.replace(destination)
        return build_index(root)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--cache-root',type=Path,required=True,help='Trusted local Courtvision cache checkout; never an uploaded pickle')
    parser.add_argument('--season',required=True)
    parser.add_argument('--game-id',action='append',required=True)
    args=parser.parse_args()
    result=prepare(args.root,args.cache_root,args.season,args.game_id)
    print(f'Historical Replay index now contains {len(result["games"])} prepared games')
