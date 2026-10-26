from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from live_refresh import current_event,fetch_pair,PregameNotReady


class RefreshTest(unittest.TestCase):
    def setUp(self):
        self.f=json.loads((Path(__file__).parent/'fixtures/espn_current_0022600112.json').read_text())
        self.board={'events':[self.f['event']]}
        self.event_id=self.f['event']['id']

    def test_pair_is_bounded_to_two_requests(self):
        fetcher=Mock(side_effect=[(self.board,{}),(self.f['summary'],{})])
        pair=fetch_pair(self.f['canonical'],self.event_id,fetcher)
        self.assertEqual(pair['summary'],self.f['summary'])
        self.assertEqual(fetcher.call_count,2)

    def test_pregame_never_fetches_summary_or_invents_estimate(self):
        self.board['events'][0]['competitions'][0]['status']['type']['state']='pre'
        fetcher=Mock(return_value=(self.board,{}))
        with self.assertRaises(PregameNotReady): fetch_pair(self.f['canonical'],self.event_id,fetcher)
        self.assertEqual(fetcher.call_count,1)

    def test_missing_duplicate_wrong_season_and_date_fail(self):
        for defect in ('missing','duplicate','season','date'):
            board=deepcopy(self.board)
            if defect=='missing': board['events']=[]
            if defect=='duplicate': board['events']*=2
            if defect=='season': board['events'][0]['season']['type']=1
            if defect=='date': board['events'][0]['competitions'][0]['date']='2026-10-24T23:00Z'
            with self.subTest(defect=defect),self.assertRaises(ValueError):
                current_event(self.f['canonical'],self.event_id,Mock(return_value=(board,{})))
