import os
import re
import logging


logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {'.mkv', '.avi', '.mp4', '.ts', '.m4v'}
PLEX_PATTERN = re.compile(r'.+ - S\d{2}E\d+\.\w+$')
EPISODE_PATTERN = re.compile(r'\[(\d+)(?:_\w+)?\]')


class Renamer:
    def __init__(self, root_dir, anilibria_regex=None):
        self.root_dir = root_dir

    def rename(self):
        logger.info(f'Renamer walking: {self.root_dir}')
        unmatched = []

        for dirpath, dirs, files in os.walk(self.root_dir):
            if not re.match(r'Season\s+\d+', os.path.basename(dirpath)):
                continue

            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in VIDEO_EXTENSIONS:
                    continue

                if PLEX_PATTERN.match(filename):
                    continue

                episode = _extract_episode(filename)
                if episode is None:
                    unmatched.append(os.path.join(dirpath, filename))
                    logger.warning(f'Renamer: unrecognized file: {os.path.join(dirpath, filename)}')
                    continue

                show_name, season_num = _parse_context_from_path(dirpath)
                new_filename = f'{show_name} - S{season_num}E{episode:02d}{ext}'

                if new_filename == filename:
                    continue

                old_path = os.path.join(dirpath, filename)
                new_path = os.path.join(dirpath, new_filename)
                logger.info(f'Renaming: {filename} -> {new_filename}')
                os.rename(old_path, new_path)

        return unmatched


def _extract_episode(filename):
    """Extract episode number from AniLibria filename.

    Looks for first [digits] group. Returns int or None.
    Examples: Name_[05]_[...].mkv -> 5, Bleach_[001]_[...].mkv -> 1, Name_[26_END].mkv -> 26
    """
    m = EPISODE_PATTERN.search(filename)
    if m:
        return int(m.group(1))
    return None


def _parse_context_from_path(dirpath):
    """Extract show name and season number from directory structure.

    Expected: .../Show Name (Year)/Season XX/
    Returns (show_name, season_str) e.g. ('Поднятие уровня в одиночку', '01')
    """
    basename = os.path.basename(dirpath)
    parent = os.path.basename(os.path.dirname(dirpath))

    season_match = re.match(r'Season\s+(\d+)', basename)
    season_num = season_match.group(1).zfill(2) if season_match else '01'

    name_match = re.match(r'(.+?)\s*\(\d{4}\)$', parent)
    show_name = name_match.group(1).strip() if name_match else parent

    return show_name, season_num
