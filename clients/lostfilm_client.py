from bs4 import BeautifulSoup
import logging
import re

import utils
from domain import series as s
from services import network

logger = logging.getLogger(__name__)


def get_series(db, transmission, lostfilm_download_dir, torrent_mirror, lostfilm_lf_session, series_names, proxies):
    series_list = []

    logger.info('Start update {} shows'.format(len(series_names)))
    for series_name in series_names:
        logger.info('Search show - {}'.format(series_name))
        full_url = torrent_mirror + '/series/' + series_name + '/seasons/'
        res = network.get(full_url, proxies=proxies)

        series_ids = re.findall(r"PlayEpisode\('(\d+)'\)", res.text)
        series_ids = drop_seasons_id(series_ids)

        logger.info('Found {} series with show name {}'.format(len(series_ids), series_name))

        for series_id in series_ids:
            logger.info('Produce show with id - {}'.format(series_id))
            torrent_page = torrent_mirror + '/v_search.php?a=' + series_id
            cookies = {'lf_session': lostfilm_lf_session}
            res = network.get(torrent_page, cookies=cookies, proxies=proxies)
            soup = BeautifulSoup(res.text, "html.parser")
            reddirect_url = soup.find('a').attrs['href']

            res = network.get(reddirect_url, proxies=proxies)
            soup = BeautifulSoup(res.text, "html.parser")
            torrent_url = soup.find(tag_with_1080p_link).attrs['href']

            series = s.Series(torrent_url, series_id)

            if not utils.is_series_exist(db, series):
                download_path = lostfilm_download_dir + '/' + series_name
                transmission.send_to_transmission([series], download_path, proxies)
                db.insert({'name': series.name, 'url': series.torrent_url})
                series_list.append(series)

    return series_list


def drop_seasons_id(series_ids):
    series_id_wo_seasons_id = []

    for series_id in series_ids:
        if not series_id.endswith('999'):
            series_id_wo_seasons_id.append(series_id)

    return series_id_wo_seasons_id


def tag_with_1080p_link(tag):
    return tag.name == 'a' and tag.has_attr('href') and '1080p' in tag.text