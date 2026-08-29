# System Architecture — Hard Construction Rules

> **Document Purpose**: This file is the single source of truth for any AI agent, developer, or contributor working on this codebase. It defines inviolable rules, architectural invariants, data flow, and behavioral contracts. Read this before writing any code.

---

## 1. Core Mission

Build a **zero-authentication** Twitter/X thread scraper that captures the complete public ecosystem of any post — the thread itself, all nested comment discussions, and all quote tweets — into a single unified output folder with machine-readable and human-readable exports.

### Non-Negotiable Constraints

| Constraint | Rule |
|-----------|------|
| **No authentication** | Must never require Twitter login, API keys, OAuth tokens, or browser cookies. If a data source starts requiring auth, fall back to the next provider — never prompt the user for credentials. |
| **No headless browsers** | No Selenium, Playwright, or Puppeteer. HTTP requests only (`requests` library). SSR stream decoding and public API proxies are the extraction method. |
| **No external databases** | All output is file-based. JSON, Markdown, HTML, plain text, and downloaded media files. No SQLite, no Redis, no Postgres. |
| **Idempotent re-runs** | Running the scraper twice on the same URL overwrites the same folder — no duplicate folders, no timestamp-suffixed directories. |

---

## 2. Output Directory — The Law of ONE

### Hierarchy

```
output/
  └── {username}/                              ← ONE folder per author
        └── {sanitized_content_title}_{tweet_id}/   ← ONE folder per post
              ├── thread.md
              ├── comments.md
              ├── requotes.md
              ├── full_archive.md
              ├── thread_data.json     (Mega JSON)
              ├── thread_data.txt
              ├── thread_view.html
              └── media/
```

### Hard Rules

1. **ONE folder per username** — `output/{screen_name}/`. Never duplicate user folders.
2. **ONE subfolder per root post** — Contains ALL artifacts for that post: thread, comments, requotes, media. There is NEVER a second folder for a requote of the same post.
3. **Context-first naming** — Folder name format is `{sanitized_title}_{tweet_id}`. The human-readable content title comes FIRST. The numeric Tweet ID comes LAST. Rationale: humans browse file explorers by reading the start of folder names, not memorizing 19-digit numbers.
4. **Title sanitization** — Strip `\/*?:"<>|#@,;!.` characters, replace whitespace with `_`, truncate to 55 characters max. Always append `_{tweet_id}` at the end.

---

## 3. Data Taxonomy — Three Categories, Never Conflated

Every tweet discovered during a scrape is classified into **exactly one** of three categories. A tweet NEVER appears in more than one category.

### 3A. Main Thread (`thread.tweets`)

**Definition**: The sequential direct reply chain authored by the thread's original author, starting at the root tweet.

**Reconstruction Algorithm** — Strict Linear Chain:
```
1. Start at root_tweet (the oldest tweet in the conversation by the author)
2. current = root_tweet
3. WHILE True:
4.   Find candidate WHERE:
5.     - candidate.author == main_author
6.     - candidate.replying_to_status_id == current.id
7.     - candidate.quote IS NULL  ← NOT a quote tweet
8.     - candidate.id NOT IN visited
9.   IF found: append to chain, current = candidate
10.  ELSE: break
```

**Critical Invariant**: If the author posted a 4-tweet thread and then separately quote-tweeted their own Tweet #4 with a 7-tweet follow-up, the main thread contains EXACTLY 4 tweets. The 7-tweet quote thread is classified as a Requote. These must NEVER be merged.

### 3B. Comments (`thread.comment_tree`)

**Definition**: Tweets by ANY user (including the author) that are direct or nested replies to main thread tweets, AND are not themselves part of a quote thread being tracked as a Requote.

**Structure**: A recursive tree of `CommentNode` objects, where each node contains a `Tweet` and a list of child `CommentNode` replies. Supports arbitrary depth:

```
Level 1: @user_a replies to Main Tweet #2
  └── Level 2: @user_b replies to @user_a
        └── Level 3: @author replies to @user_b
              └── Level 4: @user_b replies to @author
```

**Discovery Rule**: Comments are found via **multi-wave iterative SSR expansion**:
```
Wave 1: Crawl SSR streams of all main thread tweets → discover Level 1 comments
Wave 2: Crawl SSR streams of Level 1 comments that have replies > 0 → discover Level 2
Wave 3: Crawl SSR streams of Level 2 comments → discover Level 3
...repeat up to max_waves (default: 5)
```

This is NOT a single-pass crawl. Each wave discovers new tweets, and the next wave expands those newly discovered tweets. This is how Aditya's reply to @julymemo's comment is found — it only exists in julymemo's SSR stream, not the main thread's.

