import os
import yaml


class ProxyConfig:
    def __init__(self, cfg):
        self.enabled = cfg.get('enabled', False)
        self.host = cfg.get('host', '')
        self.port = cfg.get('port', 0)
        if self.enabled and self.host and self.port:
            self.url = f'socks5://{self.host}:{self.port}'
            self.as_dict = {'http': self.url, 'https': self.url}
        else:
            self.url = None
            self.as_dict = None


class QbittorrentConfig:
    def __init__(self, cfg):
        self.host = cfg.get('host', '127.0.0.1')
        self.port = cfg.get('port', 8080)
        self.username = os.environ.get('QB_USERNAME', cfg.get('username', 'admin'))
        self.password = os.environ.get('QB_PASSWORD', cfg.get('password', 'adminadmin'))
        self.download_dir = cfg.get('download_dir', '/downloads/TV Shows')
        self.anime_dir = cfg.get('anime_dir', '/downloads/Anime')
        self.movies_dir = cfg.get('movies_dir', '/downloads/Movies')
        self.incomplete_dir = cfg.get('incomplete_dir', '')


class AnilibriaConfig:
    def __init__(self, cfg):
        self.torrent_mirror = cfg.get('torrent_mirror', 'https://www.anilibria.tv')
        self.api_mirror = cfg.get('api_mirror', 'https://api.anilibria.tv')
        self.db_path = cfg.get('db_path', '/storage/anilibria.json')


class LostfilmConfig:
    def __init__(self, cfg):
        self.lf_session = os.environ.get('LF_SESSION', cfg.get('lf_session', ''))
        self.torrent_mirror = cfg.get('torrent_mirror', 'https://www.lostfilm.tv')
        self.db_path = cfg.get('db_path', '/storage/lostfilm.json')


class RenamerConfig:
    def __init__(self, cfg):
        self.root_dir = cfg.get('root_dir', '/library')
        anilibria = cfg.get('anilibria', {})
        self.anilibria_regex = anilibria.get('regex', '')


class NocronConfig:
    def __init__(self, cfg):
        self.token = os.environ.get('TG_BOT_TOKEN', cfg.get('token', ''))


class Config:
    def __init__(self, cfg):
        global_cfg = cfg.get('global', {})
        self.proxy = ProxyConfig(global_cfg.get('proxy', {}))
        self.qbittorrent = QbittorrentConfig(cfg.get('qbittorrent', {}))
        self.anilibria = AnilibriaConfig(cfg.get('anilibria', {}))
        self.lostfilm = LostfilmConfig(cfg.get('lostfilm', {}))
        self.renamer = RenamerConfig(cfg.get('renamer', {}))
        self.nocron = NocronConfig(cfg.get('nocronbot', {}))


def from_file(path):
    with open(path) as f:
        cfg = yaml.safe_load(f)
    return Config(cfg)
