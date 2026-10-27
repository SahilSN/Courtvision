from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from nba_api.stats.static import teams

from daily_live_policy import active_games, allowed_daily_games, validate_daily_manifest
from live_artifacts import read_json, write_json
from live_operations import operations_status
from official_live_rosters import normalize_roster, roster_candidates, roster_url, validate_roster_artifact
from prepare_daily_live import prepare_daily_live
from reviewed_live_players import merge_candidates
from run_nightly_intelligence import published_paths, publish_current_data, git


class DailyPreparationTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root/'results/live_context'
        original = Path(__file__).resolve().parents[1]/'results/live_context/2026-27_day_context_v1.json'
        self.context = read_json(original)
        self.context['games'] = self.context['games'][:5]
        self.now = datetime.fromisoformat(self.context['gameDate']+'T12:00:00+00:00')
        self.day = self.context['gameDate']
        self.registry = {t['id']:t['full_name'] for t in teams.get_teams()}
        self.context_path = self.directory/'2026-27_day_context_v1.json'
        write_json(self.context_path,self.context)
        self.env = {'COURTVISION_ENABLE_LIVE_BETA':'1'}
        self.policy = dict(schemaVersion=1,enabled=True,season='2026-27',seasonType='Regular Season',
                           issuedAt=(self.now-timedelta(hours=1)).isoformat(),
                           expiresAt=(self.now+timedelta(days=3)).isoformat(),maxGames=4)
        write_json(self.root/'cloud/live_daily_policy.json',self.policy)
        self.fetcher = Mock(side_effect=self.fetch)

    def roster(self,team_id):
        return dict(parameters=dict(TeamID=team_id,Season='2026-27'),resultSets=[dict(
            name='CommonTeamRoster',headers=['TeamID','SEASON','PLAYER','PLAYER_ID'],
            rowSet=[[team_id,2026,f'Official Player {team_id}',10000+team_id%1000]])])

    def fetch(self,url):
        if url.startswith('https://stats.nba.com/stats/commonteamroster?'):
            team_id = int(parse_qs(urlparse(url).query)['TeamID'][0])
            return self.roster(team_id),{}
        event_id = parse_qs(urlparse(url).query)['event'][0]
        game, = [g for g in self.context['games'] if g['espnEventId']==event_id]
        competitors, players = [], []
        for side in ('home','away'):
            team_id = game[side+'TeamId']
            provider_id = str(team_id)
            competitors.append(dict(homeAway=side,team=dict(id=provider_id,displayName=self.registry[team_id])))
            players.append(dict(team=dict(id=provider_id),statistics=[dict(athletes=[dict(
                athlete=dict(displayName=f'Official Player {team_id}'))])]))
        return dict(header=dict(id=event_id,season=dict(year=2027,type=2),
                                competitions=[dict(date=self.now.isoformat(),competitors=competitors)]),
                    boxscore=dict(players=players)),{}

    def prepare(self,**kwargs):
        return prepare_daily_live(self.root,fetcher=self.fetcher,now=self.now,**kwargs)

    def test_prepare_is_bounded_and_automatic_policy_has_no_network(self):
        report = self.prepare()
        self.assertEqual(report['status'],'prepared')
        self.assertEqual(report['games'],4)
        self.assertEqual(report['deferredGames'],1)
        self.assertLessEqual(self.fetcher.call_count,12)
        with patch('requests.sessions.Session.request',side_effect=AssertionError('Viewer HTTP')):
            ids = allowed_daily_games(self.root,self.env,self.now)
            self.assertEqual(len(ids),4)
            self.assertEqual(active_games(self.root,self.env,self.now),ids)
            health = operations_status(self.root,self.env,self.now)
        self.assertEqual(health['preparation'],'prepared')
        self.assertEqual(health['deferredGames'],1)
        self.assertFalse((self.root/'cloud/live_rollout.json').exists())

    def test_expiry_kill_optin_malformed_and_oversized_slates_fail_closed(self):
        self.prepare()
        self.assertFalse(allowed_daily_games(self.root,{},self.now))
        self.assertFalse(allowed_daily_games(self.root,{**self.env,'COURTVISION_DISABLE_LIVE_BETA':'1'},self.now))
        self.assertFalse(allowed_daily_games(self.root,self.env,self.now+timedelta(days=1)))
        for key,value in [('enabled',False),('maxGames',5),('maxGames',True),('seasonType','Pre Season'),
                          ('expiresAt',(self.now+timedelta(days=8)).isoformat())]:
            policy = {**self.policy,key:value}
            write_json(self.root/'cloud/live_daily_policy.json',policy)
            self.assertFalse(allowed_daily_games(self.root,self.env,self.now))
        write_json(self.root/'cloud/live_daily_policy.json',self.policy)
        path = self.directory/'2026-27_daily_live_v1.json'
        manifest = read_json(path)
        write_json(path,{**manifest,'gameIds':[g['gameId'] for g in self.context['games']]})
        self.assertFalse(allowed_daily_games(self.root,self.env,self.now))
        path.write_text('{')
        self.assertFalse(allowed_daily_games(self.root,self.env,self.now))

    def test_partial_publication_and_altered_context_cannot_activate(self):
        self.prepare()
        context = deepcopy(self.context)
        context['games'][0]['pregameContext']['homePreGameWins'] += 1
        write_json(self.context_path,context)
        self.assertFalse(allowed_daily_games(self.root,self.env,self.now))
        self.assertEqual(operations_status(self.root,self.env,self.now)['preparation'],'unavailable')
        self.context_path.unlink()
        self.assertFalse(allowed_daily_games(self.root,self.env,self.now))

    def test_bad_context_never_starts_official_or_espn_requests(self):
        context = deepcopy(self.context)
        context['completeThrough'] = context['gameDate']
        write_json(self.context_path,context)
        with self.assertRaises(ValueError): self.prepare()
        self.fetcher.assert_not_called()

    def test_roster_outage_retains_validation_and_publishes_review_queue(self):
        def outage(url):
            if url.startswith('https://stats.nba.com/'):
                raise TimeoutError('private upstream message')
            return self.fetch(url)
        self.fetcher.side_effect = outage
        report = self.prepare()
        self.assertEqual(report['status'],'degraded')
        self.assertGreater(report['pendingIdentities'],0)
        queue = read_json(self.directory/'2026-27_identity_review_v1.json')
        self.assertNotIn('private upstream message',json.dumps(queue))
        self.assertTrue(all(p['reason']=='unresolved' for p in queue['pending']))
        roster = read_json(self.directory/'2026-27_roster_identities_v1.json')
        self.assertTrue(all(t['status']=='unavailable' and not t['players'] for t in roster['teams']))
        # Availability of matchups is NOT a certificate that their feed/players
        # can pass. Existing exact mappings still work; unknown names still block.
        self.assertEqual(len(allowed_daily_games(self.root,self.env,self.now)),4)
        self.assertEqual(operations_status(self.root,self.env,self.now)['preparation'],'degraded')

    def test_budget_exhaustion_is_bounded_and_explicit_not_synthetic_success(self):
        result = self.prepare(budget=0)
        self.fetcher.assert_not_called()
        self.assertEqual(result['status'],'degraded')
        self.assertGreater(result['rosterTeamsUnavailable'],0)
        manifest = read_json(self.directory/'2026-27_daily_live_v1.json')
        self.assertTrue(all(g['status']=='unavailable' for g in manifest['summaryInspections']))

    def test_exact_official_ids_are_dated_team_scoped_and_conflicts_block(self):
        self.prepare()
        path = self.directory/'2026-27_roster_identities_v1.json'
        artifact = read_json(path)
        team = artifact['teams'][0]; person = team['players'][0]
        kwargs = dict(path=path,now=self.now)
        self.assertEqual(roster_candidates(person['fullName'],'2026-27',team['teamId'],self.day,**kwargs),{person['personId']})
        self.assertFalse(roster_candidates(person['fullName'],'2025-26',team['teamId'],self.day,**kwargs))
        self.assertFalse(roster_candidates(person['fullName'],'2026-27',-1,self.day,**kwargs))
        self.assertFalse(roster_candidates(person['fullName'],'2026-27',team['teamId'],'2020-01-01',**kwargs))
        self.assertFalse(roster_candidates(person['fullName'],'2026-27',team['teamId'],self.day,path=path,now=self.now-timedelta(seconds=1)))
        self.assertEqual(merge_candidates('Graham Ike','2026-27',1610612744,{99}),{1643633,99})
        path.write_text('{')
        self.assertFalse(roster_candidates(person['fullName'],'2026-27',team['teamId'],self.day,**kwargs))

    def test_official_roster_wrong_parameters_rows_and_ambiguity_rejected(self):
        team_id = self.context['games'][0]['homeTeamId']
        good = self.roster(team_id)
        for defect in ('params','team','season','bool_id','duplicate','empty','missing'):
            payload = deepcopy(good)
            dataset = payload['resultSets'][0]
            if defect=='params': payload['parameters']['Season']='2025-26'
            if defect=='team': dataset['rowSet'][0][0] = -1
            if defect=='season': dataset['rowSet'][0][1] = 2025
            if defect=='bool_id': dataset['rowSet'][0][3] = True
            if defect=='duplicate': dataset['rowSet'] *= 2
            if defect=='empty': dataset['rowSet'] = []
            if defect=='missing': dataset['headers'].remove('PLAYER_ID')
            with self.subTest(defect=defect),self.assertRaises((ValueError,KeyError)):
                normalize_roster(payload,team_id,'2026-27')

    def test_manual_window_precedence_and_intentional_pause(self):
        self.prepare()
        selected = self.context['games'][-1]['gameId']
        config = dict(schemaVersion=1,enabled=True,season='2026-27',seasonType='Regular Season',
                      gameDate=self.day,issuedAt=(self.now-timedelta(minutes=5)).isoformat(),
                      expiresAt=(self.now+timedelta(minutes=5)).isoformat(),gameIds=[selected])
        path = self.root/'cloud/live_rollout.json'
        write_json(path,config)
        self.assertEqual(active_games(self.root,self.env,self.now),(selected,))
        config['expiresAt'] = self.now.isoformat()
        write_json(path,config)
        self.assertEqual(len(active_games(self.root,self.env,self.now)),4)
        config['enabled'] = False
        write_json(path,config)
        self.assertFalse(active_games(self.root,self.env,self.now))
        path.write_text('{')
        self.assertFalse(active_games(self.root,self.env,self.now))

    def test_nightly_publication_allowlist_includes_data_not_rollout_or_code(self):
        paths = published_paths()
        for suffix in ('_daily_live_v1.json','_roster_identities_v1.json','_identity_review_v1.json'):
            self.assertTrue(any(p.endswith(suffix) for p in paths))
        self.assertTrue(all(p.startswith('results/') for p in paths))

    def test_isolated_publisher_includes_daily_data_and_preserves_staged_user_code(self):
        with tempfile.TemporaryDirectory() as directory:
            remote = Path(directory)/'remote.git'
            git(self.root,'init','--bare','--initial-branch=main',str(remote))
            git(self.root,'init','--initial-branch=main')
            git(self.root,'config','user.name','Test')
            git(self.root,'config','user.email','test@example.com')
            (self.root/'.gitignore').write_text('results/.runtime/\n')
            (self.root/'README.md').write_text('original code\n')
            git(self.root,'add','.')
            git(self.root,'commit','-m','initial')
            git(self.root,'remote','add','origin',str(remote))
            git(self.root,'push','-u','origin','main')
            (self.root/'README.md').write_text('user-staged code\n')
            git(self.root,'add','README.md')
            index = git(self.root,'diff','--cached','--binary').stdout
            self.prepare()
            publish_current_data(self.root)
            self.assertEqual(git(self.root,'diff','--cached','--binary').stdout,index)
            payload = git(self.root,'--git-dir',str(remote),'show',
                'main:results/live_context/2026-27_daily_live_v1.json').stdout
            self.assertEqual(len(json.loads(payload)['gameIds']),4)
            self.assertEqual(git(self.root,'--git-dir',str(remote),'show','main:README.md').stdout,'original code\n')

    def test_optional_live_preparation_failure_does_not_erase_valid_coverage(self):
        from daily_live_context import refresh_nightly_context
        with patch('daily_live_context.refresh_coverage',return_value={'status':'success'}), \
             patch('daily_live_context.refresh_day_context',return_value={'status':'success'}), \
             patch('prepare_daily_live.prepare_daily_live',side_effect=TimeoutError('not public')):
            report = refresh_nightly_context(self.root)
        self.assertEqual(report['status'],'success')
        self.assertEqual(report['dayContext']['status'],'success')
        self.assertEqual(report['livePreparation'],{'status':'unavailable','errorType':'TimeoutError'})

    def test_wrong_summary_context_cannot_populate_identity_review(self):
        original = self.fetch
        def wrong(url):
            payload,meta = original(url)
            if 'summary?event=' in url:
                payload['header']['season']['type'] = 1
            return payload,meta
        self.fetcher.side_effect = wrong
        self.prepare()
        queue = read_json(self.directory/'2026-27_identity_review_v1.json')
        self.assertFalse(queue['pending'])
        self.assertTrue(all(g['status']=='unavailable' for g in queue['games']))

    def test_empty_verified_schedule_stays_empty_without_network(self):
        self.context['games'] = []
        write_json(self.context_path,self.context)
        result = self.prepare()
        self.fetcher.assert_not_called()
        self.assertEqual(result['games'],0)
        self.assertFalse(allowed_daily_games(self.root,self.env,self.now))

    def test_preparation_only_fetches_fixed_endpoint_families(self):
        from prepare_daily_live import preparation_fetch
        with patch('prepare_daily_live.fetch_json',return_value=({},{})) as fetched:
            preparation_fetch(roster_url(1610612744,'2026-27'))
            self.assertEqual(fetched.call_args.kwargs['headers']['Referer'],'https://www.nba.com/')
            with self.assertRaises(ValueError): preparation_fetch('https://example.com/roster')



if __name__=='__main__':
    unittest.main()
