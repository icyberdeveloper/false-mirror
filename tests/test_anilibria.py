"""Tests for Anilibria client — franchise grouping, episode detection, quality selection."""
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from clients.anilibria import (
    get_series, _get_franchise_info, _get_best_quality, _parse_episode_count,
)


# --- Fixtures ---

def _make_release(id=9600, code='test-anime', name='Тест Аниме', year=2024,
                  type_value='TV', is_ongoing=False, torrents=None):
    return {
        'id': id,
        'type': {'value': type_value, 'description': type_value},
        'year': year,
        'name': {'main': name, 'english': code, 'alternative': None},
        'alias': code,
        'is_ongoing': is_ongoing,
        'torrents': torrents or [_make_torrent()],
    }


def _make_torrent(id=1, hash='aaa', description='1-12', quality='1080p',
                  codec_label='AVC', seeders=50):
    return {
        'id': id,
        'hash': hash,
        'description': description,
        'quality': {'value': quality, 'description': quality},
        'codec': {'value': f'x264/{codec_label}', 'label': codec_label},
        'seeders': seeders,
    }


def _make_franchise(name='Тест Аниме', first_year=2024, releases=None):
    """Build a franchise API response (list with one franchise)."""
    if releases is None:
        releases = [
            _make_franchise_release(release_id=9600, sort_order=1, alias='test-anime',
                                    name='Тест Аниме', type_value='TV'),
        ]
    return [{
        'name': name,
        'first_year': first_year,
        'franchise_releases': releases,
    }]


def _make_franchise_release(release_id, sort_order, alias, name='',
                            type_value='TV', is_ongoing=False):
    return {
        'release_id': release_id,
        'sort_order': sort_order,
        'release': {
            'id': release_id,
            'alias': alias,
            'name': {'main': name},
            'type': {'value': type_value},
            'is_ongoing': is_ongoing,
        },
    }


# --- Pure function tests ---

class TestParseEpisodeCount(unittest.TestCase):
    def test_range(self):
        assert _parse_episode_count('1-12') == 12

    def test_range_not_from_one(self):
        assert _parse_episode_count('3-12') == 10

    def test_single(self):
        assert _parse_episode_count('1') == 1

    def test_empty(self):
        assert _parse_episode_count('') == 0

    def test_none(self):
        assert _parse_episode_count(None) == 0

    def test_spaces(self):
        assert _parse_episode_count('1 - 13') == 13

    def test_garbage(self):
        assert _parse_episode_count('bonus') == 0


class TestGetBestQuality(unittest.TestCase):
    def test_prefers_non_hevc(self):
        torrents = [
            _make_torrent(id=1, codec_label='HEVC', seeders=200),
            _make_torrent(id=2, codec_label='AVC', seeders=50),
        ]
        assert _get_best_quality(torrents)['id'] == 2

    def test_falls_back_to_hevc_if_only_option(self):
        torrents = [
            _make_torrent(id=1, codec_label='HEVC', seeders=100),
        ]
        assert _get_best_quality(torrents)['id'] == 1

    def test_prefers_most_seeders_among_non_hevc(self):
        torrents = [
            _make_torrent(id=1, codec_label='AVC', seeders=10),
            _make_torrent(id=2, codec_label='AVC', seeders=100),
        ]
        assert _get_best_quality(torrents)['id'] == 2


# --- Franchise info tests ---

class TestGetFranchiseInfo(unittest.TestCase):
    def _mock_get(self, franchise_response):
        """Return a mock for network.get that returns franchise_response on franchise URL."""
        def side_effect(url, proxies=None):
            mock_resp = MagicMock()
            mock_resp.json.return_value = franchise_response
            return mock_resp
        return side_effect

    @patch('clients.anilibria.network.get')
    def test_single_season_franchise(self, mock_get):
        mock_get.side_effect = self._mock_get(_make_franchise())
        release = _make_release()

        name, season, year, all_rel = _get_franchise_info(9600, release, None)

        assert name == 'Тест Аниме'
        assert season == '01'
        assert year == 2024
        assert len(all_rel) == 1

    @patch('clients.anilibria.network.get')
    def test_multi_season_franchise(self, mock_get):
        franchise = _make_franchise(releases=[
            _make_franchise_release(9600, 1, 'test-anime-s1', 'Тест S1'),
            _make_franchise_release(9839, 2, 'test-anime-s2', 'Тест S2'),
        ])
        mock_get.side_effect = self._mock_get(franchise)
        release = _make_release(id=9839)

        name, season, year, all_rel = _get_franchise_info(9839, release, None)

        assert season == '02'
        assert name == 'Тест Аниме'
        assert len(all_rel) == 2

    @patch('clients.anilibria.network.get')
    def test_no_franchise(self, mock_get):
        mock_get.side_effect = self._mock_get([])  # empty list
        release = _make_release(name='Одиночный Релиз', year=2025)

        name, season, year, all_rel = _get_franchise_info(9600, release, None)

        assert name == 'Одиночный Релиз'
        assert season == '01'
        assert year == 2025
        assert all_rel is None

    @patch('clients.anilibria.network.get')
    def test_franchise_api_failure_uses_fallback(self, mock_get):
        mock_get.side_effect = Exception('timeout')
        release = _make_release(name='Фоллбэк', year=2023)

        name, season, year, all_rel = _get_franchise_info(9600, release, None)

        assert name == 'Фоллбэк'
        assert season == '01'
        assert year == 2023
        assert all_rel is None


