from tinydb import Query
from tinydb import TinyDB


class DbController:
    def __init__(self, qbittorrent_db_path, anilibria_db_path, lostfilm_db_path):
        self.qbittorrent = TinyDB(qbittorrent_db_path)
        self.anilibria = TinyDB(anilibria_db_path)
        self.lostfilm = TinyDB(lostfilm_db_path)

    def is_series_exist(self, series):
        series_entity = Query()
        res = self.qbittorrent.search(series_entity.url == series.torrent_url)
        return len(res) != 0

    def save_series(self, series):
        self.qbittorrent.insert({
            'id': series.id,
            'url': series.torrent_url,
            'download_path': series.download_path,
            'name': series.name,
            'release_year': series.release_year,
            'season_num': series.season_num
        })

    def get_lostfilm_codes(self):
        return self.lostfilm.all()

    def get_anilibria_codes(self):
        return self.anilibria.all()

    def save_new_lostfilm_code(self, code):
        code_entity = Query()
        res = self.lostfilm.search(code_entity.code == code)
        if len(res) == 0:
            self.lostfilm.insert({'code': code})

    def save_new_anilibria_code(self, code):
        code_entity = Query()
        res = self.anilibria.search(code_entity.code == code)
        if len(res) == 0:
            self.anilibria.insert({'code': code})
