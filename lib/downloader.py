import os
import yt_dlp
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union, Tuple, Callable
from lib.config_reader import config
from lib.init import videos_folder_path, cookies_file_path
from lib.logger import main_logger
from lib.storage import storage
from lib.utils.regex_utils import slugify_filename
from lib.video_optimizer import VideoOptimizer


@dataclass
class VideoInfo:
    downloaded: bool
    url: str
    info_path: Path
    tmp_path: Path
    video_path: Path
    server_url: str


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
        self.tmp_prefix = "tmp_"
        self.ydl_opts: yt_dlp._Params = {
            "format": format_selector,
            "format_sort": ["codec:avc", "res", "fps", "hdr:0", "br"],
            "merge_output_format": "mp4",  # Force final container to MP4
            "postprocessors": [{  # Add a postprocessor to remux to MP4
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }],
            "outtmpl": str(self.output_dir / f"{self.tmp_prefix}%(title)s.%(ext)s"),
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
        else:
            self.ydl_opts["cookiefile"] = str(path)

    def prepare_info(self, url: str) -> VideoInfo:
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            tmp_path = Path(ydl.prepare_filename(info))

            new_filename = slugify_filename(tmp_path.name[len(self.tmp_prefix):])
            video_path = (tmp_path.parent / new_filename)
            info_path = video_path.with_suffix('.json')
            server_url = f"{config.server_video_url}/{video_path.name}" if config.server_video_url else ""

            if video_path.is_file():
                return VideoInfo(True, url, info_path, tmp_path, video_path, server_url)

            if not info_path.exists():
                with open(info_path, "w") as f:
                    json.dump(info, f, ensure_ascii=False, indent=2)

        return VideoInfo(False, url, info_path, tmp_path, video_path, server_url)

    def download_video(self, video_info: VideoInfo, callback: Callable[[str], None] = None) -> Tuple[bool, str]:
        try:
            if video_info.downloaded:
                return False, "cached"

            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                error_code = ydl.download_with_info_file(str(video_info.info_path))
                if error_code:
                    raise RuntimeError(f"Error code: {error_code}")

                opt_needed, opt_info = self.optimizer.needs_optimization(video_info.tmp_path)

                if storage.optimize and opt_needed:
                    if callback:
                        callback("Optimizing...")
                else:
                    opt_info = None

                optimized = self.optimizer.process_download(video_info.tmp_path, video_info.video_path, opt_info)
                return False, 'optimized' if optimized else ''
        except Exception as e:
            main_logger.error(f"[Downloader] Error downloading {video_info.url}: {e}", exc_info=e)
            return True, str(e)

    def download(self, url: str, callback: Callable[[str], None] = None) -> Tuple[Optional[VideoInfo], str]:
        info = self.prepare_info(url)
        error, result = self.download_video(info, callback)
        if error:
            return None, result
        else:
            return info, result


downloader = Downloader(videos_folder_path, logger=False)


def main():
    print(downloader.download(url="https://youtu.be/X60dOghzlxU?si=wu3rMoU6dkdm16UL"))


if __name__ == '__main__':
    main()
