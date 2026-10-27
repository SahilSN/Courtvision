import json
import unittest
from summarize_live_reliability import summarize


class ReliabilitySummaryTest(unittest.TestCase):
    def test_observed_spans_and_weighted_state_samples_not_release_approval(self):
        prefix='COURTVISION_SCORE_COHERENCE '
        lines=[prefix+json.dumps(dict(gameId='0022600127',event='reconciled',observedMismatchSeconds=n)) for n in (10,20,30)]
        lines.append('COURTVISION_LIVE_STATE '+json.dumps(dict(gameId='0022600127',state='stale_snapshot',samples=4)))
        report=summarize(lines);game=report['games'][0]
        self.assertEqual(game['medianObservedSpanSeconds'],20)
        self.assertEqual(game['p95ObservedSpanSeconds'],30)
        self.assertEqual(game['presentationSamples']['stale_snapshot'],4)
        self.assertFalse(report['releaseApproval'])

    def test_rejects_private_invalid_and_nonfinite_fields_without_echoing_them(self):
        lines=['irrelevant private log', 'COURTVISION_SCORE_COHERENCE bad-json']
        for value in (float('nan'), -1, 'private payload'):
            lines.append('COURTVISION_SCORE_COHERENCE '+json.dumps(dict(gameId='0022600127',event='reconciled',observedMismatchSeconds=value)))
        report=summarize(lines)
        self.assertEqual(report['rejectedRecords'],4)
        self.assertFalse(report['games'])
        self.assertNotIn('private',json.dumps(report))
