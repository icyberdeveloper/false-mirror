class Series:
    external_id: str
    code: str
    torrent_url: str
    name: str
    download_path: str
    release_year: int
    season_num: str

    def __init__(self, external_id: str, code: str, torrent_url: str, download_path: str, name: str, release_year: int, season_num: str):
        self.external_id = external_id
        self.code = code
        self.torrent_url = torrent_url
        self.name = name
        self.download_path = download_path
        self.release_year = release_year
        self.season_num = season_num
