import json
from pathlib import Path
import unittest
from unittest.mock import patch
from cloud_espn_adapter import normalize_snapshot
from cloud_espn_box import normalize_box


class CurrentFeedsTest(unittest.TestCase):
    def test_captured_regulation_games_with_reviewed_rookies(self):
        for game in ('0022600112','0022600113'):
            f=json.loads((Path(__file__).parent/'fixtures'/f'espn_current_{game}.json').read_text())
            with self.subTest(game=game),patch('requests.sessions.Session.request',side_effect=AssertionError('Unexpected HTTP')):
                timeline=normalize_snapshot(f['event'],f['summary'],f['canonical'])
                box=normalize_box(f['event'],f['summary'],f['canonical'])
                self.assertEqual(int(timeline.period.max()),4)
                self.assertEqual(set(box['teams'].points),{int(timeline.scoreHome.iloc[-1]),int(timeline.scoreAway.iloc[-1])})
                self.assertTrue(box['players'].loc[~box['players'].didNotPlay].personId.notna().all())
