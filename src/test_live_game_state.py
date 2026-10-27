from copy import deepcopy
from types import SimpleNamespace
import unittest

from live_game_state import verified_source_state, presentation_state


def feed(state,completed):
    status=dict(type=dict(state=state,completed=completed))
    return dict(event=dict(competitions=[dict(status=status)]),
                summary=dict(header=dict(competitions=[dict(status=deepcopy(status))])))


class GameStateTest(unittest.TestCase):
    def test_final_needs_both_explicit_completed_sections(self):
        self.assertEqual(verified_source_state(feed('post',True)),'post')
        self.assertEqual(verified_source_state(feed('in',False)),'in')
        for state,completed in [('in',True),('post',False),('post',1),('pre',False)]:
            self.assertEqual(verified_source_state(feed(state,completed)),'unknown')
        data=feed('post',True)
        data['event']['competitions'][0]['status']['type']['state']='in'
        self.assertEqual(verified_source_state(data),'unknown')
        self.assertEqual(verified_source_state({}),'unknown')

    def test_stale_final_never_looks_current(self):
        result=SimpleNamespace(display_state='validated_snapshot',snapshot=SimpleNamespace(source_state='post'))
        self.assertEqual(presentation_state(result),'Final')
        for state in ('stale_snapshot','possibly_stalled'):
            result.display_state=state
            self.assertEqual(presentation_state(result),'Delayed')
        result.display_state='invalid'
        self.assertEqual(presentation_state(result),'Unavailable')
        self.assertEqual(presentation_state(None),'Unavailable')

    def test_zero_clock_alone_is_not_final(self):
        result=SimpleNamespace(display_state='progress_unknown',snapshot=SimpleNamespace(source_state='in'))
        self.assertEqual(presentation_state(result),'Live')
        result.snapshot.source_state='unknown'
        self.assertEqual(presentation_state(result),'Snapshot')
