from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from cloud_espn_adapter import ProviderContextUnavailable
from daily_live_context import build_day_context, read_day_context, refresh_day_context


class DayContextTest(unittest.TestCase):
    def setUp(self):
        self.game = dict(game_id='0022600002', game_date='2026-10-23', home_team_id=1610612760, away_team_id=1610612745)
        self.canonical = dict(gameId='0022600002', gameDate='2026-10-23', season='2026-27', homeTeamId=1610612760, awayTeamId=1610612745)
        self.coverage = dict(schemaVersion=1, season='2026-27', seasonType='Regular Season', scope='prior-results-cross-check',
            completeThrough='2026-10-22', checkedDays=['2026-10-21', '2026-10-22'], checkedAt='2026-10-23T08:00:00Z', games=[
                dict(gameId='0022600001', gameDate='2026-10-21', season='2026-27', homeTeamId=1610612760, awayTeamId=1610612745,
                     homeScore=100, awayScore=90, espnEventId='previous')])
        self.espn = dict(leagues=[dict(id='46', season=dict(year=2027))], events=[dict(id='today',season=dict(year=2027,type=2),competitions=[dict(
            date='2026-10-23T23:00Z', competitors=[dict(homeAway='home',team=dict(displayName='Oklahoma City Thunder')),
                                                dict(homeAway='away',team=dict(displayName='Houston Rockets'))])])])

    def build(self):
        return build_day_context([self.game], self.espn, self.coverage, '2026-27', '2026-10-23')

    def test_identity_and_prior_only_records(self):
        game = self.build()['games'][0]
        self.assertEqual(game['gameId'], '0022600002')
        self.assertEqual(game['espnEventId'], 'today')
        self.assertEqual(game['pregameContext']['homePreGameWins'], 1)
        self.assertAlmostEqual(game['pregameContext']['homePreGameWinPct'], 2/3)

    def test_stale_missing_and_noncontiguous_coverage_refused(self):
        for field, value in [('completeThrough','2026-10-21'),('checkedDays',[]),('checkedDays',['2026-10-20','2026-10-22']),('seasonType','Pre Season')]:
            original = deepcopy(self.coverage)
            self.coverage[field] = value
            with self.assertRaises(ProviderContextUnavailable): self.build()
            self.coverage = original

    def test_missing_extra_duplicate_or_swapped_games_refused(self):
        for defect in ('missing','duplicate','swapped'):
            original = deepcopy(self.espn)
            if defect == 'missing': self.espn['events'] = []
            if defect == 'duplicate': self.espn['events'] *= 2
            if defect == 'swapped':
                competitors = self.espn['events'][0]['competitions'][0]['competitors']
                competitors[0]['homeAway'], competitors[1]['homeAway'] = 'away','home'
            with self.assertRaises((ValueError, KeyError)): self.build()
            self.espn = original

    def test_prior_game_on_target_day_refused(self):
        self.coverage['games'][0]['gameDate'] = '2026-10-23'
        with self.assertRaises(ProviderContextUnavailable): self.build()

    def test_opening_night_empty_verified_history(self):
        self.coverage['games'] = []
        self.assertEqual(self.build()['games'][0]['pregameContext']['homePreGameWinPct'], 0.5)

    def test_reader_rejects_wrong_day_game_team_and_broken_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'context.json'
            path.write_text(json.dumps(self.build()))
            self.assertEqual(read_day_context(path,self.canonical)['espnEventId'],'today')
            for field,value in [('gameDate','2026-10-24'),('gameId','0022600003'),('homeTeamId',1610612747)]:
                with self.assertRaises(ProviderContextUnavailable): read_day_context(path,{**self.canonical,field:value})
            path.write_text('{')
            with self.assertRaises(ProviderContextUnavailable): read_day_context(path,self.canonical)

    def test_failed_refresh_keeps_prior_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root/'results/live_context'
            target.mkdir(parents=True)
            (target/'2026-27_coverage_v1.json').write_text(json.dumps(self.coverage))
            kwargs = dict(game_date='2026-10-23',nba_loader=Mock(return_value=[self.game]),espn_loader=Mock(return_value=self.espn))
            refresh_day_context(root,**kwargs)
            path = target/'2026-27_day_context_v1.json'
            before = path.read_bytes()
            kwargs['nba_loader'] = Mock(side_effect=TimeoutError())
            with self.assertRaises(TimeoutError): refresh_day_context(root,**kwargs)
            self.assertEqual(path.read_bytes(),before)
