import copy
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch, Mock

import pandas as pd
from streamlit.testing.v1 import AppTest

from published_replay import PILOT_PATH
from replay_catalog import INDEX, build_index, catalog_seasons, load_catalog_replay, read_index, season_catalog, valid_identity
from replay_collection import GAME_IDS


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        folder=self.root/'results/replay_pilot'
        folder.mkdir(parents=True)
        for gid in GAME_IDS:
            shutil.copyfile(PILOT_PATH.parent/f'{gid}.json',folder/f'{gid}.json')
        build_index(self.root)

    def current_export(self, completed=True):
        data=json.loads(PILOT_PATH.read_text())
        data.update(gameId='0022600001',season='2026-27',date='2026-10-21',completed=completed,seasonType='Regular Season')
        path=self.root/'results/replay_catalog/games/0022600001.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(data))
        return path

    def metadata(self):
        path=self.root/'results/season_intelligence/2026-27_team_rating_games_v1.csv'
        path.parent.mkdir(parents=True)
        pd.DataFrame([
            dict(season='2026-27',gameDate='2026-10-21',gameId='0022600001',team='OKC',opponent='HOU',isHome=1),
            dict(season='2026-27',gameDate='2026-10-21',gameId='0022600001',team='HOU',opponent='OKC',isHome=0),
            dict(season='2026-27',gameDate='2026-10-22',gameId='0022600002',team='BOS',opponent='NYK',isHome=1),
        ]).to_csv(path,index=False)

    def test_completed_current_season_metadata_is_cataloged_not_assumed_playable(self):
        self.metadata()
        games,failed=season_catalog('2026-27',self.root)
        self.assertFalse(failed)
        self.assertEqual(len(games),1)  # An incomplete pair is not advertised.
        self.assertEqual(games[0]['availability'],'Not prepared')
        self.assertEqual(catalog_seasons(self.root)[0],'2026-27')

    def test_explicit_completed_current_export_is_ready_and_uses_same_offline_view(self):
        self.metadata();self.current_export();build_index(self.root)
        games,_=season_catalog('2026-27',self.root)
        self.assertEqual(games[0]['availability'],'Prepared')
        data,timeline=load_catalog_replay(games[0],self.root)
        self.assertEqual(data['season'],'2026-27')
        self.assertEqual(int(timeline.period.max()),6)

    def test_nonfinal_export_rejected_without_replacing_last_good_index(self):
        before=(self.root/INDEX).read_bytes()
        self.current_export(False)
        with self.assertRaises(ValueError):build_index(self.root)
        self.assertEqual((self.root/INDEX).read_bytes(),before)

    def test_checksum_changes_and_wrong_metadata_block_playback(self):
        entry=next(iter(read_index(self.root).values()))
        with self.assertRaises(ValueError):load_catalog_replay({**entry,'home':'BOS'},self.root)
        path=self.root/f'results/replay_pilot/{entry["gameId"]}.json'
        path.write_text(path.read_text()+' ')
        with self.assertRaises(ValueError):load_catalog_replay(entry,self.root)

    def test_bad_or_missing_index_does_not_erase_completed_metadata(self):
        self.metadata()
        for raw in ('{','{"schemaVersion":999,"games":[]}'):
            (self.root/INDEX).write_text(raw)
            games,failed=season_catalog('2026-27',self.root)
            self.assertTrue(failed)
            self.assertEqual(games[0]['availability'],'Not prepared')

    def test_no_path_escape_duplicates_or_new_legacy_exceptions(self):
        original=json.loads((self.root/INDEX).read_text())
        for change in ('path','duplicate','legacy'):
            data=copy.deepcopy(original)
            if change=='path':data['games'][0]['gameId']='../../secret'
            elif change=='duplicate':data['games'].append(data['games'][0])
            else:data['games'][0].update(gameId='0022600001',season='2026-27',date='2026-10-21')
            (self.root/INDEX).write_text(json.dumps(data))
            with self.assertRaises(ValueError):read_index(self.root)

    def test_symlink_artifact_is_rejected(self):
        entry=next(iter(read_index(self.root).values()))
        path=self.root/f'results/replay_pilot/{entry["gameId"]}.json'
        path.unlink();path.symlink_to(PILOT_PATH)
        with self.assertRaises(ValueError):load_catalog_replay(entry,self.root)

    def test_regular_season_identity_and_bubble_dates(self):
        valid_identity('0021900001','2019-20','2020-08-01')
        for gid,season,day in [('0012600001','2026-27','2026-10-21'),('0022500001','2026-27','2026-10-21'),
                               ('0022600001','2026-28','2026-10-21'),('0022600001','2026-27','2025-10-21')]:
            with self.assertRaises(ValueError):valid_identity(gid,season,day)

    def test_catalog_filters_and_current_empty_playback_are_offline(self):
        self.metadata()
        script=f'from replay_view import render_replay_view\nrender_replay_view({str(self.root)!r})'
        with patch('requests.sessions.Session.request',side_effect=AssertionError('No feed')), \
             patch('subprocess.Popen',side_effect=AssertionError('No worker')):
            app=AppTest.from_string(script,default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertFalse(app.slider)
            self.assertEqual(app.selectbox(key='replay_catalog_season').value,'2026-27')
            self.assertIn('No prepared replays',' '.join(x.value for x in app.info))
            app.selectbox(key='replay_catalog_season').select('2025-26').run()
            self.assertFalse(app.exception)
            self.assertTrue(app.slider)
            app.selectbox(key='replay_catalog_availability').select('Not prepared').run()
            self.assertFalse(app.slider)
            self.assertIn('No published completed games',' '.join(x.value for x in app.info))

    def test_preparation_failure_cannot_replace_published_artifact(self):
        from prepare_replay_catalog import prepare
        path=self.current_export();build_index(self.root)
        before=path.read_bytes()
        def changed_export(gid,season,cache_root,destination):
            destination.write_bytes(before+b' ')
            return destination
        with patch('prepare_replay_catalog.export_game',side_effect=changed_export),self.assertRaises(ValueError):
            prepare(self.root,self.root,'2026-27',['0022600001'])
        self.assertEqual(path.read_bytes(),before)
