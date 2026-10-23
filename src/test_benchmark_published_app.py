import unittest

from benchmark_published_app import benchmark


class BenchmarkSettingsTest(unittest.TestCase):
    def test_unbounded_or_empty_runs_are_rejected_before_app_execution(self):
        for repeats in (0, -1, 6, 1000):
            with self.subTest(repeats=repeats), self.assertRaises(ValueError):
                benchmark(repeats)
