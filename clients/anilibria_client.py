import logging
from domain import series as s
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


def is_franchise(title):
    return len(title['franchises']) > 0


def get_name(title):
    if is_franchise(title):
        return title['franchises'][0]['franchise']['name']

    return title['names']['ru'] if title['names']['ru'] else title['names']['en']


def get_release_year(title):
    return title['season']['year'] if title['season']['year'] else 0


def get_season_number(title):
    if is_franchise(title):
        code = title['code']
        releases = title['franchises'][0]['releases']
        for release in releases:
            if release['code'] == code:
                ordinal = release['ordinal']
                return '0' + str(ordinal) if ordinal < 10 else str(ordinal)
    return '01'


def get_series(db, qbittorent_client, download_dir, torrent_mirror, api_mirror, anime_names, proxies):
    series_list = []

    for anime_name in anime_names:
        logger.info('Search anime - {}'.format(anime_name))
        titles = get_titles(api_mirror, anime_name, proxies)

        if titles is None or len(titles) == 0:
            logger.warning('Not found anilibria anime: ' + anime_name)
            continue

        logger.info('Found {} anime with query {}'.format(len(titles), anime_name))

        for title in titles:
            if title['type']['code'] != 1:  # only TV Shows
                logger.warning('Skip not TV Show type for : ' + anime_name)
                continue

            torrents = title['torrents']
            if torrents is None or len(torrents['list']) == 0:
                logger.warning('Not found torrents for anime: ' + anime_name)
                continue

            id = title['id']
            code = title['code']
            best_torrent = get_best_quality(torrents['list'])
            torrent_url = torrent_mirror + best_torrent['url']
            name = get_name(title)
            release_year = get_release_year(title)
            season_num = get_season_number(title)
            download_path = '{0}/{1} ({2})/Season {3}'.format(
                download_dir, name, release_year, season_num
            )

            logger.info('Produce anime with title - {}'.format(name))

            series = s.Series(id, code, torrent_url, download_path, name, release_year, season_num)
            if not db.is_series_exist(series):
                qbittorent_client.send_to_qbittorent([series], proxies)
                db.save_series(series)
                series_list.append(series)

    return series_list
