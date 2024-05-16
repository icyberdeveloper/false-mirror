from tinydb import Query


def filter_torrents_if_exists(db, series_list):
    filtered_series = []

    for series in series_list:
        series_entity = Query()
        res = db.search(series_entity.url == series.torrent_url)
        if len(res) == 0:
            filtered_series.append(series)

    return filtered_series
