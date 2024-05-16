from bs4 import BeautifulSoup
import requests
import logging
import re

import utils
import series as s


logger = logging.getLogger(__name__)


def get_series(db, torrent_mirror, lostfilm_lf_session, series_names):
    series_list = []
    for series_name in series_names:
        logger.info('Search show - {}'.format(series_name))
        full_url = torrent_mirror + '/series/' + series_name + '/seasons/'
        res = requests.get(full_url)

        series_ids = re.findall(r"PlayEpisode\('(\d+)'\)", res.text)
        series_ids = drop_seasons_id(series_ids)

        logger.info('Found {} series with show name {}'.format(len(series_ids), series_name))

        for series_id in series_ids:
            logger.info('Produce show with id - {}'.format(series_id))
            torrent_page = torrent_mirror + '/v_search.php?a=' + series_id
            cookies = {'lf_session': lostfilm_lf_session}
            res = requests.get(torrent_page, cookies=cookies)
            soup = BeautifulSoup(res.text, "html.parser")
            reddirect_url  = soup.find('a').attrs['href']

            res = requests.get(reddirect_url)
            soup = BeautifulSoup(res.text, "html.parser")
            torrent_url = soup.find(tag_with_1080p_link).attrs['href']

            series = s.Series(torrent_url, series_id)
            series_list.append(series)

        return utils.filter_torrents_if_exists(db, series_list)


def drop_seasons_id(series_ids):
    series_id_wo_seasons_id = []

    for series_id in series_ids:
        if not series_id.endswith('999'):
            series_id_wo_seasons_id.append(series_id)

    return series_id_wo_seasons_id


def tag_with_1080p_link(tag):
    return tag.name == 'a' and tag.has_attr('href') and '1080p' in tag.text