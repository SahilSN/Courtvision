from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from cloud_espn_adapter import normalize_snapshot,ProviderContextUnavailable
from cloud_espn_box import normalize_box


class SourceLedgerTest(unittest.TestCase):
    def setUp(self):
        self.feed=json.loads((Path(__file__).parent/'fixtures/espn_score_conflict_0022600122.json').read_text())
        self.block=patch('requests.sessions.Session.request',side_effect=AssertionError('No HTTP'))
        self.block.start();self.addCleanup(self.block.stop)

    def normalize(self):
        return normalize_snapshot(self.feed['event'],self.feed['summary'],self.feed['canonical'])

    def test_captured_phantom_foul_points_reconcile_every_scorer(self):
        original=deepcopy(self.feed)
        timeline=self.normalize()
        self.assertEqual(timeline.attrs['scoreSource'],'reconciled_scoring_events')
        self.assertEqual(int(timeline.scoreHome.iloc[-1]),109)
        self.assertEqual(int(timeline.reportedScoreHome.iloc[-1]),112)
        self.assertEqual(int(timeline.scoreAway.iloc[-1]),113)
        self.assertEqual(self.feed,original)
        box=normalize_box(self.feed['event'],self.feed['summary'],self.feed['canonical'])
        self.assertEqual(sorted(box['teams'].points),[109,113])

    def test_ambiguous_or_unreconciled_metadata_never_repaired(self):
        original=deepcopy(self.feed)
        for defect in ('missing_flag','bad_points','flagged_foul','header','player_totals','missing_raw_score'):
            self.feed=deepcopy(original)
            plays=self.feed['summary']['plays']
            scored=next(p for p in plays if p['scoringPlay'])
            if defect=='missing_flag':del plays[0]['scoringPlay']
            if defect=='bad_points':scored['scoreValue']=True
            if defect=='flagged_foul':
                foul=next(p for p in plays if p['id']=='401909871472');foul['scoringPlay']=True
            if defect=='header':self.feed['summary']['header']['competitions'][0]['competitors'][0]['score']='999'
            if defect=='missing_raw_score':del plays[0]['homeScore']
            if defect=='player_totals':
                stats=self.feed['summary']['boxscore']['players'][0]['statistics'][0]
                i=stats['labels'].index('PTS');played=[a for a in stats['athletes'] if not a['didNotPlay'] and int(a['stats'][i])>0]
                played[0]['stats'][i]=str(int(played[0]['stats'][i])+1)
                played[1]['stats'][i]=str(int(played[1]['stats'][i])-1)
            with self.subTest(defect=defect),self.assertRaises(ProviderContextUnavailable):self.normalize()

    def test_unrelated_identity_failure_still_blocks(self):
        self.feed['summary']['plays'][1]['participants']=[{'athlete':{'id':'unresolved'}}]
        with self.assertRaises(ProviderContextUnavailable):self.normalize()
