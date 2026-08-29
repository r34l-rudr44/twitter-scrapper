"""
Twitter/X Thread Scraper - Main Entry Point.
Run directly as CLI or import the scraper in your own Python projects.
"""

import sys
from models import Thread, Tweet, Author, MediaItem, QuoteTweet
from scraper import TwitterThreadScraper
from exporters import ThreadExporter


def scrape_thread(url_or_id: str, verbose: bool = False) -> Thread:
    """Convenience function to scrape a thread in Python scripts."""
    scraper = TwitterThreadScraper(verbose=verbose)
    return scraper.scrape_thread(url_or_id)


if __name__ == "__main__":
    from cli import main
    main()
