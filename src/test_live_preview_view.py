import os
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class PreviewTest(unittest.TestCase):
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
            for state,phrase in [('Stale snapshot','last validated'),('Possibly stalled','not changed'),('Unavailable','No estimate')]:
                app.selectbox[0].set_value(state).run()
                self.assertFalse(app.exception)
                text=' '.join(str(element.value) for element in [*app.info,*app.warning])
                self.assertIn(phrase,text)
                if state=='Unavailable': self.assertFalse(app.dataframe)
