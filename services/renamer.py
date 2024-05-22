import os
import re
import logging


logger = logging.getLogger(__name__)


class Renamer:
    def __init__(self, dir, anilibria_regex):
        self.dir = dir
        self.anilibria_regex = anilibria_regex

    def rename(self):
        for address, dirs, files in os.walk(self.dir):
            for filename in files:
                match_result = re.match(self.anilibria_regex, filename)
                if match_result:
                    abs_path = os.path.join(address, filename)
                    logger.info('Match file to rename: {}'.format(abs_path))

                    new_filename = self.get_new_filename(match_result)
                    new_abs_path = os.path.join(address, new_filename)

                    os.rename(abs_path, new_abs_path)
                    logger.info('Successful rename file, new name is: {}'.format(new_abs_path))

    def get_new_filename(self, match_result):
        name, s, e = self.extract_data(match_result)
        new_filename = name + ' - s' + s + 'e' + e + '.mkv'
        return new_filename

    @staticmethod
    def extract_data(match_result):
        name = match_result.group('name')
        episode = match_result.group('episode')
        season = 1

        season_match = re.match('.*(S(?P<season>[0-9]{1}))$', name)
        if season_match:
            season = int(season_match.group('season'))

        season = '0' + str(season) if season < 10 else str(season)

        return name, season, episode
