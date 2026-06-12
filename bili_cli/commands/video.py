"""Video-related commands."""

from __future__ import annotations

from typing import Any

import click
from rich.table import Table

from .. import payloads
from . import common


def _load_video_sections(
    *,
    bv_or_url: str,
    subtitle: bool,
    subtitle_timeline: bool,
    subtitle_format: str,
    comments: bool,
    comment_limit: int | None,
    ai: bool,
    related: bool,
) -> dict[str, Any]:
    from .. import client

    bvid = common.extract_bvid_or_exit(bv_or_url)
    needs_optional_cred = subtitle or subtitle_timeline or comments or ai or related
    cred = common.get_credential(mode="optional") if needs_optional_cred else None

    info = common.run_or_exit(
        client.get_video_info(bvid, credential=None),
        "获取视频信息失败",
    )

    subtitle_text = ""
    subtitle_items: list[dict[str, Any]] = []
    ai_summary = ""
    comments_items: list[dict[str, Any]] = []
    related_items: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []

    if subtitle or subtitle_timeline:
        sub_data = common.run_optional(
            client.get_video_subtitle(bvid, credential=cred),
            "获取字幕失败",
        )
        if sub_data is not None:
            subtitle_text, subtitle_items = sub_data
        else:
            warnings.append({"code": "subtitle_unavailable", "message": "获取字幕失败"})

    if ai:
        ai_data = common.run_optional(
            client.get_video_ai_conclusion(bvid, credential=cred),
            "获取 AI 总结失败",
        )
        if ai_data is not None:
            ai_summary = ai_data.get("model_result", {}).get("summary", "")
        else:
            warnings.append({"code": "ai_summary_unavailable", "message": "获取 AI 总结失败"})

    if comments:
        comments_data = common.run_optional(
            client.get_video_comments(bvid, credential=cred),
            "获取评论失败",
        )
        if comments_data is not None:
            comments_items = comments_data.get("replies") or []
            if comment_limit is not None and comment_limit >= 0:
                comments_items = comments_items[:comment_limit]
        else:
            warnings.append({"code": "comments_unavailable", "message": "获取评论失败"})

    if related:
        related_data = common.run_optional(
            client.get_related_videos(bvid, credential=cred),
            "获取相关推荐失败",
        )
        if related_data is not None:
            related_items = related_data
        else:
            warnings.append({"code": "related_unavailable", "message": "获取相关推荐失败"})

    return {
        "bvid": bvid,
        "info": info,
        "subtitle_text": subtitle_text,
        "subtitle_items": subtitle_items,
        "subtitle_format": subtitle_format if subtitle_timeline else "plain",
        "ai_summary": ai_summary,
        "comments_items": comments_items,
        "related_items": related_items,
        "warnings": warnings,
    }


def _build_structured_payload(sections: dict[str, Any]) -> dict[str, Any]:
    return payloads.normalize_video_command_payload(
        sections["info"],
        subtitle_text=sections["subtitle_text"],
        subtitle_items=sections["subtitle_items"],
        subtitle_format=sections["subtitle_format"],
        ai_summary=sections["ai_summary"],
        comments=sections["comments_items"],
        related=sections["related_items"],
        warnings=sections["warnings"],
    )


@click.command()
@click.argument("bv_or_url")
@click.option("--subtitle", "-s", is_flag=True, help="显示字幕内容")
@click.option("--subtitle-timeline", "-st", is_flag=True, help="显示带时间线的字幕")
@click.option(
    "--subtitle-format",
    type=click.Choice(["timeline", "srt"]),
    default="timeline",
    help="字幕格式：timeline 或 srt",
)
@click.option("--comments", "-c", is_flag=True, help="显示评论")
@click.option("--ai", is_flag=True, help="显示 AI 总结")
@click.option("--related", "-r", is_flag=True, help="显示相关推荐视频")
@common.structured_output_options
def video(
    bv_or_url: str,
    subtitle: bool,
    subtitle_timeline: bool,
    subtitle_format: str,
    comments: bool,
    ai: bool,
    related: bool,
    as_json: bool,
    as_yaml: bool,
):
    """查看视频详情."""
    output_format = common.resolve_output_format(as_json=as_json, as_yaml=as_yaml)
    sections = _load_video_sections(
        bv_or_url=bv_or_url,
        subtitle=subtitle,
        subtitle_timeline=subtitle_timeline,
        subtitle_format=subtitle_format,
        comments=comments,
        comment_limit=None,
        ai=ai,
        related=related,
    )
    structured_payload = _build_structured_payload(sections)
    if common.emit_structured(structured_payload, output_format):
        return

    info = sections["info"]
    bvid = sections["bvid"]
    subtitle_text = sections["subtitle_text"]
    subtitle_items = sections["subtitle_items"]
    ai_summary = sections["ai_summary"]
    comments_items = sections["comments_items"]
    related_items = sections["related_items"]

    stat = info.get("stat", {})
    owner = info.get("owner", {})

    table = Table(title=f"视频 {info.get('title', bvid)}", show_header=False, border_style="blue")
    table.add_column("Field", style="bold cyan", width=12)
    table.add_column("Value")

    table.add_row("BV", bvid)
    table.add_row("标题", info.get("title", ""))
    table.add_row("UP", f"{owner.get('name', '')} (UID: {owner.get('mid', '')})")
    table.add_row("时长", common.format_duration(info.get("duration", 0)))
    table.add_row("播放", common.format_count(stat.get("view", 0)))
    table.add_row("弹幕", common.format_count(stat.get("danmaku", 0)))
    table.add_row("点赞", common.format_count(stat.get("like", 0)))
    table.add_row("投币", common.format_count(stat.get("coin", 0)))
    table.add_row("收藏", common.format_count(stat.get("favorite", 0)))
    table.add_row("分享", common.format_count(stat.get("share", 0)))
    table.add_row("链接", f"https://www.bilibili.com/video/{bvid}")

    desc = info.get("desc", "").strip()
    if desc:
        table.add_row("简介", desc[:200])

    common.console.print(table)

    if subtitle or subtitle_timeline:
        common.console.print("\n[bold]字幕:[/bold]\n")
        if subtitle_timeline and subtitle_items:
            from .. import client

            display_content = client.format_subtitle_timeline(
                subtitle_items,
                output_format=subtitle_format,
            )
        else:
            display_content = subtitle_text

        if display_content:
            common.console.print(display_content)
        else:
            common.console.print("[yellow]无字幕[/yellow]")

    if ai:
        common.console.print("\n[bold]AI 总结:[/bold]\n")
        if ai_summary:
            common.console.print(ai_summary)
        else:
            common.console.print("[yellow]暂无 AI 总结[/yellow]")

    if comments:
        common.console.print("\n[bold]热门评论:[/bold]\n")
        if not comments_items:
            common.console.print("[yellow]暂无评论[/yellow]")
        else:
            for comment in comments_items[:10]:
                member = comment.get("member", {})
                content = comment.get("content", {}).get("message", "")
                likes = comment.get("like", 0)
                username = member.get("uname", "")
                common.console.print(f"  [cyan]{username}[/cyan] [dim](👍 {likes})[/dim]")
                common.console.print(f"  {content[:120]}")
                common.console.print()

    if related:
        common.console.print()
        if related_items:
            related_table = Table(title="相关推荐", border_style="blue")
            related_table.add_column("#", style="dim", width=4)
            related_table.add_column("BV", style="cyan", width=14)
            related_table.add_column("标题", max_width=40)
            related_table.add_column("UP", width=12)
            related_table.add_column("播放", width=8, justify="right")

            for index, related_video in enumerate(related_items[:10], start=1):
                related_owner = related_video.get("owner", {})
                related_stat = related_video.get("stat", {})
                related_table.add_row(
                    str(index),
                    related_video.get("bvid", ""),
                    related_video.get("title", "")[:40],
                    related_owner.get("name", "")[:12],
                    common.format_count(related_stat.get("view", 0)),
                )
            common.console.print(related_table)


