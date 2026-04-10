from tinydb import Query, TinyDB


class Database:
    def __init__(self, anilibria_db_path, lostfilm_db_path):
        self.anilibria = TinyDB(anilibria_db_path)
        self.lostfilm = TinyDB(lostfilm_db_path)

    def get_lostfilm_codes(self):
        return self.lostfilm.all()

    def get_anilibria_codes(self):
        return self.anilibria.all()

    def save_new_lostfilm_code(self, code):
        q = Query()
        if not self.lostfilm.search(q.code == code):
            self.lostfilm.insert({'code': code})

    def save_new_anilibria_code(self, code):
        q = Query()
        if not self.anilibria.search(q.code == code):
            self.anilibria.insert({'code': code})
            return True
        return False

