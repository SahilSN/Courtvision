import os
from pathlib import Path
import unittest
import runpy
import streamlit as st
from unittest.mock import patch, Mock

from streamlit.testing.v1 import AppTest


class CloudEntrypointTest(unittest.TestCase):
    def test_prepared_route_defaults_to_intelligence_and_kill_recovers_session(self):
        entrypoint=Path(__file__).resolve().parents[1]/'cloud/app.py'
        real_run=runpy.run_path
        calls=[]
        healthy=Mock(return_value=True)
        def fake_view(root,games,rollout_guard=None):
            self.assertIsNotNone(rollout_guard)
            calls.append(tuple(games));st.info('TEST LIVE ROUTE')
        def dispatch(path,*args,**kwargs):
            if Path(path).name=='live_runtime_gate.py':return {'runtime_ready':healthy}
            if Path(path).name=='live_beta_view.py': return {'render_live_beta':fake_view}
            return real_run(path,*args,**kwargs)
        with patch.dict(os.environ,{'COURTVISION_CLOUD_READY':'1','COURTVISION_DISABLE_OPERATOR_PROBES':'1',
                                   'COURTVISION_ENABLE_LIVE_BETA':'1','COURTVISION_DISABLE_LIVE_BETA':'0'}), \
             patch('live_rollout.allowed_games',return_value=('0022600125',)) as gate, \
             patch('runpy.run_path',side_effect=dispatch), \
             patch('requests.sessions.Session.request',side_effect=AssertionError('Unexpected network')):
            app=AppTest.from_file(str(entrypoint),default_timeout=90).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.sidebar.radio(key='cloud_workspace').value,'Season Intelligence')
            self.assertFalse(calls)
            app.sidebar.radio(key='cloud_workspace').set_value('Live Beta').run()
            self.assertFalse(app.exception)
            self.assertEqual(calls,[('0022600125',)])
            healthy.return_value=False
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['cloud_workspace'],'Season Intelligence')
            self.assertEqual(len(calls),1)
            healthy.return_value=True
            gate.return_value=()
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['cloud_workspace'],'Season Intelligence')
            self.assertFalse(any(x.value=='TEST LIVE ROUTE' for x in app.info))
            gate.side_effect=RuntimeError('private diagnostic detail')
            app.run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['cloud_workspace'],'Season Intelligence')

    def test_setup_is_closed_without_explicit_readiness(self):
        entrypoint = Path(__file__).resolve().parents[1] / "cloud" / "app.py"
        with patch.dict(os.environ, {"COURTVISION_CLOUD_READY": ""}), \
             patch("requests.sessions.Session.request") as network, \
             patch("subprocess.Popen") as workers:
            app = AppTest.from_file(str(entrypoint)).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.info), 1)
            self.assertIn("not available yet", app.info[0].value)
            self.assertEqual(len(app.sidebar.radio), 0)
            self.assertEqual(len(app.dataframe), 0)
            network.assert_not_called()
            workers.assert_not_called()


if __name__ == "__main__":
    unittest.main()
