import re
import logging
from datetime import datetime
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from services import network


logger = logging.getLogger(__name__)


def get_series(library, qbittorrent, download_dir, torrent_mirror, lf_session, codes, proxies, tracker=None):
    added = []
    logger.info(f'LostFilm: processing {len(codes)} shows')

    for item in codes:
        code = item['code']
        logger.info(f'LostFilm: checking {code}')

        try:
            seasons_url = f'{torrent_mirror}/series/{code}/seasons/'
            res = network.get(seasons_url, proxies=proxies)

            series_ids = re.findall(r"PlayEpisode\('(\d+)'\)", res.text)
            series_ids = [sid for sid in series_ids if not sid.endswith('999')]
            logger.info(f'LostFilm: found {len(series_ids)} episodes for {code}')

            main_url = f'{torrent_mirror}/series/{code}'
            ru_name, release_year = _get_name_and_year(main_url, proxies)

            for series_id in series_ids:
                season_str = _get_season_number(series_id)
                episode_str = _get_episode_number(series_id)

                # Check filesystem
                if library.episode_exists(code, ru_name, release_year, season_str, episode_str):
                    continue

                # Check qBittorrent queue (skip if active, remove if broken)
                if qbittorrent.episode_in_queue(code, season_str, episode_str):
                    continue

                try:
                    redirect_url = _get_redirect_url(torrent_mirror, series_id, lf_session, proxies)
                    links = _parse_torrent_links(redirect_url, proxies)
                    if not links:
                        logger.warning(f'LostFilm: no torrent links for {code} S{season_str}E{episode_str}')
                        continue

                    # Best available quality (1080p → 720p → SD)
                    torrent_url = _pick_best_quality(links)
                    download_path = f'{download_dir}/{ru_name} ({release_year})/Season {season_str}'
                    label = f'{ru_name} S{season_str}E{episode_str}'
                    qbittorrent.download_torrent(torrent_url, download_path, proxies, tracker=tracker, label=label)
                    added.append(label)
                    logger.info(f'LostFilm: queued {ru_name} S{season_str}E{episode_str}')

                except Exception as e:
                    logger.error(f'LostFilm: error processing {code} S{season_str}E{episode_str}: {e}')

        except Exception as e:
            logger.error(f'LostFilm: error processing show {code}: {e}')

    return added


def get_movie(qbittorrent, movies_dir, torrent_mirror, lf_session, code, proxies, tracker=None):
    """Download a single movie from LostFilm."""
    logger.info(f'LostFilm movie: checking {code}')

    movie_url = f'{torrent_mirror}/movies/{code}'
    res = network.get(movie_url, proxies=proxies)

    # Get movie name
    soup = BeautifulSoup(res.text, 'html.parser')
    title_tag = soup.find('h1', {'class': 'title-ru'}) or soup.find(class_='title-ru')
    ru_name = title_tag.text.strip() if title_tag else code.replace('_', ' ')

    # Get year
    year_match = re.search(r'(\d{4})\s*г\.', res.text)
    release_year = int(year_match.group(1)) if year_match else 0

    # Get PlayEpisode ID
    series_ids = re.findall(r"PlayEpisode\('(\d+)'\)", res.text)
    if not series_ids:
        logger.warning(f'LostFilm movie: no PlayEpisode ID for {code}')
        return []

    series_id = series_ids[0]

    # Check if already downloading
    if qbittorrent.episode_in_queue(code, '01', '01'):
        logger.info(f'LostFilm movie: {code} already in queue')
        return []

    redirect_url = _get_redirect_url(torrent_mirror, series_id, lf_session, proxies)
    links = _parse_torrent_links(redirect_url, proxies)
    if not links:
        logger.warning(f'LostFilm movie: no torrent links for {code}')
        return []

    torrent_url = _pick_best_quality(links)
    folder = f'{ru_name} ({release_year})' if release_year else ru_name
    download_path = f'{movies_dir}/{folder}'
    label = f'{ru_name} ({release_year})' if release_year else ru_name
    qbittorrent.download_torrent(torrent_url, download_path, proxies, tracker=tracker, label=label)
    logger.info(f'LostFilm movie: queued {label}')
    return [label]


def _get_name_and_year(main_page_url, proxies):
    res = network.get(main_page_url, proxies=proxies)
    soup = BeautifulSoup(res.text, 'html.parser')

    title_tag = soup.find('h1', {'class': 'title-ru'})
    ru_name = title_tag.text if title_tag else 'Unknown'

    date_tag = soup.find('meta', {'itemprop': 'dateCreated'})
    if date_tag and 'content' in date_tag.attrs:
        try:
            release_year = datetime.strptime(date_tag['content'], '%Y-%m-%d').year
        except ValueError:
            release_year = 0
    else:
        release_year = 0

    return ru_name, release_year


def _get_redirect_url(torrent_mirror, series_id, lf_session, proxies):
    url = f'{torrent_mirror}/v_search.php?a={series_id}'
    cookies = {'lf_session': lf_session}
    res = network.get(url, cookies=cookies, proxies=proxies)
    soup = BeautifulSoup(res.text, 'html.parser')
    meta = soup.find('meta')
    if not meta:
        return ''
    content = meta.attrs.get('content', '')
    redirect = ''
    if 'url=' in content:
        redirect = content.split('url=', 1)[1]
    elif len(content) > 7:
        redirect = content[7:]
    # Handle relative URLs
    if redirect and redirect.startswith('/'):
        parsed = urlparse(torrent_mirror)
        redirect = f'{parsed.scheme}://{parsed.netloc}{redirect}'
    return redirect


def _parse_torrent_links(redirect_url, proxies):
    """Parse all torrent download links from quality selection page.
    Returns list of (label, url) sorted by quality: SD first, then 720p, then 1080p."""
    if not redirect_url:
        return []
    try:
        res = network.get(redirect_url, proxies=proxies)
    except Exception as e:
        logger.warning(f'LostFilm: failed to fetch quality page: {e}')
        return []

    soup = BeautifulSoup(res.text, 'html.parser')
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text().strip()
        # Only torrent download links (tracktor.site), skip external sites
        if 'tracktor' not in href:
            continue
        if not text:
            continue
        links.append((text, href))

    return links


def _pick_best_quality(links):
    """Pick highest quality: 1080p > 720p > SD."""
    for pref in ['1080p', '720p']:
        for text, href in links:
            if pref in text:
                return href
    # Fallback: first available (SD/WEB-DLRip)
    return links[0][1] if links else None




def _get_season_number(series_id):
    season = int(series_id[-6:-3])
    return f'{season:02d}'


def _get_episode_number(series_id):
    episode = int(series_id[-3:])
    return f'{episode:02d}'
