from copy import deepcopy
import unittest
from unittest.mock import Mock
from probe_nba_cdn import fetch_cdn_pair, probe_cdn
from urllib.error import HTTPError


class CDNAccessTest(unittest.TestCase):
    def setUp(self):
        self.game = dict(gameId='0022600131', gameDate='2026-10-27', season='2026-27',
                         homeTeamId=1610612747, awayTeamId=1610612757)
        self.box = {'game': {'gameId':self.game['gameId'], 'homeTeam':{'teamId':1610612747},
                            'awayTeam':{'teamId':1610612757}}}
        self.pbp = {'game': {'gameId':self.game['gameId'], 'actions':[]}}

    def test_two_fixed_official_requests_and_no_id_conversion(self):
        fetch = Mock(side_effect=[(self.box,{}),(self.pbp,{})])
        self.assertEqual(fetch_cdn_pair(self.game,fetch)['boxscore'],self.box)
        self.assertEqual(fetch.call_count,2)
        self.assertEqual(fetch.call_args_list[1].args[0],
            'https://cdn.nba.com/static/json/liveData/playbyplay/playbyplay_0022600131.json')

    def test_forbidden_is_not_retried_or_bypassed(self):
        fetch=Mock(side_effect=HTTPError('https://cdn.nba.com',403,'Forbidden',{},None))
        with self.assertRaises(HTTPError):fetch_cdn_pair(self.game,fetch)
        self.assertEqual(fetch.call_count,1)

    def test_wrong_game_or_team_blocks_before_second_request(self):
        for field in ('gameId','homeTeam'):
            bad=deepcopy(self.box)
            if field=='gameId':bad['game']['gameId']='0022600130'
            else:bad['game']['homeTeam']['teamId']=1610612738
            fetch=Mock(return_value=(bad,{}))
            with self.assertRaises(ValueError):fetch_cdn_pair(self.game,fetch)
            self.assertEqual(fetch.call_count,1)

    def test_ineligible_canonical_id_never_fetches(self):
        fetch=Mock()
        with self.assertRaises(ValueError):fetch_cdn_pair({**self.game,'gameId':'401909880'},fetch)
        fetch.assert_not_called()

    def test_host_probe_is_dated_sanitized_and_not_activation(self):
        from test_daily_live_preparation import DailyPreparationTest
        fixture=DailyPreparationTest(methodName='test_prepare_is_bounded_and_automatic_policy_has_no_network')
        fixture.setUp();self.addCleanup(fixture.doCleanups)
        game=fixture.context['games'][0]
        fetch=Mock(side_effect=HTTPError('private-details',403,'raw details',{},None))
        result=probe_cdn(fixture.day,'test',[game['gameId']],root=fixture.root,fetcher=fetch)
        self.assertEqual(result['httpStatus'],403)
        self.assertNotIn('raw details',str(result))
        self.assertFalse((fixture.root/'cloud/live_probe_request.json').exists())
        fetch.reset_mock()
        self.assertEqual(probe_cdn('2026-10-01','test',[game['gameId']],
                         root=fixture.root,fetcher=fetch)['status'],'failed')
        fetch.assert_not_called()


if __name__=='__main__':unittest.main()
