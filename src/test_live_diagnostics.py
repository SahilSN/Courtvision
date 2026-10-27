import unittest
from unittest.mock import Mock
from live_diagnostics import RefreshDiagnostics
from live_diagnostics import CoherenceDiagnostics
import json


class DiagnosticsTest(unittest.TestCase):
    def test_observed_mismatch_episode_and_recovery_duration(self):
        clock = Mock(return_value=0); emit = Mock()
        log = CoherenceDiagnostics(clock=clock, emit=emit)
        log.observe('0022600127', None)
        clock.return_value = 10
        self.assertTrue(log.observe('0022600127', 'timeline_header'))
        clock.return_value = 15
        self.assertFalse(log.observe('0022600127', 'timeline_header'))
        clock.return_value = 40
        self.assertTrue(log.observe('0022600127', None))
        report = json.loads(emit.call_args.args[0].split(' ', 1)[1])
        self.assertEqual(report['event'], 'reconciled')
        self.assertEqual(report['observedMismatchSeconds'], 30)
        self.assertEqual(report['coherentAcquisitions'], 2)
        self.assertEqual(report['mismatchedAcquisitions'], 2)
        clock.return_value = 45; log.observe('0022600127', 'box_points')
        clock.return_value = 50; log.observe('0022600127', None)
        self.assertEqual(json.loads(emit.call_args.args[0].split(' ',1)[1])['observedMismatchSeconds'], 5)

    def test_coherence_capacity_privacy_and_emitter_failure(self):
        emit = Mock(side_effect=OSError('private details'))
        log = CoherenceDiagnostics(emit=emit, max_entries=2)
        self.assertFalse(log.observe('private-user', 'timeline_header'))
        self.assertFalse(log.observe('0022600127', 'private error text'))
        self.assertFalse(log.observe('0022600127', 'box_points'))
        for game in ('0022600125', '0022600126'):
            log.observe(game, None)
        self.assertEqual(len(log.states), 2)
        self.assertNotIn('private', emit.call_args.args[0])

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
