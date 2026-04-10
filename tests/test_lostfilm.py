"""Tests for LostFilm client — episode parsing, quality selection, series/movie download logic."""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from clients.lostfilm import (
    get_series, get_movie,
    _get_season_number, _get_episode_number,
    _pick_best_quality, _parse_torrent_links, _get_redirect_url,
    _get_name_and_year,
)


# --- Pure function tests ---

class TestGetSeasonNumber(unittest.TestCase):
    def test_normal(self):
        # series_id format: XXXX[SSS][EEE] — last 6 digits are season+episode
        assert _get_season_number('123001005') == '01'  # season 1
        assert _get_season_number('123012003') == '12'  # season 12

    def test_short_id(self):
        assert _get_season_number('12345') == '01'

    def test_non_numeric(self):
        assert _get_season_number('abc') == '01'


class TestGetEpisodeNumber(unittest.TestCase):
    def test_normal(self):
        assert _get_episode_number('123001005') == '05'
        assert _get_episode_number('123001012') == '12'

    def test_short_id(self):
        assert _get_episode_number('12') == '01'


class TestPickBestQuality(unittest.TestCase):
    def test_prefers_1080p(self):
        links = [
            ('SD (480p)', 'http://sd.torrent'),
            ('MP4 (720p)', 'http://720.torrent'),
            ('MP4 (1080p)', 'http://1080.torrent'),
        ]
        assert _pick_best_quality(links) == 'http://1080.torrent'

    def test_falls_back_to_720p(self):
        links = [
            ('SD (480p)', 'http://sd.torrent'),
            ('MP4 (720p)', 'http://720.torrent'),
        ]
        assert _pick_best_quality(links) == 'http://720.torrent'

    def test_falls_back_to_first(self):
        links = [
            ('SD (480p)', 'http://sd.torrent'),
        ]
        assert _pick_best_quality(links) == 'http://sd.torrent'

    def test_empty_returns_none(self):
        assert _pick_best_quality([]) is None


class TestParseTorrentLinks(unittest.TestCase):
    @patch('clients.lostfilm.network.get')
    def test_extracts_tracktor_links(self, mock_get):
        mock_get.return_value = MagicMock(text='''
            <html><body>
            <a href="https://tracktor.site/td.php?s=1080p">MP4 (1080p)</a>
            <a href="https://tracktor.site/td.php?s=720p">MP4 (720p)</a>
            <a href="https://other.site/nope">Other</a>
            </body></html>
        ''')
        links = _parse_torrent_links('http://redirect.url', None)
        assert len(links) == 2
        assert links[0][0] == 'MP4 (1080p)'
        assert 'tracktor' in links[0][1]

    @patch('clients.lostfilm.network.get')
    def test_empty_redirect_url(self, mock_get):
        links = _parse_torrent_links('', None)
        assert links == []
        mock_get.assert_not_called()

    @patch('clients.lostfilm.network.get')
    def test_network_failure(self, mock_get):
        mock_get.side_effect = Exception('timeout')
        links = _parse_torrent_links('http://some.url', None)
        assert links == []


class TestGetRedirectUrl(unittest.TestCase):
    @patch('clients.lostfilm.network.get')
    def test_extracts_url_from_meta(self, mock_get):
        mock_get.return_value = MagicMock(text='''
            <html><head>
            <meta http-equiv="refresh" content="0; url=https://tracktor.site/dl?id=123">
            </head></html>
        ''')
        url = _get_redirect_url('https://www.lostfilm.tv', '123456', 'session', None)
        assert url == 'https://tracktor.site/dl?id=123'

    @patch('clients.lostfilm.network.get')
    def test_handles_relative_url(self, mock_get):
        mock_get.return_value = MagicMock(text='''
            <html><head>
            <meta http-equiv="refresh" content="0; url=/redirect/path">
            </head></html>
        ''')
        url = _get_redirect_url('https://www.lostfilm.tv', '123', 'session', None)
        assert url == 'https://www.lostfilm.tv/redirect/path'

    @patch('clients.lostfilm.network.get')
    def test_no_meta_tag(self, mock_get):
        mock_get.return_value = MagicMock(text='<html><head></head></html>')
        url = _get_redirect_url('https://www.lostfilm.tv', '123', 'session', None)
        assert url == ''


class TestGetNameAndYear(unittest.TestCase):
    @patch('clients.lostfilm.network.get')
    def test_extracts_name_and_year(self, mock_get):
        mock_get.return_value = MagicMock(text='''
            <html><body>
            <h1 class="title-ru">Захват</h1>
            <meta itemprop="dateCreated" content="2019-09-10">
            </body></html>
        ''')
        name, year = _get_name_and_year('http://test.url', None)
        assert name == 'Захват'
        assert year == 2019

    @patch('clients.lostfilm.network.get')
    def test_missing_name_and_year(self, mock_get):
        mock_get.return_value = MagicMock(text='<html><body></body></html>')
        name, year = _get_name_and_year('http://test.url', None)
        assert name == 'Unknown'
        assert year == 0


# --- get_series integration tests ---

