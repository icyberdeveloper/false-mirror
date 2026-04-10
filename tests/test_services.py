"""Tests for services: database, library, renamer, tracker, network, qbittorrent."""
import os
import sys
import json
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))


# --- Database tests ---

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.al_path = os.path.join(self.tmpdir, 'anilibria.json')
        self.lf_path = os.path.join(self.tmpdir, 'lostfilm.json')
        from services.database import Database
        self.db = Database(self.al_path, self.lf_path)

    def test_save_and_get_anilibria(self):
        self.db.save_new_anilibria_code('test-anime')
        codes = self.db.get_anilibria_codes()
        assert len(codes) == 1
        assert codes[0]['code'] == 'test-anime'

    def test_save_and_get_lostfilm(self):
        self.db.save_new_lostfilm_code('test_show')
        codes = self.db.get_lostfilm_codes()
        assert len(codes) == 1
        assert codes[0]['code'] == 'test_show'

    def test_no_duplicates(self):
        self.db.save_new_anilibria_code('anime-1')
        self.db.save_new_anilibria_code('anime-1')
        self.db.save_new_anilibria_code('anime-1')
        assert len(self.db.get_anilibria_codes()) == 1

    def test_multiple_codes(self):
        self.db.save_new_lostfilm_code('show-1')
        self.db.save_new_lostfilm_code('show-2')
        self.db.save_new_lostfilm_code('show-3')
        assert len(self.db.get_lostfilm_codes()) == 3

    def test_empty_db(self):
        assert self.db.get_anilibria_codes() == []
        assert self.db.get_lostfilm_codes() == []


# --- Library tests ---

