import re
import logging

from services import network


logger = logging.getLogger(__name__)

API_BASE = 'https://anilibria.top/api/v1'


def get_series(library, qbittorrent, download_dir, codes, proxies, tracker=None, db=None):
    """Check a single release for new episodes. If it belongs to a franchise,
    auto-register any unknown sibling seasons in the DB (they'll get their own
    scheduler slot on the next cycle)."""
    added = []
    new_siblings = []
    logger.info(f'Anilibria: processing {len(codes)} shows')

    for item in codes:
        code = item['code']
        logger.info(f'Anilibria: checking {code}')

        try:
            try:
                release = _get_release(code, proxies)
            except Exception:
                logger.warning(f'Anilibria: not found or unavailable: {code}')
                continue

            if release.get('type', {}).get('value') != 'TV':
                logger.warning(f'Anilibria: skipping non-TV type: {code}')
                continue

            torrents = release.get('torrents')
            if not torrents:
                logger.warning(f'Anilibria: no torrents for: {code}')
                continue

            # Get franchise info for proper season grouping
            release_id = release['id']
            franchise_name, season_num, base_year, all_releases = _get_franchise_info(release_id, release, proxies)

            # Auto-track sibling TV seasons from franchise
            if db and all_releases:
                for fr in all_releases:
                    rel = fr.get('release', {})
                    sibling_alias = rel.get('alias')
                    sibling_type = rel.get('type', {}).get('value')
                    if sibling_alias and sibling_alias != code and sibling_type == 'TV':
                        if db.save_new_anilibria_code(sibling_alias):
                            new_siblings.append(sibling_alias)

            # Check only THIS release
            best = _get_best_quality(torrents)
            torrent_episodes = _parse_episode_count(best.get('description', ''))
            disk_count = library.count_season_files(franchise_name, base_year, season_num)

            if disk_count >= torrent_episodes and torrent_episodes > 0:
                logger.info(f'Anilibria: {franchise_name} S{season_num} up to date ({disk_count}/{torrent_episodes} episodes)')
                continue

            if qbittorrent.torrent_hash_in_queue(best.get('hash', '')):
                logger.info(f'Anilibria: {franchise_name} S{season_num} torrent already in queue')
                continue

            torrent_url = f'{API_BASE}/anime/torrents/{best["id"]}/file'
            download_path = f'{download_dir}/{franchise_name} ({base_year})/Season {season_num}'
            label = f'{franchise_name} S{season_num}'

            if disk_count > 0:
                logger.info(f'Anilibria: {franchise_name} S{season_num} has {disk_count} eps, torrent has {torrent_episodes} — updating')

            qbittorrent.download_torrent(torrent_url, download_path, proxies, tracker=tracker, label=label)
            added.append(label)
            logger.info(f'Anilibria: queued {label}')

        except Exception as e:
            logger.error(f'Anilibria: error processing {code}: {e}')

    # Immediately check newly discovered sibling seasons
    if new_siblings:
        logger.info(f'Anilibria: checking {len(new_siblings)} new sibling seasons')
        sibling_added = get_series(
            library, qbittorrent, download_dir,
            [{'code': s} for s in new_siblings], proxies,
            tracker=tracker, db=None,  # db=None to avoid infinite recursion
        )
        added.extend(sibling_added)

    return added


def _get_release(code, proxies):
    url = f'{API_BASE}/anime/releases/{code}'
    res = network.get(url, proxies=proxies)
    return res.json()


def _get_franchise_info(release_id, release, proxies):
    """Get franchise name, season number, base year, and all franchise releases.

    Returns (name, season_num_str, year, franchise_releases_list_or_None).
    """
    fallback_name = release.get('name', {}).get('main') or release.get('name', {}).get('english') or 'Unknown'
    fallback_year = release.get('year', 0)

    try:
        url = f'{API_BASE}/anime/franchises/release/{release_id}'
        res = network.get(url, proxies=proxies)
        franchises = res.json()

        if not franchises:
            return fallback_name, '01', fallback_year, None

        franchise = franchises[0]
        franchise_name = franchise.get('name') or fallback_name
        base_year = franchise.get('first_year') or fallback_year

        all_releases = franchise.get('franchise_releases', [])

        season_num = 1
        for fr in all_releases:
            if fr.get('release_id') == release_id:
                season_num = fr.get('sort_order', 1)
                break

        return franchise_name, f'{season_num:02d}', base_year, all_releases

    except Exception as e:
        logger.warning(f'Anilibria: could not fetch franchise for release {release_id}: {e}')
        return fallback_name, '01', fallback_year, None


def _get_best_quality(torrents):
    torrents.sort(key=lambda x: x.get('seeders', 0), reverse=True)
    for t in torrents:
        codec = t.get('codec', {}).get('label', '')
        if 'HEVC' not in codec:
            return t
    return torrents[0]


def _parse_episode_count(desc):
    """Parse torrent description like '1-12' or '1' to get episode count."""
    if not desc:
        return 0
    m = re.search(r'(\d+)\s*-\s*(\d+)', desc)
    if m:
        return int(m.group(2)) - int(m.group(1)) + 1
    m = re.search(r'^(\d+)$', desc.strip())
    if m:
        return 1
    return 0
