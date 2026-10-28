"""Bounded official HTML fallback. Discovery links are never identity evidence."""

from datetime import datetime
from html.parser import HTMLParser
import json
import re
import ssl
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, HTTPSHandler, build_opener

from espn_live import normalize_name
from nba_api.stats.static import teams
from probe_live_access import NoRedirects

SLUGS = {
    'ATL':'hawks', 'BOS':'celtics', 'BKN':'nets', 'CHA':'hornets', 'CHI':'bulls',
    'CLE':'cavaliers', 'DAL':'mavericks', 'DEN':'nuggets', 'DET':'pistons',
    'GSW':'warriors', 'HOU':'rockets', 'IND':'pacers', 'LAC':'clippers',
    'LAL':'lakers', 'MEM':'grizzlies', 'MIA':'heat', 'MIL':'bucks',
    'MIN':'timberwolves', 'NOP':'pelicans', 'NYK':'knicks', 'OKC':'thunder',
    'ORL':'magic', 'PHI':'sixers', 'PHX':'suns', 'POR':'blazers', 'SAC':'kings',
    'SAS':'spurs', 'TOR':'raptors', 'UTA':'jazz', 'WAS':'wizards',
}


def team_slug(team_id):
    matches = [t['abbreviation'] for t in teams.get_teams() if t['id'] == team_id]
    if len(matches) != 1:
        raise ValueError('Unknown official NBA team')
    return SLUGS[matches[0]]


def valid_source(url, person_id, team_id):
    if not isinstance(url, str):
        return False
    parts = urlsplit(url)
    return (parts.scheme == 'https' and parts.netloc == 'www.nba.com'
            and not parts.query and not parts.fragment
            and re.fullmatch(rf'/(?:{team_slug(team_id)}/)?player/{person_id}(?:/[a-z0-9-]+)?/?', parts.path) is not None)


def fetch_html(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.netloc != 'www.nba.com' or parts.query or parts.fragment:
        raise ValueError('Unofficial profile request')
    import certifi
    opener = build_opener(NoRedirects(), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))
    with opener.open(Request(url, headers={'User-Agent': 'Courtvision-Official-Identity/1.0',
                                         'Accept': 'text/html'}), timeout=5) as response:
        if response.headers.get_content_type() != 'text/html':
            raise ValueError('Official profile is not HTML')
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Oversized official profile')
        return raw.decode('utf-8')


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links, self.data, self._script = [], [], False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])
        if tag == 'script' and attrs.get('id') == '__NEXT_DATA__':
            self._script = True

    def handle_endtag(self, tag):
        if tag == 'script':
            self._script = False

    def handle_data(self, value):
        if self._script:
            self.data.append(value)


def profile_identity(html, url, name, team_id):
    """Require ID, exact full name and team in ONE structured player record."""
    page = Page(html)
    payload = json.loads(''.join(page.data))
    found = set()
    def walk(value):
        if isinstance(value, dict):
            person = value.get('personId', value.get('playerId'))
            full = value.get('displayFirstLast') or ' '.join(
                str(value.get(key, '')) for key in ('firstName', 'lastName'))
            if (type(person) is int and 0 < person < 1_000_000_000
                    and type(value.get('teamId')) is int and value['teamId'] == team_id
                    and normalize_name(full) == normalize_name(name)
                    and valid_source(url, person, team_id)):
                found.add(person)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    # Do not accept IDs from analytics, arbitrary scripts, text, or URL alone.
    walk(payload['props']['pageProps'])
    if len(found) != 1:
        raise ValueError('Official profile lacks a unique exact team/player record')
    return found.pop()


class ProfileLookup:
    def __init__(self, *, fetcher=fetch_html, allowed=lambda: True, max_requests=4):
        self.fetcher, self.allowed, self.remaining = fetcher, allowed, max_requests
        self.cache = {}

    def fetch(self, url):
        if url not in self.cache:
            if self.remaining <= 0 or not self.allowed():
                raise TimeoutError('Official profile lookup budget reached')
            self.remaining -= 1
            self.cache[url] = None  # Cache failures too; no repeated team request.
            self.cache[url] = self.fetcher(url)
        if self.cache[url] is None:
            raise ValueError('Official page unavailable')
        return self.cache[url]

    def resolve(self, name, team_id, espn_id, now):
        if not isinstance(espn_id, str) or not re.fullmatch(r'[0-9]{1,12}', espn_id):
            raise ValueError('Missing exact ESPN identity')
        slug = team_slug(team_id)
        directory = f'https://www.nba.com/{slug}/roster'
        page = Page(self.fetch(directory))
        # Slug only discovers candidates; structured profile verification below
        # remains mandatory. No IDs are inferred from a name or ESPN number.
        wanted = normalize_name(name)
        links = set()
        for href in page.links:
            url = urljoin(directory, href)
            match = re.fullmatch(r'/(?:'+slug+r'/)?player/([0-9]+)/([a-z0-9-]+)/?', urlsplit(url).path)
            if match and normalize_name(match[2]) == wanted and valid_source(url, int(match[1]), team_id):
                links.add(url)
        if len({int(re.search(r'/player/([0-9]+)', u)[1]) for u in links}) != 1:
            raise ValueError('Missing or ambiguous official directory link')
        for url in sorted(links):
            try:
                person = profile_identity(self.fetch(url), url, name, team_id)
            except (ValueError, KeyError, TypeError):
                continue
            return dict(personId=person, fullName=name, teamId=team_id, espnId=espn_id,
                        source=url, directorySource=directory, checkedAt=now.isoformat(),
                        method='official-profile-exact-name-team-id')
        raise ValueError('No verified official player profile')


def validate_evidence(item, checked):
    person, team = item['personId'], item['teamId']
    if (type(person) is not int or not 0 < person < 1_000_000_000
            or type(team) is not int or not isinstance(item['fullName'], str)
            or not 1 <= len(item['fullName']) <= 100
            or any(ord(c) < 32 for c in item['fullName']) or not normalize_name(item['fullName'])
            or not isinstance(item['espnId'], str) or not re.fullmatch(r'[0-9]{1,12}', item['espnId'])
            or item['method'] != 'official-profile-exact-name-team-id'
            or not valid_source(item['source'], person, team)
            or item['directorySource'] != f'https://www.nba.com/{team_slug(team)}/roster'):
        raise ValueError('Invalid official profile evidence')
    stamp = datetime.fromisoformat(item['checkedAt'])
    if stamp.tzinfo is None or stamp > checked:
        raise ValueError('Invalid official profile timestamp')
    return item
