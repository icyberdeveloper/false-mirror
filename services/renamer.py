import os
import re
import logging


logger = logging.getLogger(__name__)


class Renamer:
    def __init__(self, root_dir, anilibria_regex):
        self.root_dir = root_dir
        self.anilibria_regex = anilibria_regex

    def rename(self):
        if not self.anilibria_regex:
            return
        logger.info(f'Renamer walking: {self.root_dir}')
        for dirpath, dirs, files in os.walk(self.root_dir):
            for filename in files:
                match = re.match(self.anilibria_regex, filename)
                if match:
                    old_path = os.path.join(dirpath, filename)
                    new_filename = self._build_new_filename(match)
                    new_path = os.path.join(dirpath, new_filename)
                    logger.info(f'Renaming: {filename} -> {new_filename}')
                    os.rename(old_path, new_path)

    def _build_new_filename(self, match):
        name = match.group('name')
        episode = match.group('episode')
        season = 1

        season_match = re.match(r'(?P<name>.+)S(?P<season>\d+)$', name)
        if season_match:
            season = int(season_match.group('season'))
            name = season_match.group('name')

        name = name.replace('_', ' ').strip()
        season_str = f'{season:02d}'
        return f'{name} - s{season_str}e{episode}.mkv'
