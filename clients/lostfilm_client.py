from bs4 import BeautifulSoup
import logging
import re
from datetime import datetime

from domain import series as s
from services import network

logger = logging.getLogger(__name__)


def get_series(db, qbittorent_client, download_dir, torrent_mirror, lostfilm_lf_session, series_names, proxies):
    series_list = []

    logger.info('Start update {} shows'.format(len(series_names)))
    for series_name in series_names:
        logger.info('Search show - {}'.format(series_name))
        seasons_url = torrent_mirror + '/series/' + series_name + '/seasons/'
        res = network.get(seasons_url, proxies=proxies)

        series_ids = re.findall(r"PlayEpisode\('(\d+)'\)", res.text)
        series_ids = drop_seasons_id(series_ids)

        logger.info('Found {} series with show name {}'.format(len(series_ids), series_name))

        main_page_url = torrent_mirror + '/series/' + series_name
        ru_name, release_date = get_original_name_and_release_date(main_page_url, proxies)
        release_year = datetime.strptime(release_date, '%Y-%m-%d').date().year

        for series_id in series_ids:
            logger.info('Produce show with id - {}'.format(series_id))

            redirect_url = get_redirect_url(torrent_mirror, series_id, lostfilm_lf_session, proxies)
            torrent_url = get_torrent_url(redirect_url, proxies)

            series = s.Series(torrent_url, ru_name)

            if not db.is_series_exist(series):
                season_str = get_season_number(series_id)
                download_path = '{0}/{1} ({2})/Season {3}'.format(
                    download_dir, series_name, release_year, season_str
                )

                qbittorent_client.send_to_qbittorent([series], download_path, proxies)
                db.core.insert({'name': series.name, 'url': series.torrent_url})
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


def get_redirect_url(torrent_mirror, series_id, lostfilm_lf_session, proxies):
    torrent_page = torrent_mirror + '/v_search.php?a=' + series_id
    cookies = {'lf_session': lostfilm_lf_session}
    res = network.get(torrent_page, cookies=cookies, proxies=proxies)
    soup = BeautifulSoup(res.text, 'html.parser')
    redirect_url = soup.find('a').attrs['href']

    return redirect_url


def get_torrent_url(redirect_url, proxies):
    res = network.get(redirect_url, proxies=proxies)
    soup = BeautifulSoup(res.text, 'html.parser')
    torrent_url = soup.find(tag_with_1080p_link).attrs['href']

    return torrent_url


def get_original_name_and_release_date(main_page_url, proxies):
    res = network.get(main_page_url, proxies=proxies)
    soup = BeautifulSoup(res.text, 'html.parser')
    ru_name = soup.find('h1', {'class': 'title-ru'}).text
    release_date = soup.find('meta', {'itemprop': 'dateCreated'}).attrs['content']

    return ru_name, release_date


def get_season_number(id):
    tmp = id[-6:]
    season = tmp[:3]
    if season.startswith('0'):
        season = season[-2:]

    return season
