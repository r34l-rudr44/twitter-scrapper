"""
Exporters for Twitter/X Thread Scraper.
Produces structured, unambiguous exports organized by context-first folder naming:
output/{username}/{content_title}_{tweet_id}/
  ├── thread.md          (Clean unrolled main thread)
  ├── comments.md        (Multi-level nested comments and sub-reply trees)
  ├── requotes.md        (Requotes tied to exact quoted tweets & unrolled quote threads)
  ├── full_archive.md    (Comprehensive unified archive)
  ├── thread_data.json   (Mega unified JSON schema tying everything together)
  ├── thread_data.txt    (Plain text reading format)
  ├── thread_view.html   (Standalone responsive interactive viewer)
  └── media/             (High-resolution downloaded photos and videos)
"""

import os
import re
import json
import html
from typing import Optional, List, Dict, Tuple
from pathlib import Path
import requests

from models import Thread, Tweet, MediaItem, Requote, CommentNode


class ThreadExporter:
    """Handles serialization and file exporting for scraped threads, comments, and requotes."""

    @staticmethod
    def sanitize_title(name: str) -> str:
        """Sanitizes a string to be used safely as a human-readable title."""
        # Replace punctuation and special characters with spaces/underscores
        clean = re.sub(r'[\\/*?:"<>|#@,;!.]', "", name)
        clean = re.sub(r"\s+", "_", clean.strip())
        return clean[:55] or "thread"

    @classmethod
    def get_output_paths(cls, thread: Thread, base_output_dir: str = "output") -> Tuple[str, str]:
        """
        Calculates the context-first human-friendly directory structure:
        output/{username}/{sanitized_title}_{tweet_id}/
        """
        username = thread.author.screen_name or "unknown_user"
        content_title = cls.sanitize_title(thread.title)
        folder_name = f"{content_title}_{thread.root_id}"
        target_dir = os.path.join(base_output_dir, username, folder_name)
        return target_dir, folder_name

    @classmethod
    def to_thread_markdown(cls, thread: Thread) -> str:
        """Generates dedicated thread.md containing the unrolled main author thread."""
        author = thread.author
        lines = []

        lines.append(f"# {thread.title}\n")
        lines.append(f"**Author:** [{author.name} (@{author.screen_name})]({author.profile_url})  ")
        if thread.tweets:
            lines.append(f"**Date:** {thread.tweets[0].formatted_date}  ")
        lines.append(
            f"**Stats:** 🧵 {thread.tweet_count} Main Tweets | ❤️ {thread.total_likes:,} Likes | 🔁 {thread.total_retweets:,} Retweets  "
        )
        lines.append(f"**Original URL:** [{thread.source_url}]({thread.source_url})\n")
        lines.append("---\n")

        for tweet in thread.tweets:
            lines.append(f"### Tweet {tweet.position_in_thread} of {thread.tweet_count}")
            lines.append(f"*Posted on {tweet.formatted_date}* • [View on X]({tweet.url})\n")
            lines.append(f"{tweet.text}\n")

            if tweet.media:
                lines.append("**Attached Media:**")
                for i, m in enumerate(tweet.media, 1):
                    if m.type == "photo":
                        lines.append(f"- 📷 [Image {i}]({m.url})")
                        lines.append(f"  ![Image {i}]({m.url})")
                    elif m.type == "video":
                        lines.append(f"- 🎬 [Watch Video]({m.url})")
                lines.append("")

            if tweet.quote:
                lines.append(f"> 🗨️ **Quote from {tweet.quote.author_name} (@{tweet.quote.author_screen_name}):**")
                lines.append(f"> {tweet.quote.text}")
                if tweet.quote.url:
                    lines.append(f"> [Original Quoted Tweet]({tweet.quote.url})")
                lines.append("")

            metrics_parts = []
            if tweet.likes:
                metrics_parts.append(f"❤️ {tweet.likes:,} likes")
            if tweet.retweets:
                metrics_parts.append(f"🔁 {tweet.retweets:,} retweets")
            if tweet.replies:
                metrics_parts.append(f"💬 {tweet.replies:,} replies")
            if tweet.views:
                metrics_parts.append(f"👁️ {tweet.views:,} views")

            if metrics_parts:
                lines.append(f"*{' • '.join(metrics_parts)}*\n")
            lines.append("---\n")

        return "\n".join(lines)

    @classmethod
    def _render_comment_node_md(cls, node: CommentNode, indent_level: int = 0) -> List[str]:
        """Recursively renders a CommentNode and all its nested sub-replies in Markdown."""
        lines = []
        t = node.tweet
        author = t.author
        indent = "  " * indent_level
        prefix = "└─ " if indent_level > 0 else ""

        level_tag = f"[Level {node.depth}]"
        lines.append(f"{indent}{prefix}**{author.name}** ([@{author.screen_name}]({author.profile_url})) {level_tag} — *❤️ {t.likes:,} likes* • *{t.formatted_date}*")
        lines.append(f"{indent}[View on X]({t.url})\n")

        for body_line in t.text.split("\n"):
            lines.append(f"{indent}> {body_line}")
        lines.append("")

        for reply_node in node.replies:
            lines.extend(cls._render_comment_node_md(reply_node, indent_level + 1))

        return lines

    @classmethod
    def to_comments_markdown(cls, thread: Thread) -> str:
        """Generates dedicated comments.md containing the hierarchical multi-level comment tree."""
        lines = []
        lines.append(f"# 💬 Comments & Discussion Tree\n")
        lines.append(f"**Target Thread:** [{thread.title}]({thread.source_url})  ")
        lines.append(f"**Total Captured Comments:** {thread.comment_count} | **Top-Level Discussions:** {thread.top_level_comment_count}\n")
        lines.append("---\n")

        if not thread.comment_tree and not thread.comments:
            lines.append("*No public comments or replies were found on this post.*\n")
            return "\n".join(lines)

        if thread.comment_tree:
            for i, top_node in enumerate(thread.comment_tree, 1):
                lines.append(f"## 🗨️ Discussion #{i} (Top-Level)")
                lines.extend(cls._render_comment_node_md(top_node, indent_level=0))
                lines.append("---\n")
        else:
            for c in thread.comments:
                lines.append(f"### 🗨️ {c.author.name} ([@{c.author.screen_name}]({c.author.profile_url})) — *❤️ {c.likes:,} likes*")
                lines.append(f"*{c.formatted_date}* • [View Reply]({c.url})\n")
                lines.append(f"{c.text}\n")
                lines.append("---\n")

        return "\n".join(lines)

    @classmethod
    def to_requotes_markdown(cls, thread: Thread) -> str:
        """
        Generates dedicated requotes.md explicitly linking which exact tweet in the thread
        was quoted, the unrolled quote thread, and any discussion on that requote.
        """
        lines = []
        lines.append(f"# 🔁 Requotes & Quote Threads\n")
        lines.append(f"**Target Thread:** [{thread.title}]({thread.source_url})  ")
        lines.append(
            f"**Total Requotes Captured:** {thread.requote_count} (Single Quotes: {thread.single_requote_count} | Multi-Tweet Quote Threads: {thread.thread_requote_count})\n"
        )
        lines.append("---\n")

        if not thread.requotes:
            lines.append("*No requotes or quote threads were found on this post.*\n")
            return "\n".join(lines)

        for i, req in enumerate(thread.requotes, 1):
            r_author = req.author
            tag = f"🧵 {req.tweet_count}-Tweet Quote Thread" if req.is_thread else "📌 Single Requote"
            lines.append(f"## Requote #{i}: {r_author.name} ([@{r_author.screen_name}]({r_author.profile_url})) — *{tag}*")
            
            # Show exact quoted tweet target in the main thread
            if req.quoted_tweet_position:
                lines.append(f"> 📌 **Quoted Tweet #{req.quoted_tweet_position} of Main Thread:**  ")
                if req.quoted_tweet_snippet:
                    lines.append(f"> *\"{req.quoted_tweet_snippet}\"*  ")
                if req.quoted_status_id:
                    lines.append(f"> [View Quoted Tweet](https://x.com/i/status/{req.quoted_status_id})\n")
            elif req.quoted_status_id:
                lines.append(f"> 📌 **Quoting Tweet ID:** [{req.quoted_status_id}](https://x.com/i/status/{req.quoted_status_id})\n")

            lines.append(f"**Total Engagement on Requote:** ❤️ {req.total_likes:,} likes | 🔁 {req.total_retweets:,} retweets\n")

            for t in req.tweets:
                prefix = f"**[{t.position_in_thread}/{req.tweet_count}]** " if req.is_thread else ""
                lines.append(f"{prefix}*Posted on {t.formatted_date}* • [View on X]({t.url})\n")
                lines.append(f"{t.text}\n")
                if t.media:
                    for m in t.media:
                        lines.append(f"- Attached {m.type}: {m.url}")
                    lines.append("")

            # Render downstream comments on this requote if present
            if req.comments:
                lines.append(f"### 💬 Comments on this Requote ({len(req.comments)}):")
                for c_node in req.comments:
                    lines.extend(cls._render_comment_node_md(c_node, indent_level=1))

            lines.append("---\n")

        return "\n".join(lines)

    @classmethod
    def to_full_archive_markdown(cls, thread: Thread) -> str:
        """Generates a complete unified full_archive.md with Thread, Comments Tree, and Requotes."""
        thread_md = cls.to_thread_markdown(thread)
        comments_md = cls.to_comments_markdown(thread)
        requotes_md = cls.to_requotes_markdown(thread)

        parts = [
            thread_md,
            "\n\n" + "=" * 60 + "\n\n",
            comments_md,
            "\n\n" + "=" * 60 + "\n\n",
            requotes_md
        ]
        return "".join(parts)

    @classmethod
    def to_json(cls, thread: Thread, indent: int = 2) -> str:
        """Converts thread, nested comment trees, and requotes to structured Mega JSON."""
        return json.dumps(thread.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def to_text(cls, thread: Thread) -> str:
        """Converts thread to clean plain text format."""
        author = thread.author
        lines = []
        lines.append("=" * 60)
        lines.append(f"THREAD ARCHIVE: {thread.title}")
        lines.append(f"AUTHOR: {author.name} (@{author.screen_name})")
        lines.append(f"STATS: {thread.tweet_count} Main Tweets | {thread.comment_count} Comments | {thread.requote_count} Requotes")
        lines.append(f"SOURCE: {thread.source_url}")
        lines.append("=" * 60)
        lines.append("\n--- MAIN THREAD ---")
        for tweet in thread.tweets:
            lines.append(f"[{tweet.position_in_thread}/{thread.tweet_count}] {tweet.formatted_date}")
            lines.append(tweet.text)
            lines.append("")

        if thread.comments:
            lines.append("\n--- COMMENTS & REPLIES ---")
            for c in thread.comments:
                lines.append(f"[@{c.author.screen_name}] (❤️ {c.likes:,} likes - {c.formatted_date}):")
                lines.append(f"{c.text}\n")

        if thread.requotes:
            lines.append("\n--- REQUOTES & QUOTE THREADS ---")
            for req in thread.requotes:
                tag = f"[QUOTE THREAD ({req.tweet_count} Tweets)]" if req.is_thread else "[SINGLE REQUOTE]"
                ref_info = f" (Quoting Tweet #{req.quoted_tweet_position})" if req.quoted_tweet_position else ""
                lines.append(f"{tag}{ref_info} @{req.author.screen_name} (❤️ {req.total_likes:,}):")
                for t in req.tweets:
                    lines.append(f"  ({t.position_in_thread}/{req.tweet_count}) {t.text}")
                lines.append("")

        return "\n".join(lines)

    @classmethod
    def _render_comment_node_html(cls, node: CommentNode, is_reply: bool = False) -> str:
        """Recursively renders a CommentNode into properly nested, visually threaded HTML."""
        t = node.tweet
        avatar = f'<img src="{t.author.avatar_url}" class="comment-avatar" alt="{html.escape(t.author.name)}">' if t.author.avatar_url else f'<div class="comment-avatar-placeholder">{html.escape(t.author.name[0].upper())}</div>'
        sub_replies_html = "".join(cls._render_comment_node_html(r, is_reply=True) for r in node.replies)

        wrapper_class = "comment-thread-reply" if is_reply else "comment-thread-root"
        branch_tag = f'<div class="reply-branch-tag">↳ Reply [Level {node.depth}]</div>' if is_reply else ''

        reply_block = ""
        if sub_replies_html:
            reply_block = f'<div class="replies-container">{sub_replies_html}</div>'

        return f'''
        <div class="{wrapper_class}">
            <div class="comment-layout">
                <div class="comment-left-col">
                    {avatar}
                    {"<div class='thread-line'></div>" if node.replies else ""}
                </div>
                <div class="comment-right-col">
                    {branch_tag}
                    <div class="comment-meta">
                        <span class="comment-author">{html.escape(t.author.name)}</span>
                        <span class="handle">@{html.escape(t.author.screen_name)}</span>
                        <span class="comment-date">{t.formatted_date}</span>
                    </div>
                    <div class="comment-body">{html.escape(t.text).replace(chr(10), "<br>")}</div>
                    <div class="comment-footer">
                        <span>❤️ {t.likes:,} likes</span>
                        <a href="{t.url}" target="_blank" class="tweet-link">View Reply ↗</a>
                    </div>
                </div>
            </div>
            {reply_block}
        </div>
        '''


    @classmethod
    def to_html(cls, thread: Thread) -> str:
        """Generates a modern standalone HTML archive with interactive sections."""
        author = thread.author
        avatar_html = f'<img src="{author.avatar_url}" class="author-avatar" alt="{author.name}">' if author.avatar_url else ''
        verified_badge = '<span class="badge">✓</span>' if author.verified else ''

        # 1. Main Tweets HTML
        tweets_html = []
        for tweet in thread.tweets:
            media_blocks = []
            for m in tweet.media:
                if m.type == "photo":
                    media_blocks.append(f'<div class="media-wrapper"><a href="{m.url}" target="_blank"><img src="{m.url}" class="tweet-img" loading="lazy"></a></div>')
                elif m.type == "video":
                    media_blocks.append(f'<div class="media-wrapper"><video controls class="tweet-video" poster="{m.thumbnail_url or ""}"><source src="{m.url}" type="video/mp4"></video></div>')

            media_html = f'<div class="tweet-media-grid">{"".join(media_blocks)}</div>' if media_blocks else ''

            quote_html = ""
            if tweet.quote:
                quote_html = f'''
                <div class="quote-card">
                    <div class="quote-header">
                        <strong>{html.escape(tweet.quote.author_name)}</strong>
                        <span class="handle">@{html.escape(tweet.quote.author_screen_name)}</span>
                    </div>
                    <div class="quote-body">{html.escape(tweet.quote.text).replace(chr(10), "<br>")}</div>
                </div>
                '''

            tweets_html.append(f'''
            <article class="tweet-card">
                <div class="tweet-card-header">
                    <span class="tweet-num">Tweet {tweet.position_in_thread} of {thread.tweet_count}</span>
                    <span class="tweet-date">{tweet.formatted_date}</span>
                </div>
                <div class="tweet-body">{html.escape(tweet.text).replace(chr(10), "<br>")}</div>
                {media_html}
                {quote_html}
                <div class="tweet-footer">
                    <div class="tweet-metrics">
                        <span>❤️ {tweet.likes:,}</span>
                        <span>🔁 {tweet.retweets:,}</span>
                        <span>💬 {tweet.replies:,}</span>
                    </div>
                    <a href="{tweet.url}" target="_blank" class="tweet-link">View on X ↗</a>
                </div>
            </article>
            ''')

        # 2. Comments Tree HTML
        if thread.comment_tree:
            comments_html = "".join(cls._render_comment_node_html(n) for n in thread.comment_tree)
        elif thread.comments:
            comments_html = "".join(f'''
            <div class="comment-card">
                <div class="comment-header">
                    <strong>{html.escape(c.author.name)}</strong>
                    <span class="handle">@{html.escape(c.author.screen_name)}</span>
                    <span class="comment-date">{c.formatted_date}</span>
                </div>
                <div class="comment-body">{html.escape(c.text).replace(chr(10), "<br>")}</div>
                <div class="comment-footer">
                    <span>❤️ {c.likes:,} likes</span>
                    <a href="{c.url}" target="_blank" class="tweet-link">View Reply ↗</a>
                </div>
            </div>
            ''' for c in thread.comments)
        else:
            comments_html = "<p style='color:var(--text-secondary); font-style:italic;'>No public comments found on this post.</p>"

        # 3. Requotes HTML
        requotes_blocks = []
        for req in thread.requotes:
            badge_class = "badge-thread" if req.is_thread else "badge-single"
            badge_text = f"🧵 {req.tweet_count}-Tweet Quote Thread" if req.is_thread else "📌 Single Requote"
            
            ref_badge = f'<span class="ref-badge">Quoting Tweet #{req.quoted_tweet_position}</span>' if req.quoted_tweet_position else ''

            sub_tweets = []
            for t in req.tweets:
                prefix = f'<span class="sub-num">[{t.position_in_thread}/{req.tweet_count}]</span> ' if req.is_thread else ''
                sub_tweets.append(f'''
                <div class="requote-item">
                    <div class="requote-text">{prefix}{html.escape(t.text).replace(chr(10), "<br>")}</div>
                    <div class="requote-item-footer">
                        <span>{t.formatted_date}</span>
                        <a href="{t.url}" target="_blank" class="tweet-link">View on X ↗</a>
                    </div>
                </div>
                ''')

            r_avatar = f'<img src="{req.author.avatar_url}" class="comment-avatar">' if req.author.avatar_url else ''

            # Render comments on this requote as a threaded tree
            req_comments_html = ""
            if req.comments:
                comments_rendered = "".join(cls._render_comment_node_html(c_node) for c_node in req.comments)
                req_comments_html = f'''
                <div class="requote-comments">
                    <div class="requote-comments-label">💬 {len(req.comments)} comment{"s" if len(req.comments) != 1 else ""} on this requote</div>
                    {comments_rendered}
                </div>'''

            requotes_blocks.append(f'''
            <div class="requote-card">
                <div class="requote-header">
                    <div style="display:flex; align-items:center; gap:0.5rem;">
                        {r_avatar}
                        <div>
                            <strong>{html.escape(req.author.name)}</strong>
                            <span class="handle">@{html.escape(req.author.screen_name)}</span>
                            {ref_badge}
                        </div>
                    </div>
                    <span class="requote-badge {badge_class}">{badge_text}</span>
                </div>
                <div class="requote-stream">
                    {"".join(sub_tweets)}
                </div>
                {req_comments_html}
            </div>
            ''')

        requotes_html = "".join(requotes_blocks) if requotes_blocks else "<p style='color:var(--text-secondary); font-style:italic;'>No requotes or quote threads found on this post.</p>"

        full_html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(thread.title)} | Twitter Thread Archive</title>
    <style>
        :root {{
            --bg: #0f1419;
            --card-bg: #1e2732;
            --card-border: #2f3336;
            --text-primary: #f7f9f9;
            --text-secondary: #8b98a5;
            --accent: #1d9bf0;
            --quote-bg: #15181c;
            --thread-badge: #7856ff;
            --level-badge: #00ba7c;
            --ref-badge: #ff7a00;
        }}
        @media (prefers-color-scheme: light) {{
            :root {{
                --bg: #f7f9f9;
                --card-bg: #ffffff;
                --card-border: #eff3f4;
                --text-primary: #0f1419;
                --text-secondary: #536471;
                --accent: #1d9bf0;
                --quote-bg: #f7f9f9;
                --thread-badge: #7856ff;
                --level-badge: #00ba7c;
                --ref-badge: #ff7a00;
            }}
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            line-height: 1.5;
            padding: 2rem 1rem;
        }}
        .container {{ max-width: 760px; margin: 0 auto; }}
        .header-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }}
        .author-box {{ display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }}
        .author-avatar {{ width: 56px; height: 56px; border-radius: 50%; object-fit: cover; }}
        .comment-avatar {{
            width: 36px; height: 36px; border-radius: 50%; object-fit: cover;
            flex-shrink: 0; display: block;
        }}
        .comment-avatar-placeholder {{
            width: 36px; height: 36px; border-radius: 50%; background: var(--accent);
            color: #fff; font-weight: bold; font-size: 0.9rem;
            display: flex; align-items: center; justify-content: center; flex-shrink: 0;
        }}
        .badge {{ background: var(--accent); color: #fff; width: 18px; height: 18px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold; }}
        .handle {{ color: var(--text-secondary); font-size: 0.85rem; margin-left: 4px; }}
        .ref-badge {{ background: rgba(255, 122, 0, 0.15); color: var(--ref-badge); font-size: 0.75rem; padding: 2px 6px; border-radius: 8px; margin-left: 6px; }}
        .thread-meta {{ display: flex; flex-wrap: wrap; gap: 1rem; padding-top: 0.75rem; border-top: 1px solid var(--card-border); font-size: 0.9rem; color: var(--text-secondary); }}
        .tweet-card, .requote-card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 1.25rem;
            margin-bottom: 1rem;
        }}
        .tweet-card-header, .requote-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; font-size: 0.85rem; color: var(--text-secondary); }}
        .tweet-num {{ background: rgba(29, 155, 240, 0.12); color: var(--accent); padding: 2px 8px; border-radius: 12px; font-weight: 600; }}
        .tweet-body, .comment-body {{ font-size: 1rem; line-height: 1.6; margin-bottom: 0.75rem; white-space: pre-wrap; word-break: break-word; }}
        .tweet-media-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 8px; margin-bottom: 1rem; border-radius: 12px; overflow: hidden; }}
        .tweet-img, .tweet-video {{ width: 100%; max-height: 480px; object-fit: cover; border-radius: 8px; display: block; }}
        .quote-card {{ background: var(--quote-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 0.85rem 1rem; margin-bottom: 1rem; }}
        .tweet-footer, .comment-footer {{ display: flex; justify-content: space-between; align-items: center; padding-top: 0.6rem; border-top: 1px solid var(--card-border); font-size: 0.82rem; color: var(--text-secondary); }}
        .tweet-link {{ color: var(--accent); text-decoration: none; font-weight: 500; }}

        /* ── Comment Thread Layout (Twitter/Reddit-style visual nesting) ── */
        .comment-thread-root {{
            margin-bottom: 1.5rem;
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 1.25rem;
        }}
        .comment-thread-reply {{
            margin-top: 0.85rem;
            position: relative;
        }}
        .comment-layout {{
            display: flex;
            gap: 0.85rem;
            align-items: flex-start;
        }}
        .comment-left-col {{
            display: flex;
            flex-direction: column;
            align-items: center;
            flex-shrink: 0;
            width: 36px;
        }}
        .comment-avatar {{
            width: 36px; height: 36px; border-radius: 50%; object-fit: cover;
            flex-shrink: 0; display: block;
        }}
        .comment-avatar-placeholder {{
            width: 36px; height: 36px; border-radius: 50%; background: var(--accent);
            color: #fff; font-weight: bold; font-size: 0.9rem;
            display: flex; align-items: center; justify-content: center; flex-shrink: 0;
        }}
        .thread-line {{
            width: 2px;
            flex: 1;
            min-height: 20px;
            background: rgba(29, 155, 240, 0.4);
            margin-top: 6px;
            border-radius: 1px;
        }}
        .comment-right-col {{
            flex: 1;
            min-width: 0;
        }}
        .comment-thread-reply .comment-right-col {{
            background: rgba(21, 24, 28, 0.6);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 0.9rem 1rem;
        }}
        .comment-meta {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.35rem 0.5rem;
            margin-bottom: 0.5rem;
            font-size: 0.85rem;
        }}
        .comment-author {{ font-weight: 700; color: var(--text-primary); }}
        .comment-date {{ color: var(--text-secondary); font-size: 0.8rem; margin-left: auto; }}
        .replies-container {{
            margin-left: 1.25rem;
            border-left: 2px solid rgba(29, 155, 240, 0.4);
            padding-left: 1rem;
            margin-top: 0.75rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
        }}
        .reply-branch-tag {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            font-size: 0.75rem;
            color: var(--accent);
            background: rgba(29, 155, 240, 0.1);
            padding: 2px 6px;
            border-radius: 6px;
            margin-bottom: 0.35rem;
            font-weight: 600;
        }}

        .section-container {{ margin-top: 2.5rem; padding-top: 1.5rem; border-top: 2px dashed var(--card-border); }}
        .section-title {{ font-size: 1.3rem; margin-bottom: 1.25rem; }}
        .requote-badge {{ font-size: 0.8rem; font-weight: 600; padding: 3px 8px; border-radius: 10px; }}
        .badge-single {{ background: rgba(29, 155, 240, 0.15); color: var(--accent); }}
        .badge-thread {{ background: rgba(120, 86, 255, 0.18); color: var(--thread-badge); }}
        .sub-num {{ color: var(--thread-badge); font-weight: bold; }}
        .requote-stream {{ display: flex; flex-direction: column; gap: 0.75rem; margin-top: 0.5rem; }}
        .requote-item {{ background: var(--quote-bg); border: 1px solid var(--card-border); padding: 0.85rem; border-radius: 10px; }}
        .requote-item-footer {{ display: flex; justify-content: space-between; font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.5rem; }}
        .requote-comments {{ margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--card-border); }}
        .requote-comments-label {{ font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.75rem; font-weight: 600; }}
    </style>
