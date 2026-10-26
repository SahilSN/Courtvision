from copy import deepcopy
import unittest
from unittest.mock import Mock

from feed_progress import FeedProgress


class ProgressTest(unittest.TestCase):
    def setUp(self):
        self.clock=Mock(return_value=0)
        self.tracker=FeedProgress(threshold=10,max_entries=2,clock=self.clock)
        self.feed={'summary':{'plays':[{'score':1}], 'boxscore':{}, 'header':{'competitions':[{
            'status':{'type':{'state':'in','name':'STATUS_IN_PROGRESS','completed':False}}, 'competitors':[]}]}}}

    def test_repeated_acquisition_does_not_reset_progress(self):
        self.assertEqual(self.tracker.observe('game',self.feed),('observing',0))
        self.clock.return_value=11
        self.assertEqual(self.tracker.observe('game',deepcopy(self.feed)),('possibly_stalled',11))
        self.feed['summary']['plays'][0]['score']=2
        self.assertEqual(self.tracker.observe('game',self.feed),('observing',0))

    def test_final_and_intermission_not_stalled_and_resume_restarts(self):
        self.tracker.observe('game',self.feed)
        self.clock.return_value=20
        status=self.feed['summary']['header']['competitions'][0]['status']['type']
        status['name']='STATUS_HALFTIME'
        self.assertEqual(self.tracker.observe('game',self.feed),('not_active',None))
        status['name']='STATUS_IN_PROGRESS'
        self.assertEqual(self.tracker.observe('game',self.feed),('observing',0))
        status['completed']=True
        self.assertEqual(self.tracker.observe('game',self.feed),('not_active',None))

    def test_game_isolation_and_bounded_eviction(self):
        for game in ('a','b','c'): self.tracker.observe(game,self.feed)
        self.assertEqual(len(self.tracker._states),2)
        self.clock.return_value=20
        self.assertEqual(self.tracker.observe('a',self.feed),('observing',0))
