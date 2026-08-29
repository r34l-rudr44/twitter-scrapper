"""
Command-line interface (CLI) for Twitter/X Thread Scraper (Unified Single-Folder Architecture).
Renders colored terminal trees, exact quoted tweet tracking, and exports into:
output/{username}/{content_title}_{tweet_id}/
  ├── thread.md
  ├── comments.md
  ├── requotes.md
  ├── full_archive.md
  ├── thread_data.json
  ├── thread_data.txt
  └── thread_view.html
"""

import sys
import os
import argparse
from typing import Optional, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.text import Text
from rich.tree import Tree
from rich import box

from models import Thread, Tweet, Requote, CommentNode
from scraper import TwitterThreadScraper
from exporters import ThreadExporter

console = Console()


def _add_comment_to_rich_tree(node: CommentNode, rich_tree: Tree) -> None:
    """Recursively adds CommentNodes to a Rich visual terminal tree."""
    t = node.tweet
    author = t.author
    label = f"[bold cyan]@{author.screen_name}[/bold cyan] [dim]({author.name})[/dim] [green][L{node.depth}][/green] [dim]• ❤️ {t.likes:,} likes • {t.formatted_date}[/dim]\n[white]{t.text}[/white]"
    branch = rich_tree.add(label)
    for sub in node.replies:
        _add_comment_to_rich_tree(sub, branch)