</head>

<body>
    <div class="container">
        <header class="header-card">
            <div class="author-box">
                {avatar_html}
                <div>
                    <h2>{html.escape(author.name)} {verified_badge}</h2>
                    <a href="{author.profile_url}" target="_blank" class="handle">@{html.escape(author.screen_name)}</a>
                </div>
            </div>
            <div class="thread-meta">
                <span><strong>{thread.tweet_count}</strong> Main Tweets</span>
                <span><strong>{thread.comment_count}</strong> Comments</span>
                <span><strong>{thread.requote_count}</strong> Requotes</span>
                <span><strong>{thread.total_likes:,}</strong> Likes</span>
            </div>
        </header>
        <main>
            <section id="main-thread">
                <h3 class="section-title">🧵 Main Thread ({thread.tweet_count} Tweets)</h3>
                {"".join(tweets_html)}
            </section>
            <section class="section-container" id="comments-section">
                <h3 class="section-title">💬 Comments & Discussion Tree ({thread.comment_count})</h3>
                {comments_html}
            </section>
            <section class="section-container" id="requotes-section">
                <h3 class="section-title">🔁 Requotes & Quote Threads ({thread.requote_count})</h3>
                {requotes_html}
            </section>
        </main>
    </div>
</body>
</html>'''
        return full_html

    @classmethod
    def export_all(cls, thread: Thread, base_output_dir: str = "output") -> Dict[str, str]:
        """
        Exports the entire thread, comments, and requotes into the context-first hierarchy:
        output/{username}/{content_title}_{tweet_id}/
          ├── thread.md
          ├── comments.md
          ├── requotes.md
          ├── full_archive.md
          ├── thread_data.json  (Mega unified JSON)
          ├── thread_data.txt
          └── thread_view.html
        """
        target_dir, folder_name = cls.get_output_paths(thread, base_output_dir)
        os.makedirs(target_dir, exist_ok=True)

        saved_files = {"folder": target_dir}

        # 1. Dedicated thread.md
        thread_md_path = os.path.join(target_dir, "thread.md")
        with open(thread_md_path, "w", encoding="utf-8") as f:
            f.write(cls.to_thread_markdown(thread))
        saved_files["thread_md"] = thread_md_path

        # 2. Dedicated comments.md
        comments_md_path = os.path.join(target_dir, "comments.md")
        with open(comments_md_path, "w", encoding="utf-8") as f:
            f.write(cls.to_comments_markdown(thread))
        saved_files["comments_md"] = comments_md_path

        # 3. Dedicated requotes.md
        requotes_md_path = os.path.join(target_dir, "requotes.md")
        with open(requotes_md_path, "w", encoding="utf-8") as f:
            f.write(cls.to_requotes_markdown(thread))
        saved_files["requotes_md"] = requotes_md_path

        # 4. Comprehensive full_archive.md
        full_md_path = os.path.join(target_dir, "full_archive.md")
        with open(full_md_path, "w", encoding="utf-8") as f:
            f.write(cls.to_full_archive_markdown(thread))
        saved_files["full_archive_md"] = full_md_path

        # 5. Machine-readable Mega thread_data.json
        json_path = os.path.join(target_dir, "thread_data.json")
        with open(json_path, "w", encoding="utf-8") as f:
            f.write(cls.to_json(thread))
        saved_files["json"] = json_path

        # 6. Plain text thread_data.txt
        txt_path = os.path.join(target_dir, "thread_data.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(cls.to_text(thread))
        saved_files["text"] = txt_path

        # 7. Standalone interactive thread_view.html
        html_path = os.path.join(target_dir, "thread_view.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(cls.to_html(thread))
        saved_files["html"] = html_path

        return saved_files

    @classmethod
    def download_media(cls, thread: Thread, output_dir: Optional[str] = None) -> List[str]:
        """
        Downloads all attached photos and videos into a media/ subfolder.
        """
        if not output_dir:
            target_dir, _ = cls.get_output_paths(thread)
            output_dir = os.path.join(target_dir, "media")

        os.makedirs(output_dir, exist_ok=True)
        downloaded = []
        headers = {"User-Agent": "Mozilla/5.0"}

        for tweet in thread.tweets:
            for i, media in enumerate(tweet.media, 1):
                url = media.url
                if not url:
                    continue

                ext = ".jpg"
                if media.type == "video":
                    ext = ".mp4"
                elif ".png" in url.lower():
                    ext = ".png"
                elif ".gif" in url.lower():
                    ext = ".gif"
                elif ".webp" in url.lower():
                    ext = ".webp"

                filename = f"tweet_{tweet.position_in_thread:02d}_{tweet.id}_m{i}{ext}"
                filepath = os.path.join(output_dir, filename)

                try:
                    r = requests.get(url, headers=headers, stream=True, timeout=15)
                    if r.status_code == 200:
                        with open(filepath, "wb") as f:
                            for chunk in r.iter_content(chunk_size=16384):
                                f.write(chunk)
                        downloaded.append(filepath)
                except Exception:
                    pass

        return downloaded
