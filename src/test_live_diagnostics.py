import unittest
from unittest.mock import Mock
from live_diagnostics import RefreshDiagnostics


class DiagnosticsTest(unittest.TestCase):
    def test_throttle_state_change_and_capacity(self):
        clock=Mock(return_value=0);emit=Mock()
        log=RefreshDiagnostics(clock,emit,max_entries=2)
        self.assertTrue(log.record('0022600125','scheduled',.1))
        self.assertFalse(log.record('0022600125','scheduled',.1))
        self.assertTrue(log.record('0022600125','unavailable',.2,error_type='TimeoutError'))
        clock.return_value=61
        self.assertTrue(log.record('0022600125','unavailable',.2))
        for game in ('0022600126','0022600127'):log.record(game,'scheduled',.1)
        self.assertEqual(len(log.states),2)
        self.assertEqual(emit.call_count,5)

    def test_no_raw_errors_or_invalid_measurements(self):
        emit=Mock();log=RefreshDiagnostics(emit=emit)
        self.assertFalse(log.record('private-id','unavailable',.1))
        self.assertFalse(log.record('0022600125','unavailable',float('nan')))
        log.record('0022600125','unavailable',.2,error_type='private message with spaces')
        self.assertNotIn('private',emit.call_args.args[0])