def display_thread(thread: Thread) -> None:
    """Renders the entire thread, nested comments tree, and requotes beautifully using Rich."""
    author = thread.author
    
    # Thread Summary Header
    header_text = Text()
    header_text.append(f"{author.name}", style="bold white")
    if author.verified:
        header_text.append(" ✔", style="bold cyan")
    header_text.append(f" (@{author.screen_name})\n", style="dim cyan")
    header_text.append(f"{thread.title}\n\n", style="bold yellow")
    header_text.append(
        f"📊 Main Tweets: {thread.tweet_count}  |  💬 Total Comments: {thread.comment_count}  |  🔁 Requotes: {thread.requote_count}  |  ❤️ Total Likes: {thread.total_likes:,}\n",
        style="dim"
    )
    header_text.append(f"🔗 Link: {thread.source_url}", style="blue underline")

    console.print(Panel(header_text, title="[bold cyan]Twitter / X Thread Archive[/bold cyan]", border_style="cyan", box=box.ROUNDED))

    # 1. Main Thread Tweets
    for tweet in thread.tweets:
        card_content = [tweet.text]

        if tweet.media:
            media_lines = []
            for i, m in enumerate(tweet.media, 1):
                icon = "📷" if m.type == "photo" else "🎬"
                media_lines.append(f"{icon} [link={m.url}]Media {i} ({m.type})[/link]")
            card_content.append("\n" + "  •  ".join(media_lines))

        if tweet.quote:
            card_content.append(f"\n> [bold]Quoting @{tweet.quote.author_screen_name}:[/bold]\n> {tweet.quote.text}")

        metrics_parts = []
        if tweet.likes:
            metrics_parts.append(f"❤️ {tweet.likes:,}")
        if tweet.retweets:
            metrics_parts.append(f"🔁 {tweet.retweets:,}")
        if tweet.replies:
            metrics_parts.append(f"💬 {tweet.replies:,}")
        if tweet.views:
            metrics_parts.append(f"👁️ {tweet.views:,}")
        
        footer = f"[dim]{tweet.formatted_date}[/dim]"
        if metrics_parts:
            footer += f"  •  [dim]{'  '.join(metrics_parts)}[/dim]"

        card_text = "\n".join(card_content) + f"\n\n{footer}"
        
        console.print(Panel(
            card_text,
            title=f"[bold green]Main Tweet {tweet.position_in_thread} of {thread.tweet_count}[/bold green]",
            subtitle=f"[dim][link={tweet.url}]Open on X[/link][/dim]",
            subtitle_align="right",
            border_style="green" if tweet.position_in_thread == 1 else "bright_blue",
            box=box.ROUNDED
        ))

    # 2. Hierarchical Comments Tree
    if thread.comment_tree:
        console.print(f"\n[bold yellow]💬 Nested Comments & Discussion Tree ({thread.comment_count} total comments captured):[/bold yellow]")
        for i, top_node in enumerate(thread.comment_tree[:10], 1):
            tree_root = Tree(f"[bold yellow]Discussion #{i}[/bold yellow]")
            _add_comment_to_rich_tree(top_node, tree_root)
            console.print(tree_root)
            console.print("")
    elif thread.comments:
        console.print(f"\n[bold yellow]💬 Public Comments ({len(thread.comments)} captured):[/bold yellow]")
        for c in thread.comments[:10]:
            c_text = f"[bold cyan]@{c.author.screen_name}[/bold cyan] ({c.formatted_date}):\n{c.text}\n\n[dim]❤️ {c.likes:,} likes  •  [link={c.url}]View Reply[/link][/dim]"
            console.print(Panel(c_text, border_style="dim", box=box.ROUNDED))

    # 3. Requotes & Quote Threads
    if thread.requotes:
        console.print(f"\n[bold magenta]🔁 Requotes & Quote Threads ({len(thread.requotes)} captured):[/bold magenta]")
        for req in thread.requotes:
            tag = f"[bold magenta]🧵 {req.tweet_count}-Tweet Quote Thread[/bold magenta]" if req.is_thread else "[cyan]📌 Single Requote[/cyan]"
            quoted_info = f" [bold yellow](Quoting Tweet #{req.quoted_tweet_position})[/bold yellow]" if req.quoted_tweet_position else ""
            req_lines = [f"{tag}{quoted_info} by [bold]@{req.author.screen_name}[/bold] (Total ❤️ {req.total_likes:,}):\n"]
            if req.quoted_tweet_snippet:
                req_lines.append(f"[dim]> Quoted: \"{req.quoted_tweet_snippet}\"[/dim]\n")
            for t in req.tweets:
                prefix = f"[dim][{t.position_in_thread}/{req.tweet_count}][/dim] " if req.is_thread else ""
                req_lines.append(f"{prefix}{t.text}")
            if req.comments:
                req_lines.append(f"\n[dim]  • {len(req.comments)} comment(s) on this requote[/dim]")
            req_panel_text = "\n".join(req_lines)
            console.print(Panel(req_panel_text, border_style="magenta" if req.is_thread else "blue", box=box.ROUNDED))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="High-capacity scalable Twitter/X thread, comments tree, and requote scraper without logins.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py "https://x.com/adityaarpitha/status/2092873325420961971" --quotes "https://x.com/adityaarpitha/status/2092904243166683548"
  python main.py "https://x.com/naval/status/1002103360646823936" --max-comments 500
  python main.py "1349129669258448897" --download-media
        """
    )

    parser.add_argument("url", nargs="?", help="Twitter / X tweet or thread URL (or Tweet ID)")
    parser.add_argument("-o", "--output-dir", default="output", help="Base output directory (default: output)")
    parser.add_argument("-d", "--download-media", action="store_true", help="Download high-resolution photos and videos")
    parser.add_argument("-b", "--batch", help="Path to text file containing list of URLs/IDs (one per line)")
    parser.add_argument("--quotes", "-q-url", nargs="*", default=None, help="Optional quote tweet URLs/IDs to bundle into the same post folder")
    parser.add_argument("--max-comments", type=int, default=300, help="Maximum comments to crawl across nested levels (default: 300)")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent worker threads for batch fetching (default: 8)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress terminal preview, show file export results only")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()

    urls_to_process = []
    if args.batch:
        if not os.path.exists(args.batch):
            console.print(f"[bold red]Error: Batch file '{args.batch}' not found.[/bold red]")
            sys.exit(1)
        with open(args.batch, "r", encoding="utf-8") as f:
            urls_to_process = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    elif args.url:
        urls_to_process = [args.url]
    else:
        parser.print_help()
        sys.exit(1)

    scraper = TwitterThreadScraper(max_workers=args.workers, verbose=args.verbose)

    for i, target_url in enumerate(urls_to_process, 1):
        if len(urls_to_process) > 1:
            console.print(f"\n[bold magenta]Processing [{i}/{len(urls_to_process)}]: {target_url}[/bold magenta]")

        try:
            with console.status(f"[bold green]Fetching thread, nested comments & requotes from {target_url}...[/bold green]"):
                thread = scraper.scrape_thread(target_url, extra_quote_urls=args.quotes, max_comments=args.max_comments)

            if not args.quiet:
                display_thread(thread)

            # Export structured user/tweet subfolder
            saved = ThreadExporter.export_all(thread, base_output_dir=args.output_dir)
            target_dir = saved["folder"]

            console.print(f"\n[bold green]✓ Unified into ONE single folder per post:[/bold green]")
            console.print(f"  📂 [cyan]{os.path.abspath(target_dir)}[/cyan]\n")
            console.print("  [bold white]Generated Artifacts:[/bold white]")
            console.print(f"  • [green]thread.md[/green]        : Main author thread unrolled ({thread.tweet_count} tweets)")
            console.print(f"  • [green]comments.md[/green]      : Nested comments & replies tree ({thread.comment_count} comments)")
            console.print(f"  • [green]requotes.md[/green]      : Requotes tied to exact quoted tweets ({thread.requote_count} requotes)")
            console.print(f"  • [green]full_archive.md[/green]  : Comprehensive unified archive")
            console.print(f"  • [green]thread_data.json[/green] : Mega JSON schema tying entire thread ecosystem together")
            console.print(f"  • [green]thread_data.txt[/green]  : Clean plain text format")
            console.print(f"  • [green]thread_view.html[/green] : Interactive standalone web viewer")

            # Handle media downloading
            if args.download_media:
                media_target_dir = os.path.join(target_dir, "media")
                if thread.total_media_count > 0:
                    with console.status("[bold green]Downloading high-resolution media attachments...[/bold green]"):
                        downloaded = ThreadExporter.download_media(thread, output_dir=media_target_dir)
                    console.print(f"\n  • [green]media/[/green]           : {len(downloaded)} media attachments downloaded")
                else:
                    console.print("\n  • [yellow]media/[/yellow]           : No media attachments in this thread")

        except Exception as e:
            console.print(f"[bold red]Error scraping '{target_url}': {e}[/bold red]")
            if args.verbose:
                import traceback
                traceback.print_exc()


if __name__ == "__main__":
    main()