# --- get_series integration tests ---

class TestGetSeries(unittest.TestCase):
    def setUp(self):
        self.library = MagicMock()
        self.qbt = MagicMock()
        self.db = MagicMock()
        self.tracker = MagicMock()

    def _patch_api(self, release, franchise):
        """Patch network.get to return release then franchise data."""
        responses = []

        def side_effect(url, proxies=None):
            mock_resp = MagicMock()
            if '/anime/releases/' in url:
                mock_resp.json.return_value = release
            elif '/anime/franchises/' in url:
                mock_resp.json.return_value = franchise
            elif '/anime/torrents/' in url:
                mock_resp.content = b'torrent-data'
            responses.append(url)
            return mock_resp

        return patch('clients.anilibria.network.get', side_effect=side_effect)

    def test_downloads_new_show(self):
        release = _make_release(torrents=[_make_torrent(id=42, hash='abc123', description='1-12')])
        franchise = _make_franchise()
        self.library.count_season_files.return_value = 0
        self.qbt.torrent_hash_in_queue.return_value = False

        with self._patch_api(release, franchise):
            added = get_series(self.library, self.qbt, '/downloads/Anime',
                               [{'code': 'test-anime'}], None,
                               tracker=self.tracker, db=self.db)

        assert added == ['Тест Аниме S01']
        self.qbt.download_torrent.assert_called_once()
        args = self.qbt.download_torrent.call_args
        assert '/downloads/Anime/Тест Аниме (2024)/Season 01' == args[0][1]

    def test_skips_when_all_episodes_on_disk(self):
        release = _make_release(torrents=[_make_torrent(description='1-12')])
        franchise = _make_franchise()
        self.library.count_season_files.return_value = 12

        with self._patch_api(release, franchise):
            added = get_series(self.library, self.qbt, '/downloads/Anime',
                               [{'code': 'test-anime'}], None)

        assert added == []
        self.qbt.download_torrent.assert_not_called()

    def test_skips_when_torrent_already_in_queue(self):
        release = _make_release(torrents=[_make_torrent(hash='abc123', description='1-12')])
        franchise = _make_franchise()
        self.library.count_season_files.return_value = 0
        self.qbt.torrent_hash_in_queue.return_value = True

        with self._patch_api(release, franchise):
            added = get_series(self.library, self.qbt, '/downloads/Anime',
                               [{'code': 'test-anime'}], None)

        assert added == []
        self.qbt.download_torrent.assert_not_called()

    def test_updates_when_new_episodes_available(self):
        release = _make_release(torrents=[_make_torrent(hash='new-hash', description='1-13')])
        franchise = _make_franchise()
        self.library.count_season_files.return_value = 12  # have 12, torrent has 13
        self.qbt.torrent_hash_in_queue.return_value = False

        with self._patch_api(release, franchise):
            added = get_series(self.library, self.qbt, '/downloads/Anime',
                               [{'code': 'test-anime'}], None)

        assert added == ['Тест Аниме S01']
        self.qbt.download_torrent.assert_called_once()

    def test_skips_non_tv_type(self):
        release = _make_release(type_value='MOVIE')
        franchise = _make_franchise()

        with self._patch_api(release, franchise):
            added = get_series(self.library, self.qbt, '/downloads/Anime',
                               [{'code': 'test-anime'}], None)

        assert added == []
        self.qbt.download_torrent.assert_not_called()

    def test_skips_release_without_torrents(self):
        release = _make_release(torrents=None)
        release['torrents'] = []

        with self._patch_api(release, _make_franchise()):
            added = get_series(self.library, self.qbt, '/downloads/Anime',
                               [{'code': 'test-anime'}], None)

        assert added == []
        self.qbt.download_torrent.assert_not_called()

    def test_auto_tracks_and_checks_sibling_tv_seasons(self):
        release = _make_release(id=9600)
        franchise = _make_franchise(releases=[
            _make_franchise_release(9600, 1, 'test-anime-s1', type_value='TV'),
            _make_franchise_release(9839, 2, 'test-anime-s2', type_value='TV'),
            _make_franchise_release(9999, 3, 'test-anime-ova', type_value='OVA'),
        ])
        self.library.count_season_files.return_value = 0
        self.qbt.torrent_hash_in_queue.return_value = False
        self.db.save_new_anilibria_code.return_value = True

        with self._patch_api(release, franchise):
            added = get_series(self.library, self.qbt, '/downloads/Anime',
                       [{'code': 'test-anime-s1'}], None, db=self.db)

        # Should track S2 (TV) but NOT OVA
        self.db.save_new_anilibria_code.assert_called_once_with('test-anime-s2')
        # Should download both S1 and S2 immediately
        assert len(added) == 2

    def test_does_not_auto_track_self(self):
        release = _make_release(id=9600)
        franchise = _make_franchise(releases=[
            _make_franchise_release(9600, 1, 'test-anime', type_value='TV'),
        ])
        self.library.count_season_files.return_value = 12
        self.db.save_new_anilibria_code.return_value = False

        with self._patch_api(release, franchise):
            get_series(self.library, self.qbt, '/downloads/Anime',
                       [{'code': 'test-anime'}], None, db=self.db)

        self.db.save_new_anilibria_code.assert_not_called()

    def test_franchise_groups_into_same_folder(self):
        """Season 1 and season 2 should produce same base folder path."""
        # Season 1
        release_s1 = _make_release(id=9600, code='anime-s1', torrents=[
            _make_torrent(id=1, hash='h1', description='1-12'),
        ])
        franchise = _make_franchise(name='Аниме Тест', first_year=2024, releases=[
            _make_franchise_release(9600, 1, 'anime-s1'),
            _make_franchise_release(9839, 2, 'anime-s2'),
        ])
        self.library.count_season_files.return_value = 0
        self.qbt.torrent_hash_in_queue.return_value = False

        with self._patch_api(release_s1, franchise):
            get_series(self.library, self.qbt, '/dl',
                       [{'code': 'anime-s1'}], None)

        path_s1 = self.qbt.download_torrent.call_args[0][1]

        # Season 2
        self.qbt.reset_mock()
        release_s2 = _make_release(id=9839, code='anime-s2', torrents=[
            _make_torrent(id=2, hash='h2', description='1-13'),
        ])

        with self._patch_api(release_s2, franchise):
            get_series(self.library, self.qbt, '/dl',
                       [{'code': 'anime-s2'}], None)

        path_s2 = self.qbt.download_torrent.call_args[0][1]

        # Same base, different seasons
        assert path_s1 == '/dl/Аниме Тест (2024)/Season 01'
        assert path_s2 == '/dl/Аниме Тест (2024)/Season 02'

    def test_continues_on_release_api_failure(self):
        """If one code fails, the next one should still be processed."""
        good_release = _make_release(id=9600, code='good-anime',
                                     torrents=[_make_torrent(hash='h1', description='1-12')])
        franchise = _make_franchise(name='Good', first_year=2024)
        self.library.count_season_files.return_value = 0
        self.qbt.torrent_hash_in_queue.return_value = False

        call_count = [0]
        def side_effect(url, proxies=None):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception('API down')
            mock_resp = MagicMock()
            if '/anime/releases/' in url:
                mock_resp.json.return_value = good_release
            elif '/anime/franchises/' in url:
                mock_resp.json.return_value = franchise
            elif '/anime/torrents/' in url:
                mock_resp.content = b'data'
            return mock_resp

        with patch('clients.anilibria.network.get', side_effect=side_effect):
            added = get_series(self.library, self.qbt, '/dl',
                               [{'code': 'bad-anime'}, {'code': 'good-anime'}], None)

        assert added == ['Good S01']

    def test_no_db_does_not_crash(self):
        """db=None should not crash even with franchise siblings."""
        release = _make_release(id=9600)
        franchise = _make_franchise(releases=[
            _make_franchise_release(9600, 1, 'anime-s1', type_value='TV'),
            _make_franchise_release(9839, 2, 'anime-s2', type_value='TV'),
        ])
        self.library.count_season_files.return_value = 0
        self.qbt.torrent_hash_in_queue.return_value = False

        with self._patch_api(release, franchise):
            added = get_series(self.library, self.qbt, '/dl',
                               [{'code': 'anime-s1'}], None, db=None)

        assert len(added) == 1  # downloads fine without DB


