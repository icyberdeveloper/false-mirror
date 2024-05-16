import asyncio
import logging
from anilibria import AniLibriaClient
import series as s
import utils


logger = logging.getLogger(__name__)


def get_best_quality(torrents):
    torrents.sort(key=lambda x: x.downloads, reverse=True)

    for torrent in torrents:
        if 'HEVC' not in torrent.quality.string:
            return torrent

    return torrents[0]


def get_series(db, torrent_mirror, anime_names):
    client = AniLibriaClient()
    series_list = []

    for anime_name in anime_names:
        logger.info('Search anime - {}'.format(anime_name))
        titles = asyncio.run(client.search_titles(search=anime_name))

        if titles is None or len(titles) == 0:
            logger.warning('Not found anilibria anime: ' + anime_name)
            break

        logger.info('Found {} anime with query {}'.format(len(titles), anime_name))

        for title in titles:
            torrents = title.torrents
            if torrents is None or len(torrents.list) == 0:
                logger.warning('Not found torrents for anime: ' + anime_name)
                break

            best_torrent = get_best_quality(torrents.list)
            torrent_url = torrent_mirror + best_torrent.url
            name = title.names.ru if title.names.ru else title.names.en

            logger.info('Produce anime with title - {}'.format(name))

            series = s.Series(torrent_url, name)
            series_list.append(series)

    asyncio.run(client.close())

    return utils.filter_torrents_if_exists(db, series_list)