class TestLibrary(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.incomplete = tempfile.mkdtemp()
        from services.library import Library
        self.library = Library(library_dir=self.tmpdir, incomplete_dir=self.incomplete)

    def _make_file(self, base_dir, *path_parts):
        full_path = os.path.join(base_dir, *path_parts)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        open(full_path, 'w').close()

    def test_episode_exists_in_library(self):
        self._make_file(self.tmpdir, 'Show (2020)', 'Season 01', 'Show.S01E05.mkv')
        assert self.library.episode_exists('Show', 'Show', 2020, '01', '05') is True
        assert self.library.episode_exists('Show', 'Show', 2020, '01', '06') is False

    def test_episode_exists_in_incomplete(self):
        self._make_file(self.incomplete, 'Show.S01E05.720p.mkv')
        assert self.library.episode_exists('Show', 'Show', 2020, '01', '05') is True

    def test_episode_exists_ignores_non_video(self):
        self._make_file(self.tmpdir, 'Show (2020)', 'Season 01', 'Show.S01E05.srt')
        assert self.library.episode_exists('Show', 'Show', 2020, '01', '05') is False

    def test_count_season_files(self):
        for i in range(1, 4):
            self._make_file(self.tmpdir, 'Anime (2024)', 'Season 01', f'ep{i:02d}.mkv')
        self._make_file(self.tmpdir, 'Anime (2024)', 'Season 01', 'cover.jpg')
        assert self.library.count_season_files('Anime', 2024, '01') == 3

    def test_count_season_files_missing_dir(self):
        assert self.library.count_season_files('Nothing', 2024, '01') == 0

    def test_season_has_files(self):
        self._make_file(self.tmpdir, 'X (2024)', 'Season 01', 'ep01.mp4')
        assert self.library.season_has_files('X', 2024, '01') is True
        assert self.library.season_has_files('X', 2024, '02') is False


# --- Renamer tests ---

class TestRenamer(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        from services.renamer import Renamer
        self.renamer = Renamer(self.tmpdir)

    def _make_file(self, *path_parts):
        full_path = os.path.join(self.tmpdir, *path_parts)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        open(full_path, 'w').close()
        return full_path

    def test_renames_old_format(self):
        self._make_file('Anime (2024)', 'Season 01', 'Anime_Name_[05]_[AniLibria_TV]_[WEBRip_1080p].mkv')
        self.renamer.rename()
        assert 'Anime - S01E05.mkv' in os.listdir(os.path.join(self.tmpdir, 'Anime (2024)', 'Season 01'))

    def test_renames_new_format(self):
        self._make_file('Anime (2024)', 'Season 02', 'Anime_S2_[03].mkv')
        self.renamer.rename()
        assert 'Anime - S02E03.mkv' in os.listdir(os.path.join(self.tmpdir, 'Anime (2024)', 'Season 02'))

    def test_three_digit_episode(self):
        self._make_file('Блич (2004)', 'Season 01', 'Bleach_[001]_[AniLibria_TV]_[BDRip_1080p].mkv')
        self.renamer.rename()
        assert 'Блич - S01E01.mkv' in os.listdir(os.path.join(self.tmpdir, 'Блич (2004)', 'Season 01'))

    def test_single_digit_episode(self):
        self._make_file('OVA (2020)', 'Season 01', 'Gunsmith_Cats_[1]_[AniLibria]_[BDRip_1080p].mkv')
        self.renamer.rename()
        assert 'OVA - S01E01.mkv' in os.listdir(os.path.join(self.tmpdir, 'OVA (2020)', 'Season 01'))

    def test_russian_show_name_from_folder(self):
        s1 = os.path.join(self.tmpdir, 'Поднятие уровня (2024)', 'Season 01')
        os.makedirs(s1)
        open(os.path.join(s1, 'Ore_dake_[01]_[AniLibria_TV]_[WEBRip_1080p].mkv'), 'w').close()
        self.renamer.rename()
        assert 'Поднятие уровня - S01E01.mkv' in os.listdir(s1)

    def test_season_number_from_folder_not_filename(self):
        self._make_file('Show (2024)', 'Season 02', 'Show_S3_[01].mkv')
        self.renamer.rename()
        assert 'Show - S02E01.mkv' in os.listdir(os.path.join(self.tmpdir, 'Show (2024)', 'Season 02'))

    def test_episode_end_suffix(self):
        self._make_file('Anime (2019)', 'Season 01', 'Kimetsu_no_Yaiba_[26_END]_[AniLibria.TV]_[HDTVRip_1080p].mkv')
        self.renamer.rename()
        assert 'Anime - S01E26.mkv' in os.listdir(os.path.join(self.tmpdir, 'Anime (2019)', 'Season 01'))

    def test_hyphen_in_name(self):
        self._make_file('Ванпанчмен (2015)', 'Season 01', 'One-Punch_Man_[09]_[AniLibria_TV]_[HDTVRip_720p].mkv')
        self.renamer.rename()
        assert 'Ванпанчмен - S01E09.mkv' in os.listdir(os.path.join(self.tmpdir, 'Ванпанчмен (2015)', 'Season 01'))

    def test_dash_in_quality_brackets(self):
        self._make_file('Anime (2024)', 'Season 01', 'Dungeon_Meshi_[07]_[AniLibria]_[WEB-DLRip_1080p].mkv')
        self.renamer.rename()
        assert 'Anime - S01E07.mkv' in os.listdir(os.path.join(self.tmpdir, 'Anime (2024)', 'Season 01'))

    def test_dot_in_source_brackets(self):
        self._make_file('Anime (2019)', 'Season 01', 'Name_[01]_[AniLibria.TV]_[HDTVRip_1080p].mkv')
        self.renamer.rename()
        assert 'Anime - S01E01.mkv' in os.listdir(os.path.join(self.tmpdir, 'Anime (2019)', 'Season 01'))

    def test_space_in_name(self):
        self._make_file('Академия (2016)', 'Season 01', 'Boku_no_Hero _Academia_[09]_[AniLibria_TV]_[HDTV-Rip_720p].mkv')
        self.renamer.rename()
        assert 'Академия - S01E09.mkv' in os.listdir(os.path.join(self.tmpdir, 'Академия (2016)', 'Season 01'))

    def test_exclamation_in_name(self):
        self._make_file('Гиганты (2015)', 'Season 01', 'Shingeki!_Kyojin_Chuugakkou_[03]_[AniLibria_Tv]_[HDTV-Rip_720p].mkv')
        self.renamer.rename()
        assert 'Гиганты - S01E03.mkv' in os.listdir(os.path.join(self.tmpdir, 'Гиганты (2015)', 'Season 01'))

    def test_single_file_no_episode_is_unmatched(self):
        self._make_file('Movie (2023)', 'Season 01', 'Kuramerukagari_[AniLibria]_[WEBRip_1080p].mkv')
        unmatched = self.renamer.rename()
        assert len(unmatched) == 1

    def test_returns_unmatched_files(self):
        self._make_file('Show (2024)', 'Season 01', 'weird_name_no_brackets.mkv')
        unmatched = self.renamer.rename()
        assert len(unmatched) == 1

    def test_no_unmatched_for_plex_format(self):
        self._make_file('Show (2024)', 'Season 01', 'Show - S01E05.mkv')
        assert self.renamer.rename() == []

    def test_no_unmatched_outside_season_dirs(self):
        self._make_file('Show (2024)', 'weird_file.mkv')
        assert self.renamer.rename() == []

    def test_ignores_non_video_extensions(self):
        self._make_file('Show (2024)', 'Season 01', 'cover.jpg')
        self.renamer.rename()
        assert 'cover.jpg' in os.listdir(os.path.join(self.tmpdir, 'Show (2024)', 'Season 01'))

    def test_already_renamed_not_touched(self):
        self._make_file('Show (2024)', 'Season 01', 'Show - S01E05.mkv')
        self.renamer.rename()
        assert 'Show - S01E05.mkv' in os.listdir(os.path.join(self.tmpdir, 'Show (2024)', 'Season 01'))


class TestParseContextFromPath(unittest.TestCase):
    def test_standard_path(self):
        from services.renamer import _parse_context_from_path
        name, season = _parse_context_from_path('/library/Anime/Поднятие уровня (2024)/Season 02')
        assert name == 'Поднятие уровня'
        assert season == '02'

    def test_no_year_in_parent(self):
        from services.renamer import _parse_context_from_path
        name, season = _parse_context_from_path('/library/Anime/Some Show/Season 01')
        assert name == 'Some Show'
        assert season == '01'

    def test_no_season_folder(self):
        from services.renamer import _parse_context_from_path
        name, season = _parse_context_from_path('/library/Anime/Show (2024)/extras')
        assert season == '01'  # fallback


# --- Tracker tests ---

class TestTracker(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, 'tracker.json')
        from services.tracker import Tracker
        self.tracker = Tracker(self.db_path, tg_token='', tg_chat_id='')

    def test_record_new(self):
        self.tracker.record('Show S01E01', '/downloads/Show/Season 01')
        records = self.tracker.db.all()
        assert len(records) == 1
        assert records[0]['label'] == 'Show S01E01'
        assert records[0]['status'] == 'downloading'

    def test_record_no_duplicates(self):
        self.tracker.record('Show S01E01', '/downloads/path')
        self.tracker.record('Show S01E01', '/downloads/path')
        assert len(self.tracker.db.all()) == 1

    def test_record_different_paths(self):
        self.tracker.record('Show S01E01', '/path1')
        self.tracker.record('Show S01E01', '/path2')
        assert len(self.tracker.db.all()) == 2

    def test_check_marks_verified_on_nas(self):
        self.tracker.record('Show S01E01', '/downloads/TV Shows/Show/Season 01')

        # Create NAS file
        nas_dir = os.path.join(self.tmpdir, 'nas', 'TV Shows', 'Show', 'Season 01')
        os.makedirs(nas_dir)
        open(os.path.join(nas_dir, 'episode.mkv'), 'w').close()

        # Mock qBittorrent
        qbt_client = MagicMock()
        qbt_client.torrents.return_value = [{
            'save_path': '/downloads/TV Shows/Show/Season 01',
            'state': 'uploading',
            'progress': 1.0,
        }]

        nas_library = os.path.join(self.tmpdir, 'nas')
        self.tracker.check(qbt_client, '', qbt_download_dir='/downloads', nas_library_dir=nas_library)

        records = self.tracker.db.all()
        assert records[0]['status'] == 'verified'

    def test_check_alerts_on_problem_state(self):
        self.tracker.record('Bad S01E01', '/downloads/Bad/Season 01')
        qbt_client = MagicMock()
        qbt_client.torrents.return_value = [{
            'save_path': '/downloads/Bad/Season 01',
            'state': 'error',
            'progress': 0.5,
        }]

        with patch.object(self.tracker, '_alert') as mock_alert:
            self.tracker.check(qbt_client, '')
            mock_alert.assert_called_once()
            assert 'Bad S01E01' in mock_alert.call_args[0][0]

    def test_check_no_alert_spam(self):
        """Should alert only once per problem."""
        self.tracker.record('Bad S01E01', '/downloads/Bad/Season 01')
        qbt_client = MagicMock()
        qbt_client.torrents.return_value = [{
            'save_path': '/downloads/Bad/Season 01',
            'state': 'error',
            'progress': 0.0,
        }]

        with patch.object(self.tracker, '_alert') as mock_alert:
            self.tracker.check(qbt_client, '')
            self.tracker.check(qbt_client, '')
            assert mock_alert.call_count == 1

    def test_has_video_files(self):
        from services.tracker import Tracker
        d = tempfile.mkdtemp()
        open(os.path.join(d, 'video.mkv'), 'w').close()
        assert Tracker._has_video_files(d) is True

    def test_has_video_files_no_video(self):
        from services.tracker import Tracker
        d = tempfile.mkdtemp()
        open(os.path.join(d, 'readme.txt'), 'w').close()
        assert Tracker._has_video_files(d) is False

    def test_has_video_files_missing_dir(self):
        from services.tracker import Tracker
        assert Tracker._has_video_files('/nonexistent/path') is False


# --- Network tests ---

class TestNetwork(unittest.TestCase):
    @patch('services.network.requests.get')
    def test_returns_response_on_200(self, mock_get):
        from services.network import get
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        result = get('http://test.url')
        assert result == mock_resp

    @patch('services.network.requests.get')
    def test_raises_on_404(self, mock_get):
        from services.network import get
        import requests as req
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        with self.assertRaises(req.exceptions.RequestException):
            get('http://test.url')

    @patch('services.network.requests.get')
    def test_raises_server_error_on_500(self, mock_get):
        from services.network import get, ServerError
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        with self.assertRaises(ServerError):
            get('http://test.url')

    @patch('services.network.requests.get')
    def test_passes_cookies_and_proxies(self, mock_get):
        from services.network import get
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        get('http://test.url', cookies={'a': 'b'}, proxies={'http': 'socks5://x'})
        mock_get.assert_called_once_with(
            'http://test.url', cookies={'a': 'b'},
            proxies={'http': 'socks5://x'}, timeout=30,
        )


# --- QBittorrent tests ---

class TestQBittorrentTorrentHashInQueue(unittest.TestCase):
    def _make_qbt(self, torrents_list):
        with patch('services.qbittorrent.Client') as MockClient:
            instance = MockClient.return_value
            instance.torrents.return_value = torrents_list
            from services.qbittorrent import QBittorrent
            return QBittorrent('127.0.0.1', 8080, 'admin', 'admin')

    def test_finds_matching_hash(self):
        qbt = self._make_qbt([
            {'name': 'Anime S01', 'hash': 'abc123', 'state': 'uploading', 'save_path': '/dl', 'progress': 1.0},
        ])
        assert qbt.torrent_hash_in_queue('abc123') is True

    def test_no_match(self):
        qbt = self._make_qbt([
            {'name': 'Anime S01', 'hash': 'abc123', 'state': 'uploading', 'save_path': '/dl', 'progress': 1.0},
        ])
        assert qbt.torrent_hash_in_queue('xyz999') is False

    def test_empty_hash(self):
        qbt = self._make_qbt([])
        assert qbt.torrent_hash_in_queue('') is False

    def test_empty_queue(self):
        qbt = self._make_qbt([])
        assert qbt.torrent_hash_in_queue('abc') is False


class TestQBittorrentEpisodeInQueue(unittest.TestCase):
    def _make_qbt(self, torrents_list):
        with patch('services.qbittorrent.Client') as MockClient:
            instance = MockClient.return_value
            instance.torrents.return_value = torrents_list
            from services.qbittorrent import QBittorrent
            return QBittorrent('127.0.0.1', 8080, 'admin', 'admin')

    def test_finds_episode(self):
        qbt = self._make_qbt([
            {'name': 'The.Rookie.S03E05.720p.mkv', 'hash': 'h', 'state': 'downloading',
             'save_path': '/dl', 'progress': 0.5},
        ])
        assert qbt.episode_in_queue('The_Rookie', '03', '05') is True

    def test_no_match(self):
        qbt = self._make_qbt([
            {'name': 'The.Rookie.S03E05.720p.mkv', 'hash': 'h', 'state': 'downloading',
             'save_path': '/dl', 'progress': 0.5},
        ])
        assert qbt.episode_in_queue('The_Rookie', '03', '06') is False

    def test_wrong_show(self):
        qbt = self._make_qbt([
            {'name': 'The.Rookie.S03E05.720p.mkv', 'hash': 'h', 'state': 'downloading',
             'save_path': '/dl', 'progress': 0.5},
        ])
        assert qbt.episode_in_queue('Other_Show', '03', '05') is False


# --- Config tests ---

class TestConfig(unittest.TestCase):
    def test_from_file(self):
        from config import from_file
        cfg = from_file(os.path.join(os.path.dirname(__file__), '..', 'config.yaml'))
        assert cfg.qbittorrent.host == '127.0.0.1'
        assert cfg.qbittorrent.port == 8080
        assert cfg.qbittorrent.anime_dir == '/downloads/Anime'
        assert cfg.renamer.root_dir == '/library'
        assert cfg.anilibria.db_path == '/storage/anilibria.json'

    def test_env_overrides(self):
        with patch.dict(os.environ, {'QB_USERNAME': 'testuser', 'QB_PASSWORD': 'testpass'}):
            from config import from_file
            cfg = from_file(os.path.join(os.path.dirname(__file__), '..', 'config.yaml'))
            assert cfg.qbittorrent.username == 'testuser'
            assert cfg.qbittorrent.password == 'testpass'

    def test_proxy_disabled(self):
        from config import from_file
        cfg = from_file(os.path.join(os.path.dirname(__file__), '..', 'config.yaml'))
        assert cfg.proxy.as_dict is None
        assert cfg.proxy.url is None


# --- Bot URL parsing tests ---

class TestBotUrlParsing(unittest.TestCase):
    """Test URL regex matching from bot.cmd_download without needing telegram."""

    def test_lostfilm_series_url(self):
        import re
        url = 'https://www.lostfilm.tv/series/The_Rookie/seasons/'
        m = re.search(r'lostfilm\.\w+/series/([^/?#]+)', url)
        assert m and m.group(1) == 'The_Rookie'

    def test_lostfilm_movie_url(self):
        import re
        url = 'https://www.lostfilm.tv/movies/Some_Movie/'
        m = re.search(r'lostfilm\.\w+/movies/([^/?#]+)', url)
        assert m and m.group(1) == 'Some_Movie'

    def test_anilibria_url(self):
        import re
        url = 'https://anilibria.top/release/ore-dake-level-up-na-ken'
        m = re.search(r'anilibria\.\w+/release/([^/.?#]+)', url)
        assert m and m.group(1) == 'ore-dake-level-up-na-ken'

    def test_anilibria_url_with_query(self):
        import re
        url = 'https://anilibria.tv/release/some-anime?ref=123'
        m = re.search(r'anilibria\.\w+/release/([^/.?#]+)', url)
        assert m and m.group(1) == 'some-anime'

    def test_unknown_url(self):
        import re
        url = 'https://example.com/something'
        lf = re.search(r'lostfilm\.\w+/series/([^/?#]+)', url)
        al = re.search(r'anilibria\.\w+/release/([^/.?#]+)', url)
        assert lf is None and al is None


if __name__ == '__main__':
    unittest.main()
