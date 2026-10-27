from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
from live_runtime_gate import module_matches, runtime_ready


class RuntimeGateTest(unittest.TestCase):
    def test_actual_runtime_matches_deployed_source(self):
        self.assertTrue(runtime_ready(Path(__file__).resolve().parents[1]))

    def test_stale_function_method_and_literal_rejected(self):
        original='RULES=(1,)\ndef f():\n return 1\nclass Cache:\n def get(self):\n  return 1\n'
        module=types.ModuleType('sample');exec(compile(original,'sample.py','exec'),module.__dict__)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sample.py';path.write_text(original)
            self.assertTrue(module_matches(module,path,('RULES',)))
            for source in (original.replace('RULES=(1,)','RULES=(2,)'),
                           original.replace('def f():\n return 1','def f():\n return 2'),
                           original.replace('def get(self):\n  return 1','def get(self):\n  return 2')):
                path.write_text(source)
                self.assertFalse(module_matches(module,path,('RULES',)))
            path.write_text('broken (')
            self.assertFalse(runtime_ready(directory))

    def test_stale_import_binding_rejected(self):
        import cloud_live_bundle
        with patch.object(cloud_live_bundle,'_normalize_box',lambda *a,**k:None):
            self.assertFalse(runtime_ready(Path(__file__).resolve().parents[1]))
