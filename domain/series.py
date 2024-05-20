class Series:
    torrent_url: str
    name: str
    download_dir: str
    release_year: int
    season: str

    def __init__(self, torrent_url: str, download_dir: str, name: str, release_year: int, season: str):
        self.torrent_url = torrent_url
        self.name = name
        self.download_dir = download_dir
        self.release_year = release_year
        self.season = season
