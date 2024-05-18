import logging
from domain import series as s
import utils
from services import network

logger = logging.getLogger(__name__)


def get_best_quality(torrents):
    torrents.sort(key=lambda x: x['downloads'], reverse=True)

    for torrent in torrents:
        if 'HEVC' not in torrent['quality']['string']:
            return torrent

    return torrents[0]


def get_titles(torrent_mirror, anime_name, proxies):
    url = torrent_mirror + '/v3/title/search?search=' + anime_name + '&limit=-1'
    res = network.get(url, proxies=proxies)
    return res.json()['list']


def get_series(db, transmission, anilibria_download_dir, torrent_mirror, api_mirror, anime_names, proxies):
    series_list = []

    for anime_name in anime_names:
        logger.info('Search anime - {}'.format(anime_name))
        titles = get_titles(api_mirror, anime_name, proxies)

        if titles is None or len(titles) == 0:
            logger.warning('Not found anilibria anime: ' + anime_name)
            break

        logger.info('Found {} anime with query {}'.format(len(titles), anime_name))

        for title in titles:
            torrents = title['torrents']
            if torrents is None or len(torrents['list']) == 0:
                logger.warning('Not found torrents for anime: ' + anime_name)
                break

            best_torrent = get_best_quality(torrents['list'])
            torrent_url = torrent_mirror + best_torrent['url']
            name = title['names']['ru'] if title['names']['ru'] else title['names']['en']

            logger.info('Produce anime with title - {}'.format(name))

            series = s.Series(torrent_url, name)
            if not utils.is_series_exist(db, series):
                transmission.send_to_transmission([series], anilibria_download_dir)
                db.insert({'name': series.name, 'url': series.torrent_url})
                series_list.append(series)

    return series_list
