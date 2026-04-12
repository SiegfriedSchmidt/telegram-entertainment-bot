import os
import yt_dlp
from pathlib import Path
from typing import Optional, Union, List, Tuple, Callable, Coroutine
from lib.config_reader import config
from lib.init import videos_folder_path, cookies_file_path
from lib.logger import main_logger
from lib.storage import storage
from lib.utils.regex_utils import slugify_filename
from lib.video_optimizer import VideoOptimizer


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

        self.optimizer = VideoOptimizer(
            target_height=max_height,
            target_fps=60,
            crf=23,
            preset="medium"
        )

        format_selector = (
            # Best: H.264 video + AAC audio, height <= 1080
            f"bestvideo[vcodec^=avc][height<={max_height}]+bestaudio[acodec^=mp4a]/"
            # Combined H.264/AAC
            f"best[vcodec^=avc][acodec^=mp4a][height<={max_height}]/"
            # Fallback: any H.264 video + best audio
            f"bestvideo[vcodec^=avc][height<={max_height}]+bestaudio/"
            # Last resort: any format <= max_height (still prefers lower res)
            f"best[height<={max_height}]/best"
        )

        # Default options for yt-dlp
        self.ydl_opts: yt_dlp._Params = {
            "format": format_selector,
            "format_sort": ["codec:avc", "res", "fps", "hdr:0", "br"],
            "merge_output_format": "mp4",  # Force final container to MP4
            "postprocessors": [{  # Add a postprocessor to remux to MP4
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }],
            "outtmpl": str(self.output_dir / "tmp_%(title)s.%(ext)s"),
            "restrictfilenames": False,
            "windowsfilenames": False,
            "noplaylist": True,  # Only download single videos by default,
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

    async def download(self, url: str, callback: Callable[[str], Coroutine[None, None, None]] | None = None) -> \
            Tuple[Optional[Tuple[Path, str, str, bool]], str]:
        """
        Download a single video by URL.

        Args:
            url: The video URL to download.
            callback: Callback function to call on update.

        Returns:
            The path to the downloaded file (str) or the yt-dlp info dict if return_info=True.
        """
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                tmp_filepath = Path(ydl.prepare_filename(info))

                filename = slugify_filename(os.path.basename(tmp_filepath)[4:])
                opt_needed, opt_info = self.optimizer.needs_optimization(tmp_filepath)

                if storage.optimize and opt_needed:
                    if callback:
                        await callback("Optimizing...")
                else:
                    opt_info = None

                filepath, optimized = self.optimizer.process_download(tmp_filepath, filename, opt_info)
                server_url = f"{config.server_video_url}/{filename}" if config.server_video_url else ""

                return (filepath, filename, server_url, optimized), ''
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
