import yaml


class Config:
    class base:
        sleep_interval: str
        class proxy:
            enabled: bool
            host: str
            port: str
            url: str
            as_dict: dict

    class qbittorrent:
        host: str
        port: str
        username: str
        password: str
        download_dir: str
        db_path: int

    class nocron:
        token: str

    class anilibria:
        torrent_mirror: str
        api_mirror: str
        series_names: str
        db_path: str

    class lostfilm:
        torrent_mirror: str
        lf_session: str
        series_names: str
        db_path: str

    def __init__(self, cfg):
        self.base.sleep_interval = cfg['global']['interval']
        self.base.proxy.enabled = cfg['global']['proxy']['enabled']
        self.base.proxy.as_dict = None
        if self.base.proxy.enabled:
            self.base.proxy.host = cfg['global']['proxy']['host']
            self.base.proxy.port = cfg['global']['proxy']['port']
            self.base.proxy.url = 'socks5://' + self.base.proxy.host + ':' + str(self.base.proxy.port)
            self.base.proxy.as_dict = dict(http=self.base.proxy.url, https=self.base.proxy.url)

        self.qbittorrent.host = cfg['qbittorrent']['host']
        self.qbittorrent.port = cfg['qbittorrent']['port']
        self.qbittorrent.username = cfg['qbittorrent']['username']
        self.qbittorrent.password = cfg['qbittorrent']['password']
        self.qbittorrent.download_dir = cfg['qbittorrent']['download_dir']
        self.qbittorrent.db_path = cfg['qbittorrent']['db_path']

        self.nocron.token = cfg['nocronbot']['token']

        self.anilibria.torrent_mirror = cfg['anilibria']['torrent_mirrors'][0]
        self.anilibria.api_mirror = cfg['anilibria']['api_mirrors'][0]
        self.anilibria.series_names = cfg['anilibria']['series']
        self.anilibria.db_path = cfg['anilibria']['db_path']

        self.lostfilm.torrent_mirror = cfg['lostfilm']['torrent_mirrors'][0]
        self.lostfilm.lf_session = cfg['lostfilm']['lf_session']
        self.lostfilm.series_names = cfg['lostfilm']['series']
        self.lostfilm.db_path = cfg['lostfilm']['db_path']


def from_file(path):
    with open(path) as f:
        cfgd = yaml.load(f, Loader=yaml.FullLoader)
    return Config(cfgd)
