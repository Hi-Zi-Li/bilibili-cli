"""Video download command — download video and audio streams for offline viewing."""

from __future__ import annotations

import os
import re
import tempfile

import click

from .common import console, exit_error, extract_bvid_or_exit, get_credential, run_or_exit

DEFAULT_TMP_DIR = os.path.join(tempfile.gettempdir(), "bilibili-cli")


def _sanitize_filename(title: str) -> str:
    """Remove or replace characters that are unsafe in file paths."""
    title = re.sub(r'[<>:"/\\|?*]', "_", title)
    title = title.strip(". ")
    return title[:120] or "video"


@click.command()
@click.argument("bv_or_url")
@click.option("--output", "-o", default=None, type=click.Path(),
              help=f"输出目录（默认 {DEFAULT_TMP_DIR}/{{title}}/）。")
@click.option("--video-only", is_flag=True, help="只下载视频流（不含音频）。")
@click.option("--audio-only", is_flag=True, help="只下载音频流。")
@click.option("--no-merge", is_flag=True, help="不合并视频和音频，分别保存文件。")
def download(bv_or_url: str, output: str | None, video_only: bool, audio_only: bool, no_merge: bool):
    """下载视频（视频+音频流）用于离线观看。

    默认下载视频和音频流，并使用 ffmpeg 合并为 MP4 文件。
    如果未安装 ffmpeg，则保存为单独的文件。

    \b
    示例:
      bili download BV1ABcsztEcY                  # 下载并合并
      bili download BV1ABcsztEcY --video-only     # 只下载视频
      bili download BV1ABcsztEcY --no-merge       # 分别保存视频和音频文件
      bili download BV1ABcsztEcY -o ~/videos/     # 自定义输出目录
    """
    from .. import client

    bvid = extract_bvid_or_exit(bv_or_url)

    # 1. Get video info for title
    cred = get_credential(mode="optional")
    info = run_or_exit(client.get_video_info(bvid, credential=cred), "获取视频信息")
    title = info.get("title", bvid)
    duration = info.get("duration", 0)
    safe_title = _sanitize_filename(title)

    console.print(f"[bold]📺 {title}[/bold]  ({_format_time(duration)})")

    # Determine output directory
    if output:
        out_dir = os.path.expanduser(output)
    else:
        out_dir = os.path.join(DEFAULT_TMP_DIR, safe_title)
    os.makedirs(out_dir, exist_ok=True)

    video_url = None
    audio_url = None
    video_path = None
    audio_path = None

    try:
        # 2. Get video stream URL if needed
        if not audio_only:
            console.print("[dim]获取视频流地址...[/dim]")
            video_url = run_or_exit(client.get_video_url(bvid, credential=cred), "获取视频流")
            video_path = os.path.join(out_dir, f"{safe_title}_video.m4s")
            console.print("[dim]下载视频流中...[/dim]")
            video_bytes = run_or_exit(client.download_video(video_url, video_path), "下载视频")
            video_mb = video_bytes / (1024 * 1024)
            console.print(f"[green]✅ 视频流已保存: {video_path} ({video_mb:.1f} MB)[/green]")

        # 3. Get audio stream URL if needed
        if not video_only:
            console.print("[dim]获取音频流地址...[/dim]")
            audio_url = run_or_exit(client.get_audio_url(bvid, credential=cred), "获取音频流")
            audio_path = os.path.join(out_dir, f"{safe_title}_audio.m4s")
            console.print("[dim]下载音频流中...[/dim]")
            audio_bytes = run_or_exit(client.download_audio(audio_url, audio_path), "下载音频")
            audio_mb = audio_bytes / (1024 * 1024)
            console.print(f"[green]✅ 音频流已保存: {audio_path} ({audio_mb:.1f} MB)[/green]")

        # 4. Merge if both downloaded and merging is requested
        if not no_merge and not video_only and not audio_only and video_path and audio_path:
            output_mp4 = os.path.join(out_dir, f"{safe_title}.mp4")
            console.print("[dim]合并视频和音频...[/dim]")
            if _merge_with_ffmpeg(video_path, audio_path, output_mp4):
                console.print(f"[green]✅ 合并完成: {output_mp4}[/green]")
                # Optionally clean up separate files
                # os.unlink(video_path)
                # os.unlink(audio_path)
            else:
                console.print("[yellow]⚠️  ffmpeg 不可用，请手动合并:[/yellow]")
                console.print(f"[dim]  ffmpeg -i '{video_path}' -i '{audio_path}' -c copy '{output_mp4}'[/dim]")

    except Exception as e:
        # Clean up partial downloads
        if video_path and os.path.exists(video_path):
            os.unlink(video_path)
        if audio_path and os.path.exists(audio_path):
            os.unlink(audio_path)
        raise e


def _merge_with_ffmpeg(video_path: str, audio_path: str, output_path: str) -> bool:
    """Merge video and audio using ffmpeg. Returns True on success."""
    try:
        import subprocess
        result = subprocess.run(
            ["ffmpeg", "-i", video_path, "-i", audio_path, "-c", "copy", "-y", output_path],
            capture_output=True,
            timeout=300,
        )
        if result.returncode == 0:
            return True
        console.print(f"[yellow]ffmpeg 合并失败: {result.stderr.decode()[:200]}[/yellow]")
        return False
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def _format_time(seconds: int) -> str:
    """Format duration for display."""
    if seconds >= 3600:
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}"
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"