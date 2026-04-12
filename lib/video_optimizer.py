import subprocess
import json
from lib.logger import main_logger
from pathlib import Path
from typing import Tuple


def analyze_video(video_path: Path) -> dict:
    """Analyze video using ffprobe"""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(video_path)
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")

    return json.loads(result.stdout)


class VideoOptimizer:
    def __init__(
            self,
            target_height: int = 1080,
            target_fps: int = 30,
            crf: int = 23,
            audio_bitrate: str = "128k",
            preset: str = "medium"
    ):
        """
        Initialize video optimizer with quality settings.

        Args:
            target_height: Maximum height (1080 for Full HD)
            target_fps: Target framerate (30 or 60)
            crf: Constant Rate Factor for H.264 (18-28, higher = smaller file)
            audio_bitrate: Audio bitrate (e.g., "128k")
            preset: FFmpeg preset (ultrafast, fast, medium, slow, veryslow)
        """
        self.target_height = target_height
        self.target_fps = target_fps
        self.crf = crf
        self.audio_bitrate = audio_bitrate
        self.preset = preset

    def needs_optimization(self, video_path: Path) -> Tuple[bool, dict]:
        """
        Check if video needs optimization.
        Returns (needs_optimization, video_info)
        """
        info = analyze_video(video_path)

        video_stream = next(
            (s for s in info['streams'] if s['codec_type'] == 'video'),
            None
        )

        if not video_stream:
            return False, info

        # Check conditions that require optimization
        needs_opt = False
        reasons = []

        # Check resolution
        height = video_stream.get('height', 0)
        if height > self.target_height:
            needs_opt = True
            reasons.append(f"height={height}>{self.target_height}")

        # Check codec (prefer H.264)
        codec = video_stream.get('codec_name', '')
        if codec not in ['h264', 'avc']:
            needs_opt = True
            reasons.append(f"codec={codec}!=h264")

        # Check for HDR
        color_transfer = video_stream.get('color_transfer', '')
        color_primaries = video_stream.get('color_primaries', '')
        pix_fmt = video_stream.get('pix_fmt', '')

        hdr_indicators = [
            'smpte2084', 'arib-std-b67',  # PQ, HLG
            'bt2020', 'bt2020nc',
            'yuv420p10le', 'yuv420p12le'  # 10/12-bit (often HDR)
        ]

        if any(ind in str(color_transfer).lower() or
               ind in str(color_primaries).lower() or
               ind in str(pix_fmt).lower()
               for ind in hdr_indicators):
            needs_opt = True
            reasons.append("hdr_detected")

        # Check framerate (if too high)
        fps_parts = video_stream.get('r_frame_rate', '0/1').split('/')
        if len(fps_parts) == 2 and fps_parts[1] != '0':
            fps = float(fps_parts[0]) / float(fps_parts[1])
            if fps > self.target_fps * 1.1:  # 10% tolerance
                needs_opt = True
                reasons.append(f"fps={fps:.1f}>{self.target_fps}")

        # Check bitrate
        duration = float(info['format'].get('duration', 0))
        size = float(info['format'].get('size', 0))
        if duration > 0:
            bitrate = (size * 8) / (duration * 1000000)  # Mbps
            # Heuristic: if bitrate > 20 Mbps for 1080p, it's excessive
            if bitrate > 20:
                needs_opt = True
                reasons.append(f"high_bitrate={bitrate:.1f}Mbps")

        return needs_opt, info

    def optimize_video(self, input_path: Path, output_path: Path, info: dict) -> None:
        cmd = ["ffmpeg", "-i", str(input_path), "-y"]
        vf_filters = []

        video_stream = next(s for s in info['streams'] if s['codec_type'] == 'video')

        # Check for HDR characteristics
        color_transfer = video_stream.get('color_transfer', '').lower()
        color_primaries = video_stream.get('color_primaries', '').lower()
        pix_fmt = video_stream.get('pix_fmt', '').lower()

        is_hdr = any(ind in color_transfer or
                     ind in color_primaries or
                     ind in pix_fmt
                     for ind in ['smpte2084', 'arib-std-b67', 'bt2020', '10le', '12le'])

        # Scale if needed (do this first)
        height = video_stream.get('height', 0)
        if height > self.target_height:
            vf_filters.append(f"scale=-2:{self.target_height}")

        # Handle HDR content with simple tone adjustment
        if is_hdr:
            # Simple gamma and contrast adjustment for HDR content
            # This prevents dim output without requiring special filters
            vf_filters.append("eq=gamma=1.3:contrast=1.1:saturation=1.1")

            # Force SDR color space in output
            color_settings = [
                "-colorspace", "bt709",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
            ]
        else:
            color_settings = []

        # FPS conversion
        fps_parts = video_stream.get('r_frame_rate', '0/1').split('/')
        if len(fps_parts) == 2 and fps_parts[1] != '0':
            fps = float(fps_parts[0]) / float(fps_parts[1])
            if fps > self.target_fps * 1.1:
                vf_filters.append(f"fps={self.target_fps}")

        # Apply filters
        if vf_filters:
            cmd.extend(["-vf", ",".join(vf_filters)])

        # Video encoding
        cmd.extend([
            "-c:v", "libx264",
            "-preset", self.preset,
            "-crf", str(self.crf),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ])

        # Add color settings
        cmd.extend(color_settings)

        # Audio encoding
        cmd.extend([
            "-c:a", "aac",
            "-b:a", self.audio_bitrate,
            "-ac", "2",
            str(output_path)
        ])

        # Run FFmpeg
        try:
            subprocess.run(cmd, check=True, text=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Error running ffmpeg command: {e}")

    def process_download(self, tmp_path: Path | str, final_filename: str, info: dict | None) -> Tuple[Path, bool]:
        """
        Process downloaded video from temporary file to final optimized version.

        Args:
            tmp_path: Path to temporary video file (e.g., with .tmp.mp4 extension)
            final_filename: Optional custom final filename (without extension)
                           If not provided, will use sanitized version of tmp filename without .tmp
            info: Video info from ffprobe

        Returns:
            Path to final processed video file
        """
        if not isinstance(tmp_path, Path):
            tmp_path = Path(tmp_path)

        if not tmp_path.exists():
            raise FileNotFoundError(f"Temporary file not found: {tmp_path}")

        # Create final path with same extension
        final_path = tmp_path.parent / final_filename
        optimized = False

        if info is None:
            tmp_path.rename(final_path)
        else:
            try:
                self.optimize_video(tmp_path, final_path, info)
                tmp_path.unlink()
                optimized = True
            except RuntimeError as e:
                main_logger.warning(e)
                tmp_path.rename(final_path)

        return final_path, optimized
