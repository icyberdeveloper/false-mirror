from tinydb import Query
from tinydb import TinyDB


class DbController:
    def __init__(self, db_path):
        self.core = TinyDB(db_path)

    def is_series_exist(self, series):
        series_entity = Query()
        res = self.core.search(series_entity.url == series.torrent_url)
        return len(res) != 0
