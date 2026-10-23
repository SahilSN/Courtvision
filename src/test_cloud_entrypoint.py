import os
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class CloudEntrypointTest(unittest.TestCase):
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