### 3C. Requotes (`thread.requotes`)

**Definition**: Quote Tweets referencing any tweet in the main thread. A requote can be:
- **Single Requote**: One standalone tweet embedding a quoted tweet
- **Quote Thread**: Multiple sequential tweets by the same author, where the first one embeds a quoted tweet and the rest are direct reply continuations

**Required Metadata on every Requote**:
| Field | Description |
|-------|------------|
| `root_quote_id` | Tweet ID of the first (or only) quote tweet |
| `quoted_status_id` | Tweet ID of the EXACT main thread tweet being quoted |
| `quoted_tweet_position` | Integer position in the main thread (e.g., `4` for Tweet #4) |
| `quoted_tweet_snippet` | First ~60 characters of the quoted tweet's text |
| `is_thread` | Boolean — true if the requote is a multi-tweet thread |
| `tweets` | Ordered list of all tweets in the quote thread |
| `comments` | Nested comment tree on the requote itself |

**Unrolling Algorithm**:
```
1. Start with the root quote tweet
2. Fetch its SSR stream
3. Collect all tweets by the same author in the SSR stream
4. Sort by (timestamp, id) → sequential quote thread
5. Multi-wave expand to find comments ON the requote
6. Build nested comment tree for those comments
```

---

## 4. Mega JSON Schema (`thread_data.json`)

The Mega JSON is the machine-readable single source of truth. Every other file format (Markdown, HTML, text) is derived from this data.

```json
{
  "thread_info": {
    "root_id": "string",
    "conversation_id": "string",
    "title": "string (first line of root tweet, ≤80 chars)",
    "author": { "name", "screen_name", "avatar_url", "verified", ... },
    "source_url": "string",
    "fetched_at": "ISO 8601 timestamp",
    "stats": {
      "main_tweets_count": "int",
      "total_comments_count": "int",
      "top_level_comments_count": "int",
      "total_requotes_count": "int",
      "single_requotes_count": "int",
      "thread_requotes_count": "int",
      "total_likes": "int",
      "total_retweets": "int",
      "total_media_count": "int"
    }
  },
  "main_thread": [ /* Ordered array of Tweet objects */ ],
  "comments_tree": [ /* Recursive CommentNode objects */ ],
  "all_comments_flat": [ /* Flat array of all comment Tweets */ ],
  "requotes": [ /* Array of Requote objects with nested comments */ ]
}
```

---

## 5. Data Extraction Pipeline

### Provider Fallback Chain (per tweet)

```
1. FixTweet API (api.fxtwitter.com)     ← Richest metadata, most reliable
2. Twitter Syndication CDN (cdn.syndication.twimg.com)  ← Direct from Twitter
3. VxTwitter API (api.vxtwitter.com)    ← Minimal fallback
```

Each provider is tried in order. First success wins. 404 from any provider = tweet deleted/private, skip entirely.

### SSR Stream Decoding

Twitter's server-side rendered HTML contains `relayRecords` in inline `<script>` tags. These embed base64-encoded Tweet IDs:
- `VHdlZXQ6` prefix → decodes to `Tweet:{id}`
- `Tm90ZVR3ZWV0Oj` prefix → decodes to `NoteTweet:{id}`

This is the primary discovery mechanism for thread continuations and conversation participants. It works without authentication.

### Thread Reconstruction Pipeline

```
Step 1: UPWARD ANCESTRY TRAVERSAL
  → Follow replying_to_status_id upward to find the root tweet

Step 2: SSR STREAM DISCOVERY
  → Decode base64 Tweet IDs from root tweet's HTML page

Step 3: TIMELINE TRAVERSAL
  → Fetch author's public syndication timeline for conversation continuations

Step 4: EXTRA QUOTE URL INJECTION
  → User can pass --quotes URLs to force-include known quote threads

Step 5: MULTI-WAVE ITERATIVE COMMENT CRAWLING
  → Expand SSR streams of all tweets with replies > 0
  → Repeat for newly discovered comments (up to 5 waves)

Step 6: STRICT LINEAR MAIN THREAD RECONSTRUCTION
  → Walk root → child → grandchild by same author, no quote tweets

Step 7: REQUOTE IDENTIFICATION & UNROLLING
  → Find all tweets with quote.id ∈ main_thread_ids
  → Unroll each into full quote thread + its own comment tree

Step 8: COMMENT TREE CONSTRUCTION
  → Build recursive CommentNode tree from flat comment list
  → Exclude tweets already classified as main thread or requote
```

---

## 6. Concurrency Model

- **`ThreadPoolExecutor`** with configurable `max_workers` (default: 8)
- Used for:
  - Batch tweet fetching (`fetch_tweets_batch`)
  - Parallel SSR stream crawling during comment expansion waves
- **NOT used for**: Sequential chain reconstruction (must be serial to maintain ordering guarantees)

### Rate Limiting & Resilience

- Each provider retried up to `max_retries` (default: 3) with exponential backoff (`0.3s * attempt`)
- User-Agent rotation across 4 browser fingerprints
- Per-request timeout of 12 seconds
- SSR stream fetching gracefully degrades (empty list on failure, never throws)

---

## 7. Export File Contracts

### `thread.md`
- Header with author info, date, stats, and source URL
- Sequential sections: `### Tweet N of M` for each main thread tweet
- Media links, quote embeds, and per-tweet engagement metrics
- MUST contain exactly the same number of tweets as `thread_info.stats.main_tweets_count` in the Mega JSON

### `comments.md`
- Header with target thread reference and comment counts
- If comment tree is available: rendered as recursive indented tree with `[Level N]` depth badges
- If only flat comments: rendered as sequential cards
- Comments on requotes appear in `requotes.md`, NOT duplicated here

### `requotes.md`
- Header with requote counts (single vs thread)
- Each requote section includes:
  - `📌 Quoted Tweet #N of Main Thread` — explicit pointer
  - Quoted tweet snippet in italics
  - Unrolled quote thread with `[M/N]` position markers
  - Nested comment tree on the requote (if any)

### `full_archive.md`
- Concatenation of `thread.md` + `comments.md` + `requotes.md` with section dividers

### `thread_data.json`
- The Mega JSON (§4 above). Everything else is derived from this.

### `thread_data.txt`
- Plain text, no markup. Suitable for grep/search/LLM context injection.

### `thread_view.html`
- Standalone self-contained HTML file (all CSS inline, no external dependencies)
- Dark mode by default, light mode via `prefers-color-scheme`
- Three sections: Main Thread cards, Comments tree, Requotes with badges
- Every tweet links back to X via `View on X ↗`

### `media/`
- Downloaded photos as `.jpg`/`.png`, videos as `.mp4`
- Filename format: `tweet_{position:02d}_{tweet_id}_m{media_index}{ext}`
- Only created when `--download-media` flag is passed

---

## 8. CLI Interface Contract

```
python main.py <URL> [OPTIONS]

Required:
  URL                     Twitter/X tweet URL or raw Tweet ID

Options:
  --quotes URL [URL ...]  Additional quote tweet URLs to bundle into the same post
  -o, --output-dir DIR    Base output directory (default: output)
  -d, --download-media    Download attached photos and videos
  -b, --batch FILE        Text file with one URL per line
  --max-comments N        Maximum comments to crawl (default: 300)
  --workers N             Concurrent threads (default: 8)
  -q, --quiet             Suppress terminal preview
  -v, --verbose           Debug logging
```

---

## 9. Scalability Design Notes

### For Viral Threads (100s of comments)

- Comment crawling is **wave-bounded** (max 5 waves) and **count-bounded** (`--max-comments`, default 300)
- Each wave expands at most 40 candidates
- SSR streams are fetched concurrently via ThreadPoolExecutor
- The recursive `CommentNode` tree supports arbitrary depth — the tree construction is O(N) where N = total comments

### For Batch Processing (many threads)

- `--batch` mode reads URLs from a file, processes sequentially
- Each thread gets its own subfolder — no cross-contamination
- Session object is reused across requests for connection pooling

### Known Limitations

- **Quote tweet discovery**: Twitter does NOT include quote tweets in the quoted tweet's SSR stream. Quote tweets must be either (a) discovered via author timeline, (b) found in comment SSR streams, or (c) explicitly passed via `--quotes`.
- **Private/deleted tweets**: Silently skipped. The scraper never errors on individual missing tweets.
- **Rate limits**: Excessive concurrent requests may trigger 429s. The scraper retries with backoff but does not implement token bucket throttling.

---

## 10. File Dependency Graph

```
main.py
  └── cli.py (CLI interface, Rich terminal rendering)
        ├── scraper.py (TwitterThreadScraper — all extraction logic)
        │     └── models.py (Tweet, Author, MediaItem, CommentNode, Requote, Thread)
        └── exporters.py (ThreadExporter — all serialization and file I/O)
              └── models.py
```

No circular dependencies. `models.py` is leaf. `scraper.py` and `exporters.py` both depend on `models.py` but not on each other. `cli.py` orchestrates both.
