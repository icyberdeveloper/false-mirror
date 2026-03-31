import logging

from services import network


logger = logging.getLogger(__name__)


def get_series(library, qbittorrent, download_dir, torrent_mirror, api_mirror, codes, proxies, tracker=None):
    added = []
    logger.info(f'Anilibria: processing {len(codes)} shows')

    for item in codes:
        code = item['code']
        logger.info(f'Anilibria: checking {code}')

        try:
            title = _get_title(api_mirror, code, proxies)
            if not title or 'code' not in title:
                logger.warning(f'Anilibria: not found: {code}')
                continue

            if title.get('type', {}).get('code') != 1:
                logger.warning(f'Anilibria: skipping non-TV type: {code}')
                continue

            torrents = title.get('torrents')
            if not torrents or not torrents.get('list'):
                logger.warning(f'Anilibria: no torrents for: {code}')
                continue

            name = _get_name(title)
            release_year = _get_release_year(title)
            season_num = _get_season_number(title)

            # Check filesystem instead of database
            if library.season_has_files(name, release_year, season_num):
                logger.info(f'Anilibria: already have files for {name} S{season_num}, skipping')
                continue

            best = _get_best_quality(torrents['list'])
            torrent_url = torrent_mirror + best['url']
            download_path = f'{download_dir}/{name} ({release_year})/Season {season_num}'

            label = f'{name} S{season_num}'
            qbittorrent.download_torrent(torrent_url, download_path, proxies, tracker=tracker, label=label)
            added.append(label)
            logger.info(f'Anilibria: queued {name} S{season_num}')

        except Exception as e:
            logger.error(f'Anilibria: error processing {code}: {e}')

    return added


def _get_title(api_mirror, code, proxies):
    url = f'{api_mirror}/v3/title?code={code}'
    res = network.get(url, proxies=proxies)
    return res.json()


def _get_best_quality(torrents):
    torrents.sort(key=lambda x: x.get('downloads', 0), reverse=True)
    for t in torrents:
        quality = t.get('quality', {}).get('string', '')
        if 'HEVC' not in quality:
            return t
    return torrents[0]


def _get_name(title):
    if title.get('franchises'):
        franchise_name = title['franchises'][0].get('franchise', {}).get('name')
        if franchise_name:
            return franchise_name
    names = title.get('names', {})
    return names.get('ru') or names.get('en') or 'Unknown'


def _get_release_year(title):
    season = title.get('season')
    if season and season.get('year'):
        return season['year']
    return 0


def _get_season_number(title):
    if title.get('franchises'):
        code = title['code']
        releases = title['franchises'][0].get('releases', [])
        for release in releases:
            if release.get('code') == code:
                ordinal = release.get('ordinal', 1)
                return f'{ordinal:02d}'
    return '01'