class TestGetSeries(unittest.TestCase):
    def setUp(self):
        self.library = MagicMock()
        self.qbt = MagicMock()
        self.tracker = MagicMock()

    @patch('clients.lostfilm.network.get')
    @patch('clients.lostfilm._get_redirect_url')
    @patch('clients.lostfilm._parse_torrent_links')
    def test_downloads_new_episode(self, mock_links, mock_redirect, mock_get):
        # Seasons page with one episode
        mock_get.return_value = MagicMock(text='''
            <html><body>
            <h1 class="title-ru">Тест Шоу</h1>
            <meta itemprop="dateCreated" content="2020-01-15">
            PlayEpisode('123001005')
            </body></html>
        ''')
        self.library.episode_exists.return_value = False
        self.qbt.episode_in_queue.return_value = False
        mock_redirect.return_value = 'http://redirect.url'
        mock_links.return_value = [('MP4 (1080p)', 'http://torrent.url')]

        added = get_series(
            self.library, self.qbt, '/downloads/TV Shows',
            'https://www.lostfilm.tv', 'session',
            [{'code': 'test_show'}], None, tracker=self.tracker,
        )

        assert len(added) == 1
        self.qbt.download_torrent.assert_called_once()

    @patch('clients.lostfilm.network.get')
    def test_skips_existing_episode(self, mock_get):
        mock_get.return_value = MagicMock(text='''
            <html><body>
            <h1 class="title-ru">Тест</h1>
            <meta itemprop="dateCreated" content="2020-01-01">
            PlayEpisode('123001005')
            </body></html>
        ''')
        self.library.episode_exists.return_value = True

        added = get_series(
            self.library, self.qbt, '/downloads',
            'https://www.lostfilm.tv', 'session',
            [{'code': 'test'}], None,
        )

        assert added == []
        self.qbt.download_torrent.assert_not_called()

    @patch('clients.lostfilm.network.get')
    def test_skips_episode_in_queue(self, mock_get):
        mock_get.return_value = MagicMock(text='''
            <html><body>
            <h1 class="title-ru">Тест</h1>
            <meta itemprop="dateCreated" content="2020-01-01">
            PlayEpisode('123001005')
            </body></html>
        ''')
        self.library.episode_exists.return_value = False
        self.qbt.episode_in_queue.return_value = True

        added = get_series(
            self.library, self.qbt, '/downloads',
            'https://www.lostfilm.tv', 'session',
            [{'code': 'test'}], None,
        )

        assert added == []
        self.qbt.download_torrent.assert_not_called()

    @patch('clients.lostfilm.network.get')
    def test_filters_out_999_ids(self, mock_get):
        """series_ids ending with 999 are special (full season packs) and should be skipped."""
        mock_get.return_value = MagicMock(text='''
            <html><body>
            <h1 class="title-ru">Тест</h1>
            <meta itemprop="dateCreated" content="2020-01-01">
            PlayEpisode('123001999')
            PlayEpisode('123001005')
            </body></html>
        ''')
        self.library.episode_exists.return_value = True  # skip actual downloads

        get_series(
            self.library, self.qbt, '/downloads',
            'https://www.lostfilm.tv', 'session',
            [{'code': 'test'}], None,
        )

        # episode_exists should only be called for the non-999 episode
        assert self.library.episode_exists.call_count == 1


# --- get_movie tests ---

class TestGetMovie(unittest.TestCase):
    @patch('clients.lostfilm._parse_torrent_links')
    @patch('clients.lostfilm._get_redirect_url')
    @patch('clients.lostfilm.network.get')
    def test_downloads_movie(self, mock_get, mock_redirect, mock_links):
        mock_get.return_value = MagicMock(text='''
            <html><body>
            <h1 class="title-ru">Тест Фильм</h1>
            2023 г.
            PlayEpisode('999001001')
            </body></html>
        ''')
        mock_redirect.return_value = 'http://redirect'
        mock_links.return_value = [('1080p', 'http://torrent')]
        qbt = MagicMock()
        qbt.episode_in_queue.return_value = False

        added = get_movie(
            qbt, '/downloads/Movies',
            'https://www.lostfilm.tv', 'session',
            'test_movie', None,
        )

        assert added == ['Тест Фильм (2023)']
        qbt.download_torrent.assert_called_once()
        path = qbt.download_torrent.call_args[0][1]
        assert path == '/downloads/Movies/Тест Фильм (2023)'

    @patch('clients.lostfilm.network.get')
    def test_movie_already_in_queue(self, mock_get):
        mock_get.return_value = MagicMock(text='''
            <html><body>
            <h1 class="title-ru">Фильм</h1>
            PlayEpisode('999001001')
            </body></html>
        ''')
        qbt = MagicMock()
        qbt.episode_in_queue.return_value = True

        added = get_movie(
            qbt, '/downloads/Movies',
            'https://www.lostfilm.tv', 'session',
            'test', None,
        )

        assert added == []

    @patch('clients.lostfilm.network.get')
    def test_movie_no_play_episode(self, mock_get):
        mock_get.return_value = MagicMock(text='<html><body>No episodes</body></html>')
        qbt = MagicMock()

        added = get_movie(
            qbt, '/downloads/Movies',
            'https://www.lostfilm.tv', 'session',
            'test', None,
        )

        assert added == []


if __name__ == '__main__':
    unittest.main()