@click.command(name="hydrate")
@click.argument("bv_or_url")
@click.option("-c", "--comment-limit", default=5, show_default=True, help="Maximum comments to include")
@common.structured_output_options
def hydrate(bv_or_url: str, comment_limit: int, as_json: bool, as_yaml: bool):
    """Fetch machine-readable detail for downstream hydration."""
    output_format = common.resolve_output_format(as_json=as_json, as_yaml=as_yaml)
    sections = _load_video_sections(
        bv_or_url=bv_or_url,
        subtitle=True,
        subtitle_timeline=False,
        subtitle_format="plain",
        comments=True,
        comment_limit=comment_limit,
        ai=False,
        related=False,
    )
    structured_payload = _build_structured_payload(sections)
    structured_payload["mode"] = "hydrate"
    if common.emit_structured(structured_payload, output_format):
        return

    video_data = structured_payload["video"]
    subtitle_data = structured_payload["subtitle"]
    common.console.print(
        f"Hydrated {video_data.get('bvid', '')}: "
        f"{len(structured_payload['comments'])} comments, "
        f"subtitle={'yes' if subtitle_data.get('available') else 'no'}"
    )


@click.command(name="comments")
@click.argument("bv_or_url")
@click.option("--page", default=1, show_default=True, type=click.IntRange(1), help="Comment page number")
@click.option("-l", "--limit", default=10, show_default=True, type=click.IntRange(1, 20), help="Comments per page")
@common.structured_output_options
def comments(bv_or_url: str, page: int, limit: int, as_json: bool, as_yaml: bool):
    """Fetch one page of video comments for downstream readers."""
    from .. import client

    output_format = common.resolve_output_format(as_json=as_json, as_yaml=as_yaml)
    bvid = common.extract_bvid_or_exit(bv_or_url)
    cred = common.get_credential(mode="optional")
    data = common.run_or_exit(
        client.get_video_comments(bvid, page=page, credential=cred),
        "获取评论失败",
    )

    replies = data.get("replies", []) if isinstance(data.get("replies"), list) else []
    page_info = data.get("page", {}) if isinstance(data.get("page"), dict) else {}
    api_page_size = int(page_info.get("size") or len(replies) or limit)
    total_count = page_info.get("acount") or page_info.get("count")
    try:
        total_count = int(total_count) if total_count not in (None, "") else None
    except (TypeError, ValueError):
        total_count = None

    has_more = False
    if total_count is not None and api_page_size > 0:
        has_more = page * api_page_size < total_count
    elif len(replies) >= api_page_size and api_page_size > 0:
        has_more = True

    payload = {
        "source": "bilibili",
        "entity_type": "video",
        "item_id": bvid,
        "cursor": str(page),
        "next_cursor": str(page + 1) if has_more else "",
        "limit": limit,
        "has_more": has_more,
        "total_count": total_count,
        "comments": [payloads.normalize_comment(item) for item in replies[:limit] if isinstance(item, dict)],
    }
    if common.emit_structured(payload, output_format):
        return

    if not payload["comments"]:
        common.console.print("[yellow]暂无评论[/yellow]")
        return

    for index, comment in enumerate(payload["comments"], start=1):
        author = comment.get("author", {}) if isinstance(comment.get("author"), dict) else {}
        common.console.print(
            f"[cyan]{index}. {author.get('name', 'Anonymous')}[/cyan] "
            f"[dim](👍 {comment.get('like', 0)})[/dim]"
        )
        common.console.print(str(comment.get("message", ""))[:160])
        common.console.print()
