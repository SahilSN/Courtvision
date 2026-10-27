from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import tempfile
import unittest

from live_rollout import allowed_games
from season_config import CURRENT_SEASON


class RolloutTest(unittest.TestCase):
    def test_overnight_still_requires_unexpired_explicit_operator_gates(self):
        issued = datetime.fromisoformat('2026-10-27T03:50:00+00:00')
        config = dict(schemaVersion=1, enabled=True, season=CURRENT_SEASON,
                      seasonType='Regular Season', gameDate='2026-10-26',
                      issuedAt=issued.isoformat(), expiresAt='2026-10-27T11:00:00+00:00',
                      gameIds=['0022600127'])
        env = {'COURTVISION_ENABLE_LIVE_BETA':'1'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'rollout.json'
            path.write_text(json.dumps(config))
            midnight = datetime.fromisoformat('2026-10-27T04:00:00+00:00')
            self.assertEqual(allowed_games(path, env, midnight), ('0022600127',))
            self.assertEqual(allowed_games(path, {}, midnight), ())
            self.assertEqual(allowed_games(path, {**env, 'COURTVISION_DISABLE_LIVE_BETA':'1'}, midnight), ())
            self.assertEqual(allowed_games(path, env, datetime.fromisoformat('2026-10-27T10:00:00+00:00')), ())
            config['expiresAt'] = midnight.isoformat()
            path.write_text(json.dumps(config))
            self.assertEqual(allowed_games(path, env, midnight), ())

    def test_gates_and_invalid_configs_fail_closed(self):
        now=datetime(2026,10,26,20,tzinfo=timezone.utc)
        env={'COURTVISION_ENABLE_LIVE_BETA':'1'}
        config=dict(schemaVersion=1,enabled=True,season=CURRENT_SEASON,seasonType='Regular Season',
            issuedAt=now.isoformat(),expiresAt=(now+timedelta(hours=2)).isoformat(),gameDate='2026-10-26',gameIds=['0022600125'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rollout.json'
            self.assertEqual(allowed_games(path,env,now),())
            path.write_text(json.dumps(config))
            self.assertEqual(allowed_games(path,env,now),('0022600125',))
            four={**config,'gameIds':['0022600120','0022600121','0022600122','0022600123']}
            path.write_text(json.dumps(four))
            self.assertEqual(allowed_games(path,env,now),tuple(four['gameIds']))
            path.write_text(json.dumps(config))
            self.assertEqual(allowed_games(path,{},now),())
            self.assertEqual(allowed_games(path,{**env,'COURTVISION_DISABLE_LIVE_BETA':'1'},now),())
            self.assertEqual(allowed_games(path,env,now+timedelta(hours=3)),())
            for key,value in [('enabled',False),('gameIds',['0022600125']*2),('gameIds',['0022600120','0022600121','0022600122','0022600123','0022600124']),
                              ('gameIds',[None]),('gameDate','2026-10-25'),('seasonType','Pre Season'),
                              ('expiresAt',(now+timedelta(days=2)).isoformat()),('issuedAt','2026-10-26T20:00:00')]:
                broken=deepcopy(config);broken[key]=value;path.write_text(json.dumps(broken))
                with self.subTest(key=key,value=value): self.assertEqual(allowed_games(path,env,now),())
            path.write_text('{')
            self.assertEqual(allowed_games(path,env,now),())
