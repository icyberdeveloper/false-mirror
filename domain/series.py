class Series:
    external_id: str
    torrent_url: str
    name: str
    download_dir: str
    release_year: int
    season: str

    def __init__(self, external_id: str, torrent_url: str, download_dir: str, name: str, release_year: int, season: str):
        self.external_id = external_id
        self.torrent_url = torrent_url
        self.name = name
        self.download_dir = download_dir
        self.release_year = release_year
        self.season = season
