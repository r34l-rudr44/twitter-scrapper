# Twitter/X Thread Scraper (Zero-Auth, Scalable & Structured)

A high-capacity, zero-auth Python engine and CLI to extract **Twitter/X threads, multi-level nested comment/reply trees, and requote threads** without requiring logins, cookies, or API keys.

---

## 📁 Structured Output Organization (1 Folder Per Post)

Exports are organized hierarchically by **author username** and **human-readable topic title** (context first, Tweet ID at the end):

```
output/
  └── {username}/                                 <-- Folder for each author (e.g. adityaarpitha, elonmusk, naval)
        └── {content_title}_{tweet_id}/           <-- Single unified subfolder per post
              ├── thread.md                       <-- Clean unrolled main author thread
              ├── comments.md                     <-- Multi-level nested comments tree (Level 1 -> Level 2 -> Level 3...)
              ├── requotes.md                     <-- Requotes tied to exact quoted tweets & unrolled quote threads
              ├── full_archive.md                 <-- Comprehensive unified markdown archive
              ├── thread_data.json                <-- Mega JSON schema unifying the entire thread ecosystem
              ├── thread_data.txt                 <-- Clean plain text reading format
              ├── thread_view.html                <-- Interactive standalone web viewer with nested trees
              └── media/                          <-- Downloaded high-res photos & MP4 videos
```

---

## ⚡ Key Architectural Features

- 🛡️ **Zero-Auth Extraction**: Combines SSR stream base64 decoding (`VHdlZXQ6` / `Tm90ZVR3ZWV0Oj`) with FixTweet, Twitter Syndication CDN, and VxTwitter fallback.
- 🧵 **Strict Linear Main Thread Reconstruction**: Accurately walks parent→child links starting at the root tweet, ensuring main threads are never conflated with quote threads.
- 🌳 **Multi-Level Nested Reply Trees**: Iterative multi-wave crawler discovers replies-to-replies (`Level 1 -> Level 2 -> Level 3...`) preserving full conversational context.
- 🔁 **Exact Quoted-Tweet Tracking**: Tracks which exact tweet in the thread was quoted (`📌 Quoted Tweet #4 ("4) Relational")`) and unrolls multi-tweet quote sequences (`[1/N]`, `[2/N]`, etc.).
- 📦 **Mega Unified JSON (`thread_data.json`)**: Complete machine-readable payload containing `thread_info`, `main_thread`, `comments_tree`, and `requotes`.
- ⚡ **Concurrent Crawling (`ThreadPoolExecutor`)**: Rapid multi-threaded SSR extraction for large/viral discussions.

---

## 🚀 Quick Start

### 1. Installation

```bash
git clone <repo-url>
cd twitter_scrap
pip install -r requirements.txt
```

---

## 💻 CLI Usage

### Basic Thread Scrape

```bash
# Scrapes thread, nested comments tree, and requotes into output/{username}/{title}_{tweet_id}/
python main.py "https://x.com/adityaarpitha/status/2092873325420961971"
```

### Bundle Specific Requote Threads into the Same Post Folder

```bash
python main.py "https://x.com/adityaarpitha/status/2092873325420961971" --quotes "https://x.com/adityaarpitha/status/2092904243166683548"
```

### High-Capacity Scrapes with Media Downloads

```bash
# Large viral thread with deep comment crawling
python main.py "https://x.com/naval/status/1002103360646823936" --max-comments 500 --workers 12

# Download all photos and highest-quality MP4 videos
python main.py "https://x.com/elonmusk/status/1349129669258448897" --download-media
```

### Batch Mode

```bash
# Provide a text file with one URL or ID per line
python main.py --batch urls.txt --download-media
```

---

## 🌐 Interactive Web UI

Launch the local web dashboard for interactive in-browser thread scraping and browsing:

```bash
python web_app.py
```
Open `http://127.0.0.1:8000` in your browser.

---

## 🐍 Python API Usage

```python
from scraper import TwitterThreadScraper
from exporters import ThreadExporter

scraper = TwitterThreadScraper(max_workers=8)

# Scrape thread, recursive comment tree, and quote threads
thread = scraper.scrape_thread(
    "https://x.com/adityaarpitha/status/2092873325420961971",
    extra_quote_urls=["https://x.com/adityaarpitha/status/2092904243166683548"],
    max_comments=300
)

print(f"Main Tweets: {thread.tweet_count}")
print(f"Total Comments: {thread.comment_count}")
print(f"Requotes: {thread.requote_count}")

# Export all structured files
saved = ThreadExporter.export_all(thread, base_output_dir="output")
print(f"Saved to: {saved['folder']}")
```

---

## 🧪 Running Unit Tests

```bash
python -m unittest tests/test_scraper.py
```

---

## 📐 Architecture & System Contracts

For detailed data models, invariants, and pipeline specifications, see [`system-arch.md`](system-arch.md).
