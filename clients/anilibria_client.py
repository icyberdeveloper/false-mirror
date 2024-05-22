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


def get_title(torrent_mirror, code, proxies):
    url = torrent_mirror + '/v3/title?code=' + code
    res = network.get(url, proxies=proxies)
    return res.json()


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


def get_series(db, qbittorent_client, download_dir, torrent_mirror, api_mirror, anilibria_codes, proxies):
    series_list = []

    logger.info('Start update {} shows'.format(len(anilibria_codes)))
    for anilibria_code_item in anilibria_codes:
        anilibria_code = anilibria_code_item['code']
        logger.info('GET anime - {}'.format(anilibria_code))
        title = get_title(api_mirror, anilibria_code, proxies)

        if title is None or 'code' not in title:
            logger.warning('Not found anilibria anime with code: ' + anilibria_code)
            continue

        if title['type']['code'] != 1:  # only TV Shows
            logger.warning('Skip not TV Show type for : ' + anilibria_code)
            continue

        torrents = title['torrents']
        if torrents is None or len(torrents['list']) == 0:
            logger.warning('Not found torrents for anime: ' + anilibria_code)
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

        logger.info('Process anime with title - {}'.format(name))

        series = s.Series(id, code, torrent_url, download_path, name, release_year, season_num)
        if not db.is_series_exist(series):
            qbittorent_client.send_to_qbittorent([series], proxies)
            db.save_series(series)
            series_list.append(series)

    return series_list
