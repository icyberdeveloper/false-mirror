import os
import re
import logging


logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {'.mkv', '.avi', '.mp4', '.ts', '.m4v'}


class Library:
    """Checks the actual filesystem (completed + incomplete) to determine what's already downloaded."""

    def __init__(self, library_dir, incomplete_dir=None):
        self.library_dir = library_dir
        self.incomplete_dir = incomplete_dir

    def episode_exists(self, show_code, show_name, release_year, season_num, episode_num):
        """Check if a specific episode exists on disk (completed or downloading)."""
        ep_pattern = re.compile(
            rf'[Ss]{int(season_num):02d}[Ee]{int(episode_num):02d}',
        )

        # Check completed downloads in season folder
        season_dir = os.path.join(
            self.library_dir, f'{show_name} ({release_year})', f'Season {season_num}'
        )
        if _has_matching_file(season_dir, ep_pattern):
            return True

        # Check incomplete/downloading files — match show code AND episode
        if self.incomplete_dir and os.path.isdir(self.incomplete_dir):
            # show_code like "The_Rookie" -> match "The.Rookie" or "The_Rookie" in filename
            code_pattern = show_code.replace('_', '.')
            for filename in os.listdir(self.incomplete_dir):
                ext = os.path.splitext(filename)[1].lower()
                if ext not in VIDEO_EXTENSIONS:
                    continue
                if ep_pattern.search(filename) and code_pattern.lower() in filename.lower():
                    logger.debug(f'Found incomplete episode: {filename}')
                    return True

        return False

    def season_has_files(self, show_name, release_year, season_num):
        """Check if a season directory has any video files (for full-season torrents)."""
        season_dir = os.path.join(
            self.library_dir, f'{show_name} ({release_year})', f'Season {season_num}'
        )
        if not os.path.isdir(season_dir):
            return False

        for filename in os.listdir(season_dir):
            ext = os.path.splitext(filename)[1].lower()
            if ext in VIDEO_EXTENSIONS:
                return True
        return False


def _has_matching_file(directory, pattern):
    if not os.path.isdir(directory):
        return False
    for filename in os.listdir(directory):
        ext = os.path.splitext(filename)[1].lower()
        if ext in VIDEO_EXTENSIONS and pattern.search(filename):
            return True
    return False
