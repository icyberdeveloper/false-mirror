class Series:
    torrent_url: str
    name: str

    def __init__(self, torrent_url: str, name: str):
        self.torrent_url = torrent_url
        self.name = name