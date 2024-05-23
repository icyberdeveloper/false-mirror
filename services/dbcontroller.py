from tinydb import Query
from tinydb import TinyDB


class DbController:
    def __init__(self, qbittorrent_db_path, anilibria_db_path, lostfilm_db_path):
        self.qbittorrent = TinyDB(qbittorrent_db_path)
        self.anilibria = TinyDB(anilibria_db_path)
        self.lostfilm = TinyDB(lostfilm_db_path)

    def is_series_exist(self, series):
        series_entity = Query()
        res = self.qbittorrent.search(series_entity.torrent_url == series.torrent_url)
        return len(res) != 0

    def save_series(self, series):
        self.qbittorrent.insert({
            'external_id': series.external_id,
            'code': series.code,
            'torrent_url': series.torrent_url,
            'name': series.name,
            'download_path': series.download_path,
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
