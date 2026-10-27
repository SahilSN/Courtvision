import os
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from live_preview_view import verification_label

from streamlit.testing.v1 import AppTest


class PreviewTest(unittest.TestCase):
    def test_verified_time_is_explicit_utc_and_never_invented(self):
        text = verification_label(SimpleNamespace(age_seconds=17, verified_at='2026-10-26T15:30:00+02:00'))
        self.assertIn('13:30:00 UTC', text)
        self.assertIn('17s old at the last refresh', text)
        self.assertIn('Not the age of the last play', text)
        for value in (None, 'invalid', '2026-10-26T12:00:00'):
            text = verification_label(SimpleNamespace(age_seconds=17, verified_at=value))
            self.assertNotIn('Last verified at', text)
            self.assertIn('acquired 17s', text)

    def test_gate_and_all_states_offline(self):
        path=Path(__file__).resolve().parents[1]/'cloud/live_preview.py'
        with patch.dict(os.environ,{'COURTVISION_LOCAL_LIVE_PREVIEW':'0'}):
            app=AppTest.from_file(str(path),default_timeout=60).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.selectbox)
        with patch.dict(os.environ,{'COURTVISION_LOCAL_LIVE_PREVIEW':'1'}), \
             patch('requests.sessions.Session.request',side_effect=AssertionError('Unexpected HTTP')):
            app=AppTest.from_file(str(path),default_timeout=60).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.dataframe),2)
            html=' '.join(str(element.value) for element in app.markdown)
            self.assertIn('Game snapshot scoreboard',html)
            self.assertIn('data:image/svg+xml;base64,',html)
            self.assertIn('Houston Rockets',html)
            self.assertIn('Oklahoma City Thunder',html)
            self.assertIn('FINAL',html)
            self.assertIn('Game complete',html)
            self.assertIn('model at last event',html)
            for state,phrase in [('Stale snapshot','last validated'),('Possibly stalled','not changed'),('Unavailable','No estimate')]:
                app.selectbox[0].set_value(state).run()
                self.assertFalse(app.exception)
                text=' '.join(str(element.value) for element in [*app.info,*app.warning])
                self.assertIn(phrase,text)
                if state!='Unavailable':
                    self.assertIn('DELAYED',' '.join(str(x.value) for x in app.markdown))
                if state=='Unavailable': self.assertFalse(app.dataframe)
