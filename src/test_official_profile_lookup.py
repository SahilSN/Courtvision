from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import Mock, patch

from official_profile_lookup import ProfileLookup, profile_identity, validate_evidence
from official_live_rosters import roster_candidates, validate_roster_artifact
from live_artifacts import read_json, write_json

TEAM = 1610612747
URL = 'https://www.nba.com/player/1641751/arthur-kaluma'
NOW = datetime(2026, 10, 27, 23, tzinfo=timezone.utc)


def html(**changes):
    record = dict(personId=1641751, firstName='Arthur', lastName='Kaluma', teamId=TEAM)
    record.update(changes)
    return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps(
        {'props': {'pageProps': {'playerProfile': record}}})+'</script>'


class ProfileTest(unittest.TestCase):
    def lookup(self, **kwargs):
        fetch = Mock(side_effect=lambda url: '<a href="/player/1641751/arthur-kaluma">Player</a>'
                     if url.endswith('/roster') else html())
        return ProfileLookup(fetcher=fetch, **kwargs), fetch

    def test_exact_evidence_and_request_cache(self):
        lookup, fetch = self.lookup()
        for _ in range(2):
            result = lookup.resolve('Arthur Kaluma', TEAM, '4433136', NOW)
            self.assertEqual(result['personId'], 1641751)
            self.assertEqual(validate_evidence(result, NOW), result)
        self.assertEqual(fetch.call_count, 2)

    def test_wrong_team_name_id_url_and_unstructured_text_rejected(self):
        for document, url in [(html(teamId=1610612738), URL),
                (html(lastName='Other'), URL), (html(personId=123), URL),
                (html(), URL.replace('www.nba.com', 'example.com')),
                ('Arthur Kaluma Lakers 1641751', URL)]:
            with self.subTest(url=url, document=document):
                with self.assertRaises((ValueError, KeyError)):
                    profile_identity(document, url, 'Arthur Kaluma', TEAM)

    def test_directory_alone_not_enough_and_duplicate_links_ambiguous(self):
        for document in ['No official player link',
                '<a href="/player/1641751/arthur-kaluma"></a><a href="/player/99/arthur-kaluma"></a>',
                '<a href="https://example.com/player/1641751/arthur-kaluma"></a>']:
            fetch = Mock(return_value=document)
            with self.assertRaises(ValueError):
                ProfileLookup(fetcher=fetch).resolve('Arthur Kaluma', TEAM, '4433136', NOW)
            self.assertEqual(fetch.call_count, 1)

    def test_budget_and_missing_espn_id(self):
        for kwargs in [dict(max_requests=1), dict(allowed=lambda: False)]:
            lookup, fetch = self.lookup(**kwargs)
            with self.assertRaises(TimeoutError):
                lookup.resolve('Arthur Kaluma', TEAM, '4433136', NOW)
            self.assertLessEqual(fetch.call_count, 1)
        lookup, fetch = self.lookup()
        with self.assertRaises(ValueError):
            lookup.resolve('Arthur Kaluma', TEAM, 'None', NOW)
        fetch.assert_not_called()

    def test_failure_cached_without_repeated_requests(self):
        fetch = Mock(side_effect=TimeoutError())
        lookup = ProfileLookup(fetcher=fetch)
        for _ in range(2):
            with self.assertRaises((ValueError, TimeoutError)):
                lookup.resolve('Arthur Kaluma', TEAM, '4433136', NOW)
        self.assertEqual(fetch.call_count, 1)

    def test_invalid_saved_evidence_rejected(self):
        lookup, _ = self.lookup()
        evidence = lookup.resolve('Arthur Kaluma', TEAM, '4433136', NOW)
        for key, value in [('source', 'https://example.com/player/1641751'),
                           ('checkedAt', (NOW+timedelta(seconds=1)).isoformat()),
                           ('personId', True), ('teamId', 42), ('espnId', 'unknown')]:
            broken = {**evidence, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_evidence(broken, NOW)

    def test_preparation_persists_and_reader_consumes_scoped_evidence(self):
        from test_daily_live_preparation import DailyPreparationTest
        from prepare_daily_live import prepare_daily_live
        fixture = DailyPreparationTest(methodName='test_prepare_is_bounded_and_automatic_policy_has_no_network')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        # A synthetic new player, on an actual fixture team, missing from static IDs.
        team = fixture.context['games'][0]['homeTeamId']
        name, person = 'Exact New Player', 19999999
        def fetch(url):
            if 'commonteamroster?' in url:
                raise TimeoutError()
            data, meta = fixture.fetch(url)
            for group in data['boxscore']['players']:
                for row in group['statistics'][0]['athletes']:
                    row['athlete'] = dict(displayName=name, id='123456')
            return data, meta
        def page(url):
            if url.endswith('/roster'):
                return '<a href="/player/19999999/exact-new-player"></a>'
            return html(personId=person, firstName='Exact New', lastName='Player', teamId=team)
        report = prepare_daily_live(fixture.root, now=fixture.now, fetcher=fetch, profile_fetcher=page)
        path = fixture.directory/'2026-27_roster_identities_v1.json'
        bundle = read_json(path)
        self.assertEqual(len(bundle['profiles']), 1)
        self.assertEqual(roster_candidates(name,'2026-27',team,fixture.day,path=path,now=fixture.now),{person})
        self.assertFalse(roster_candidates(name,'2025-26',team,fixture.day,path=path,now=fixture.now))
        self.assertFalse(roster_candidates(name,'2026-27',team+1,fixture.day,path=path,now=fixture.now))
        with patch('official_profile_lookup.fetch_html', side_effect=AssertionError('Viewer network')):
            self.assertEqual(roster_candidates(name,'2026-27',team,fixture.day,path=path,now=fixture.now),{person})
        self.assertGreater(report['pendingIdentities'], 0)
        # Fresh saved evidence is reused with its original timestamp; no new
        # directory request for that player/team is required next time.
        later = fixture.now+timedelta(minutes=16)
        pages = Mock(side_effect=page)
        prepare_daily_live(fixture.root, now=later, fetcher=fetch, profile_fetcher=pages)
        refreshed = read_json(path)
        self.assertEqual(refreshed['profiles'][0]['checkedAt'], bundle['profiles'][0]['checkedAt'])
        self.assertNotIn('https://www.nba.com/hawks/roster', [c.args[0] for c in pages.call_args_list])
        # A later check never revives original evidence age.
        bundle['checkedAt'] = (fixture.now+timedelta(hours=38)).isoformat()
        write_json(path, bundle)
        self.assertFalse(roster_candidates(name,'2026-27',team,fixture.day,path=path,now=fixture.now+timedelta(hours=38)))
        broken = deepcopy(bundle)
        broken['profiles'].append(deepcopy(broken['profiles'][0]))
        with self.assertRaises(ValueError):
            validate_roster_artifact(broken,'2026-27',fixture.day)


if __name__ == '__main__':
    unittest.main()
