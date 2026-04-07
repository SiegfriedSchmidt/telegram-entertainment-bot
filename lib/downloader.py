import os
import yt_dlp
from pathlib import Path
from typing import Optional, Union, List, Tuple
from lib.config_reader import config
from lib.init import videos_folder_path, cookies_file_path
from lib.logger import main_logger


def yt_dlp_hook(d):
    if d['status'] == 'finished':
        pass
        # main_logger.info('Done downloading, now post-processing ...')


class Downloader:
    def __init__(
            self,
            output_dir: Union[str, Path],
            max_height=1080,
            logger: bool = False,
    ):
        """
        Downloader that saves:
         - MP4 format (if possible)
         - Merged video+audio
         - Max resolution limited by max_height

        Args:
            output_dir: Directory to save files
            max_height: Max video height (px), e.g. 1080
            logger: Whether to show yt-dlp logs
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        format_selector = (
            # 1) BEST: Separate H.264 video + AAC audio
            f"bestvideo[vcodec^=avc][height<={max_height}]+bestaudio[acodec^=mp4a]/"
            # 2) BEST: Combined H.264/AAC file
            f"best[vcodec^=avc][acodec^=mp4a][height<={max_height}]/"
            # 3) FALLBACK: Best H.264 video (any container/audio), merged with best audio
            f"bestvideo[vcodec^=avc][height<={max_height}]+bestaudio/"
            # 4) LAST RESORT: Any format that can be remuxed to MP4
            f"best[height<={max_height}]/best"
        )

        # Default options for yt-dlp
        self.ydl_opts = {
            "format": format_selector,
            "merge_output_format": "mp4",  # Force final container to MP4
            "postprocessors": [{  # Add a postprocessor to remux to MP4
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }],
            "outtmpl": str(self.output_dir / "%(title)s.%(ext)s"),
            "restrictfilenames": True,
            "windowsfilenames": True,
            "noplaylist": True,  # Only download single videos by default
            # "logger": main_logger,
            "progress_hooks": [yt_dlp_hook],
        }

        if config.proxy_url:
            self.ydl_opts["proxy"] = config.proxy_url

        if not logger:
            # Suppress verbose yt-dlp output
            self.ydl_opts.update({"quiet": True, "no_warnings": True})

        if os.path.exists(cookies_file_path) and os.path.isfile(cookies_file_path):
            self.cookies = cookies_file_path

    @property
    def cookies(self) -> str:
        return self.ydl_opts["cookiefile"]

    @cookies.setter
    def cookies(self, path: str | Path | None) -> None:
        if path is None:
            self.ydl_opts.pop("cookiefile", "")
        self.ydl_opts["cookiefile"] = str(path)

    def download(self, url: str) -> Tuple[Optional[Tuple[str, str, str, dict]], str]:
        """
        Download a single video by URL.

        Args:
            url: The video URL to download.

        Returns:
            The path to the downloaded file (str) or the yt-dlp info dict if return_info=True.
        """
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # Construct final filename from yt-dlp info
                filepath = ydl.prepare_filename(info)
                filename = os.path.basename(filepath)
                server_url = f"{config.server_video_url}/{filename}" if config.server_video_url else ""
                return (filepath, filename, server_url, info), ''
        except Exception as e:
            main_logger.error(f"[Downloader] Error downloading {url}: {e}", exc_info=e)
            return None, str(e)

    def batch_download(self, urls: List[str]) -> List[Optional[str]]:
        """
        Download multiple URLs.

        Args:
            urls: List of video URLs.

        Returns:
            List of local file paths (or None for failures).
        """
        results = []
        for url in urls:
            res = self.download(url)
            results.append(res)
        return results


downloader = Downloader(videos_folder_path, logger=False)


def main():
    print(downloader.download(url="https://youtu.be/X60dOghzlxU?si=wu3rMoU6dkdm16UL"))


if __name__ == '__main__':
    main()