# --- Library tests ---

class TestCountSeasonFiles(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        from services.library import Library
        self.library = Library(library_dir=self.tmpdir)

    def _make_season(self, show, year, season, files):
        season_dir = os.path.join(self.tmpdir, f'{show} ({year})', f'Season {season}')
        os.makedirs(season_dir, exist_ok=True)
        for f in files:
            open(os.path.join(season_dir, f), 'w').close()
        return season_dir

    def test_counts_video_files(self):
        self._make_season('Anime', 2024, '01', [
            'ep01.mkv', 'ep02.mkv', 'ep03.mp4',
        ])
        assert self.library.count_season_files('Anime', 2024, '01') == 3

    def test_ignores_non_video_files(self):
        self._make_season('Anime', 2024, '01', [
            'ep01.mkv', 'ep02.mkv', 'thumb.jpg', 'subs.srt',
        ])
        assert self.library.count_season_files('Anime', 2024, '01') == 2

    def test_empty_dir(self):
        self._make_season('Anime', 2024, '01', [])
        assert self.library.count_season_files('Anime', 2024, '01') == 0

    def test_missing_dir(self):
        assert self.library.count_season_files('NoSuch', 2024, '01') == 0

    def test_season_has_files_delegates(self):
        self._make_season('Anime', 2024, '01', ['ep01.mkv'])
        assert self.library.season_has_files('Anime', 2024, '01') is True
        assert self.library.season_has_files('Anime', 2024, '02') is False


if __name__ == '__main__':
    unittest.main()
