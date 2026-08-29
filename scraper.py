"""
Twitter/X Thread Scraper Core Engine (Unified Single-Folder Architecture with Strict Linear Thread Reconstruction).
Extracts complete Twitter/X threads, multi-level nested comment/reply trees,
and requote threads (single quotes & multi-tweet quote threads) without logins or API keys.
"""

import re
import html
import time
import json
import base64
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List, Tuple, Set
from datetime import datetime, timezone
import requests
from bs4 import BeautifulSoup

from models import Tweet, Author, MediaItem, QuoteTweet, Requote, CommentNode, Thread

logger = logging.getLogger("twitter_scraper")


class TwitterThreadScraper:
    """Zero-auth scalable Twitter/X thread extraction engine."""

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ]

    FX_API_BASE = "https://api.fxtwitter.com"
    VX_API_BASE = "https://api.vxtwitter.com"
    SYNDICATION_TWEET_BASE = "https://cdn.syndication.twimg.com/tweet-result"
    SYNDICATION_TIMELINE_BASE = "https://syndication.twitter.com/srv/timeline-profile/screen-name"

    def __init__(self, timeout: int = 12, max_retries: int = 3, max_workers: int = 8, verbose: bool = False):
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_workers = max_workers
        self.verbose = verbose
        self.session = requests.Session()
        self._ua_index = 0

    def _get_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        """Rotates browser User-Agents and sets standard request headers."""
        ua = self.USER_AGENTS[self._ua_index % len(self.USER_AGENTS)]
        self._ua_index += 1
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    @staticmethod
    def extract_tweet_info(url_or_id: str) -> Tuple[str, Optional[str]]:
        """
        Parses a URL or ID string and returns (tweet_id, screen_name).
        Supports x.com, twitter.com, fxtwitter.com, vxtwitter.com, fixupx.com, and raw IDs.
        """
        cleaned = url_or_id.strip()

        if re.fullmatch(r"\d{1,25}", cleaned):
            return cleaned, None

        patterns = [
            r"(?:twitter\.com|x\.com|fxtwitter\.com|vxtwitter\.com|fixupx\.com)\/(?:#!\/)?([a-zA-Z0-9_]{1,30})\/status(?:es)?\/(\d+)",
            r"(?:twitter\.com|x\.com|fxtwitter\.com|vxtwitter\.com|fixupx\.com)\/i\/web\/status\/(\d+)",
            r"(?:twitter\.com|x\.com|fxtwitter\.com|vxtwitter\.com|fixupx\.com)\/status\/(\d+)",
            r"status(?:es)?\/(\d+)"
        ]

        for pat in patterns:
            match = re.search(pat, cleaned, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    return groups[1], groups[0]
                elif len(groups) == 1:
                    return groups[0], None

        num_match = re.search(r"(\d{5,25})", cleaned)
        if num_match:
            return num_match.group(1), None

        raise ValueError(f"Could not extract a valid Tweet ID from input: '{url_or_id}'")

    def _fetch_fxtwitter(self, tweet_id: str) -> Optional[Tweet]:
        """Fetches tweet data via FixTweet API."""
        url = f"{self.FX_API_BASE}/status/{tweet_id}"
        for attempt in range(self.max_retries):
            try:
                r = self.session.get(url, headers=self._get_headers(), timeout=self.timeout)
                if r.status_code == 200:
                    data = r.json()
                    tweet_raw = data.get("tweet")
                    if tweet_raw:
                        return self._parse_fxtwitter_tweet(tweet_raw)
                elif r.status_code == 404:
                    return None
            except Exception as e:
                if self.verbose:
                    logger.debug(f"[FixTweet] Attempt {attempt+1} failed for ID {tweet_id}: {e}")
                time.sleep(0.3 * (attempt + 1))
        return None

    def _fetch_syndication(self, tweet_id: str) -> Optional[Tweet]:
        """Fetches tweet data via Twitter's syndication CDN endpoint."""
        url = f"{self.SYNDICATION_TWEET_BASE}?id={tweet_id}&lang=en&token=1"
        for attempt in range(self.max_retries):
            try:
                r = self.session.get(url, headers=self._get_headers(), timeout=self.timeout)
                if r.status_code == 200:
                    data = r.json()
                    return self._parse_syndication_tweet(data)
                elif r.status_code == 404:
                    return None
            except Exception as e:
                if self.verbose:
                    logger.debug(f"[Syndication] Attempt {attempt+1} failed for ID {tweet_id}: {e}")
                time.sleep(0.3 * (attempt + 1))
        return None

    def _fetch_vxtwitter(self, tweet_id: str) -> Optional[Tweet]:
        """Fetches tweet data via VxTwitter API."""
        url = f"{self.VX_API_BASE}/Twitter/status/{tweet_id}"
        for attempt in range(self.max_retries):
            try:
                r = self.session.get(url, headers=self._get_headers(), timeout=self.timeout)
                if r.status_code == 200:
                    data = r.json()
                    return self._parse_vxtwitter_tweet(data, tweet_id)
                elif r.status_code == 404:
                    return None
            except Exception as e:
                if self.verbose:
                    logger.debug(f"[VxTwitter] Attempt {attempt+1} failed for ID {tweet_id}: {e}")
                time.sleep(0.3 * (attempt + 1))
        return None

    def fetch_tweet(self, tweet_id: str) -> Optional[Tweet]:
        """
        Fetches a single tweet with automatic multi-tier fallback.
        FixTweet -> Syndication Twimg -> VxTwitter
        """
        tweet = self._fetch_fxtwitter(tweet_id)
        if tweet:
            return tweet

        tweet = self._fetch_syndication(tweet_id)
        if tweet:
            return tweet

        tweet = self._fetch_vxtwitter(tweet_id)
        if tweet:
            return tweet

        return None

    def fetch_tweets_batch(self, tweet_ids: List[str]) -> Dict[str, Tweet]:
        """Fetches a batch of tweets concurrently using ThreadPoolExecutor."""
        results = {}
        unique_ids = [tid for tid in set(tweet_ids) if tid]
        if not unique_ids:
            return results

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_id = {executor.submit(self.fetch_tweet, tid): tid for tid in unique_ids}
            for future in as_completed(future_to_id):
                tid = future_to_id[future]
                try:
                    tweet = future.result()
                    if tweet:
                        results[tid] = tweet
                except Exception as e:
                    if self.verbose:
                        logger.debug(f"Batch fetch error for {tid}: {e}")
        return results

    def _parse_fxtwitter_tweet(self, raw: Dict[str, Any]) -> Tweet:
        """Normalizes FixTweet JSON into a Tweet model."""
        author_raw = raw.get("author") or {}
        author = Author(
            name=author_raw.get("name") or author_raw.get("screen_name") or "Unknown",
            screen_name=author_raw.get("screen_name") or "",
            avatar_url=author_raw.get("avatar_url"),
            verified=bool(author_raw.get("verified") or author_raw.get("blue_verified")),
            verified_type=author_raw.get("verified_type"),
            followers_count=author_raw.get("followers"),
            description=author_raw.get("description"),
            profile_url=author_raw.get("url") or (f"https://x.com/{author_raw.get('screen_name')}" if author_raw.get('screen_name') else None)
        )

        media_items: List[MediaItem] = []
        media_raw = raw.get("media") or {}
        
        photos = media_raw.get("photos") or []
        for p in photos:
            p_url = p.get("url")
            if p_url:
                media_items.append(MediaItem(
                    type="photo",
                    url=p_url,
                    alt_text=p.get("altText"),
                    width=p.get("width"),
                    height=p.get("height")
                ))

        videos = media_raw.get("videos") or []
        for v in videos:
            v_url = v.get("url")
            if v_url:
                media_items.append(MediaItem(
                    type="video",
                    url=v_url,
                    thumbnail_url=v.get("thumbnail_url"),
                    duration_ms=int(v.get("duration", 0) * 1000) if v.get("duration") else None,
                    variants=v.get("variants", [])
                ))

        all_media = media_raw.get("all") or []
        for m in all_media:
            m_url = m.get("url")
            if m_url and not any(item.url == m_url for item in media_items):
                m_type = m.get("type", "photo")
                media_items.append(MediaItem(
                    type=m_type,
                    url=m_url,
                    thumbnail_url=m.get("thumbnail_url"),
                    alt_text=m.get("altText")
                ))

        quote: Optional[QuoteTweet] = None
        quote_raw = raw.get("quote")
        if quote_raw:
            q_author = quote_raw.get("author") or {}
            quote = QuoteTweet(
                id=str(quote_raw.get("id", "")),
                text=html.unescape(quote_raw.get("text", "")),
                author_name=q_author.get("name", "Unknown"),
                author_screen_name=q_author.get("screen_name", ""),
                author_avatar=q_author.get("avatar_url"),
                url=quote_raw.get("url")
            )

        tweet_id = str(raw.get("id"))
        created_timestamp = raw.get("created_timestamp") or 0
        created_at_str = raw.get("created_at") or ""
        text = html.unescape(raw.get("text", ""))

        return Tweet(
            id=tweet_id,
            url=raw.get("url") or f"https://x.com/{author.screen_name}/status/{tweet_id}",
            text=text,
            author=author,
            created_at=created_at_str,
            created_timestamp=created_timestamp,
            media=media_items,
            quote=quote,
            likes=int(raw.get("likes") or 0),
            retweets=int(raw.get("retweets") or 0),
            replies=int(raw.get("replies") or 0),
            quotes=int(raw.get("quotes") or 0),
            views=raw.get("views"),
            bookmarks=raw.get("bookmarks"),
            replying_to_status_id=str(raw.get("replying_to_status")) if raw.get("replying_to_status") else None,
            conversation_id=str(raw.get("conversation_id")) if raw.get("conversation_id") else None,
            is_note_tweet=bool(raw.get("is_note_tweet")),
            lang=raw.get("lang")
        )

    def _parse_syndication_tweet(self, raw: Dict[str, Any]) -> Tweet:
        """Normalizes Twitter Syndication CDN JSON into a Tweet model."""
        user_raw = raw.get("user") or {}
        author = Author(
            name=user_raw.get("name") or user_raw.get("screen_name") or "Unknown",
            screen_name=user_raw.get("screen_name") or "",
            avatar_url=user_raw.get("profile_image_url_https"),
            verified=bool(user_raw.get("is_blue_verified") or user_raw.get("verified")),
            verified_type=user_raw.get("verified_type"),
            followers_count=user_raw.get("followers_count"),
            profile_url=f"https://x.com/{user_raw.get('screen_name')}" if user_raw.get('screen_name') else None
        )

        media_items: List[MediaItem] = []
        photos = raw.get("photos") or []
        for p in photos:
            p_url = p.get("url")
            if p_url:
                media_items.append(MediaItem(
                    type="photo",
                    url=p_url,
                    width=p.get("width"),
                    height=p.get("height")
                ))

        video_raw = raw.get("video")
        if video_raw:
            variants = video_raw.get("variants") or []
            best_mp4 = None
            max_bitrate = -1
            for var in variants:
                if var.get("type") == "video/mp4" or "video/mp4" in var.get("content_type", ""):
                    br = var.get("bitrate", 0)
                    if br > max_bitrate:
                        max_bitrate = br
                        best_mp4 = var.get("src") or var.get("url")

            v_url = best_mp4 or (variants[0].get("src") or variants[0].get("url") if variants else None)
            if v_url:
                media_items.append(MediaItem(
                    type="video",
                    url=v_url,
                    thumbnail_url=video_raw.get("poster"),
                    duration_ms=video_raw.get("durationMs"),
                    variants=variants
                ))

        quote: Optional[QuoteTweet] = None
        q_raw = raw.get("quoted_tweet")
        if q_raw:
            q_user = q_raw.get("user") or {}
            quote = QuoteTweet(
                id=str(q_raw.get("id_str", "")),
                text=html.unescape(q_raw.get("text", "")),
                author_name=q_user.get("name", "Unknown"),
                author_screen_name=q_user.get("screen_name", ""),
                author_avatar=q_user.get("profile_image_url_https"),
                url=f"https://x.com/{q_user.get('screen_name')}/status/{q_raw.get('id_str')}"
            )

        tweet_id = str(raw.get("id_str") or raw.get("id"))
        created_at_str = raw.get("created_at") or ""
        created_ts = 0
        if created_at_str:
            try:
                dt = datetime.strptime(created_at_str, "%a %b %d %H:%M:%S %z %Y")
                created_ts = int(dt.timestamp())
            except Exception:
                pass

        parent_raw = raw.get("parent")
        parent_id = str(parent_raw.get("id_str")) if parent_raw and parent_raw.get("id_str") else None
        text = html.unescape(raw.get("text", ""))

        return Tweet(
            id=tweet_id,
            url=f"https://x.com/{author.screen_name}/status/{tweet_id}",
            text=text,
            author=author,
            created_at=created_at_str,
            created_timestamp=created_ts,
            media=media_items,
            quote=quote,
            likes=int(raw.get("favorite_count") or 0),
            retweets=0,
            replies=int(raw.get("conversation_count") or 0),
            replying_to_status_id=parent_id,
            conversation_id=str(raw.get("conversation_id_str")) if raw.get("conversation_id_str") else None,
            lang=raw.get("lang")
        )

    def _parse_vxtwitter_tweet(self, raw: Dict[str, Any], tweet_id: str) -> Tweet:
        """Normalizes VxTwitter JSON into a Tweet model."""
        author = Author(
            name=raw.get("user_name") or raw.get("user_screen_name") or "Unknown",
            screen_name=raw.get("user_screen_name") or "",
            profile_url=f"https://x.com/{raw.get('user_screen_name')}" if raw.get('user_screen_name') else None
        )

        media_items: List[MediaItem] = []
        media_urls = raw.get("mediaURLs") or []
        for m_url in media_urls:
            media_type = "video" if any(ext in m_url.lower() for ext in [".mp4", ".mov", ".m3u8"]) else "photo"
            media_items.append(MediaItem(type=media_type, url=m_url))

        created_ts = raw.get("date_epoch") or 0
        created_at_str = raw.get("date") or ""

        return Tweet(
            id=tweet_id,
            url=raw.get("tweetURL") or f"https://x.com/{author.screen_name}/status/{tweet_id}",
            text=html.unescape(raw.get("text", "")),
            author=author,
            created_at=created_at_str,
            created_timestamp=created_ts,
            media=media_items,
            likes=int(raw.get("likes") or 0),
            retweets=int(raw.get("retweets") or 0),
            replies=int(raw.get("replies") or 0)
        )

    def _extract_ssr_tweet_ids(self, tweet_id: str, screen_name: Optional[str] = None) -> List[str]:
        """
        Extracts all related tweet IDs in the conversation stream from Twitter/X's SSR stream.
        Decodes base64 Tweet & NoteTweet IDs directly from initial HTML payload without login.
        """
        url = f"https://x.com/{screen_name or 'i'}/status/{tweet_id}"
        discovered_ids: List[str] = []
        try:
            r = self.session.get(url, headers=self._get_headers(), timeout=self.timeout)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                scripts = soup.find_all("script")
                for s in scripts:
                    if s.string and "relayRecords" in s.string:
                        # Extract Tweet:<id> base64 tags
                        tweet_ids_b64 = re.findall(r'VHdlZXQ6([A-Za-z0-9+/=]+)', s.string)
                        for b in tweet_ids_b64:
                            try:
                                dec = base64.b64decode("VHdlZXQ6" + b).decode('utf-8', errors='ignore')
                                if dec.startswith("Tweet:"):
                                    tid = dec.replace("Tweet:", "")
                                    if tid.isdigit() and tid not in discovered_ids:
                                        discovered_ids.append(tid)
                            except Exception:
                                pass
                        # Extract NoteTweet:<id> base64 tags
                        note_ids_b64 = re.findall(r'Tm90ZVR3ZWV0Oj([A-Za-z0-9+/=]+)', s.string)
                        for b in note_ids_b64:
                            try:
                                dec = base64.b64decode("Tm90ZVR3ZWV0Oj" + b).decode('utf-8', errors='ignore')
                                tid = dec.replace("NoteTweet:", "")
                                if tid.isdigit() and tid not in discovered_ids:
                                    discovered_ids.append(tid)
                            except Exception:
                                pass
        except Exception as e:
            if self.verbose:
                logger.debug(f"[SSR] Failed to extract SSR tweet IDs for {tweet_id}: {e}")
        return discovered_ids

    def _fetch_timeline_entries(self, screen_name: str) -> List[Dict[str, Any]]:
        """
        Fetches timeline entries from the public syndication timeline widget.
        """
        if not screen_name:
            return []

        url = f"{self.SYNDICATION_TIMELINE_BASE}/{screen_name}"
        try:
            r = self.session.get(url, headers=self._get_headers(), timeout=self.timeout)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                next_data = soup.find("script", id="__NEXT_DATA__")
                if next_data and next_data.string:
                    data = json.loads(next_data.string)
                    entries = data.get("props", {}).get("pageProps", {}).get("timeline", {}).get("entries", [])
                    return entries
        except Exception as e:
            if self.verbose:
                logger.debug(f"[Timeline] Failed to fetch timeline for @{screen_name}: {e}")
        return []

    def unroll_quote_thread(self, quote_tweet: Tweet) -> Tuple[List[Tweet], List[CommentNode]]:
        """
        Unrolls a full quote thread if the quote author continued quoting with follow-up tweets,
        and collects any direct comments left on that quote thread.
        """
        quote_author = quote_tweet.author.screen_name
        quote_tweets_dict: Dict[str, Tweet] = {quote_tweet.id: quote_tweet}
        all_discovered_in_quote: Dict[str, Tweet] = {quote_tweet.id: quote_tweet}

        # Check SSR stream of the quote tweet for continuation
        ssr_ids = self._extract_ssr_tweet_ids(quote_tweet.id, quote_author)
        batch = self.fetch_tweets_batch(ssr_ids)
        all_discovered_in_quote.update(batch)

        for tid, tw in batch.items():
            if tw.author.screen_name.lower() == quote_author.lower():
                quote_tweets_dict[tw.id] = tw

        quote_tweets = sorted(
            quote_tweets_dict.values(),
            key=lambda t: (t.created_timestamp or 0, int(t.id) if t.id.isdigit() else 0)
        )
        for i, t in enumerate(quote_tweets, 1):
            t.position_in_thread = i

        # Iterative multi-wave comment expansion on the quote thread
        quote_tweet_ids = set(quote_tweets_dict.keys())
        expanded_comment_ids: Set[str] = set(quote_tweet_ids)

        for _wave in range(3):
            candidates = [
                tw for tw in all_discovered_in_quote.values()
                if tw.id not in expanded_comment_ids and (
                    tw.replies > 0 or tw.replying_to_status_id in expanded_comment_ids
                )
            ]
            if not candidates:
                break

            expand_ids = [c.id for c in candidates]
            wave_ssr: Set[str] = set()
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futs = {executor.submit(self._extract_ssr_tweet_ids, tid, None): tid for tid in expand_ids}
                for fut in as_completed(futs):
                    try:
                        wave_ssr.update(fut.result())
                    except Exception:
                        pass

            expanded_comment_ids.update(expand_ids)
            new_ids = list(wave_ssr - set(all_discovered_in_quote.keys()))
            if not new_ids:
                break
            new_batch = self.fetch_tweets_batch(new_ids[:50])
            all_discovered_in_quote.update(new_batch)

        comments_on_quote_flat = [
            tw for tw in all_discovered_in_quote.values()
            if tw.id not in quote_tweet_ids and (
                tw.replying_to_status_id in quote_tweet_ids
                or tw.conversation_id == quote_tweet.id
                or tw.replying_to_status_id in {t.id for t in all_discovered_in_quote.values() if t.id not in quote_tweet_ids}
            )
        ]

        quote_comment_tree = self._build_nested_comment_tree(
            root_ids=quote_tweet_ids,
            all_comments=comments_on_quote_flat,
            max_nesting_depth=5
        )

        return quote_tweets, quote_comment_tree

    def _build_nested_comment_tree(self, root_ids: Set[str], all_comments: List[Tweet], max_nesting_depth: int = 10) -> List[CommentNode]:
        """
        Builds a hierarchical, recursive comment tree from a flat list of comments.
        Ties direct replies to root tweets or entry-point comments, and sub-replies
        to their parent comments (Level 1 -> Level 2 -> Level 3...).
        """
        if not all_comments:
            return []

        all_ids_in_pool = {c.id for c in all_comments}
        reply_map: Dict[str, List[Tweet]] = {}

        for c in all_comments:
            p_id = c.replying_to_status_id or ""
            if p_id not in reply_map:
                reply_map[p_id] = []
            reply_map[p_id].append(c)

        for p_id in reply_map:
            reply_map[p_id] = sorted(
                reply_map[p_id],
                key=lambda t: (t.likes, t.retweets, t.created_timestamp or 0),
                reverse=True
            )

        def build_node(tweet: Tweet, depth: int) -> CommentNode:
            tweet.depth = depth
            sub_replies = []
            if depth < max_nesting_depth and tweet.id in reply_map:
                for child_tw in reply_map[tweet.id]:
                    sub_replies.append(build_node(child_tw, depth + 1))
            return CommentNode(tweet=tweet, replies=sub_replies, depth=depth)

        # Identify top-level conversation roots in this pool:
        # A) Explicit replies to one of the root_ids
        # B) Any comment whose parent is NOT in all_comments (so it's the root of its own thread)
        top_roots: List[Tweet] = []
        seen_root_ids: Set[str] = set()

        for c in all_comments:
            is_direct_child = c.replying_to_status_id in root_ids
            is_external_parent = (c.replying_to_status_id not in all_ids_in_pool)
            if is_direct_child or is_external_parent:
                if c.id not in seen_root_ids:
                    top_roots.append(c)
                    seen_root_ids.add(c.id)

        # If for any reason no top roots were identified, treat all remaining as roots
        if not top_roots and all_comments:
            top_roots = list(all_comments)

        top_nodes: List[CommentNode] = [build_node(r_tw, depth=1) for r_tw in top_roots]
        top_nodes = sorted(top_nodes, key=lambda n: (n.tweet.likes, n.total_descendants), reverse=True)
        return top_nodes


    def scrape_thread(
        self,
        url_or_id: str,
        extra_quote_urls: Optional[List[str]] = None,
        max_comments: int = 300,
        max_depth: int = 50,
        max_comment_nesting: int = 10,
        include_comments: bool = True,
        include_requotes: bool = True
    ) -> Thread:
        """
        High-Capacity Scraper (Unified Single-Folder Output):
        - Reconstructs strictly the linear main author thread sequence (e.g. 4 tweets).
        - Crawls multi-level nested comment/reply trees.
        - Identifies and unrolls requote threads, explicitly matching which exact tweet was quoted.
        """
        focal_id, url_screen_name = self.extract_tweet_info(url_or_id)
        if self.verbose:
            logger.info(f"Extracting thread for Tweet ID: {focal_id}")

        focal_tweet = self.fetch_tweet(focal_id)
        if not focal_tweet:
            raise RuntimeError(f"Failed to fetch tweet {focal_id}. The tweet may be deleted or private.")

        author = focal_tweet.author
        if not author.screen_name and url_screen_name:
            author.screen_name = url_screen_name

        main_author_handle = author.screen_name.lower()
        all_discovered: Dict[str, Tweet] = {focal_tweet.id: focal_tweet}

        # 1. UPWARD ANCESTRY TRAVERSAL (Climb up to root tweet)
        curr_tweet = focal_tweet
        depth = 0
        while curr_tweet.replying_to_status_id and depth < max_depth:
            parent_id = curr_tweet.replying_to_status_id
            if parent_id in all_discovered:
                break
            parent_tweet = self.fetch_tweet(parent_id)
            if not parent_tweet:
                break
            all_discovered[parent_tweet.id] = parent_tweet
            curr_tweet = parent_tweet
            depth += 1

        root_tweet = curr_tweet
        root_id = root_tweet.id
        conversation_id = focal_tweet.conversation_id or root_id

        # 2. SSR THREAD STREAM DISCOVERY (Parallel queue)
        query_ids = [root_id, focal_id]
        if root_tweet.replying_to_status_id:
            query_ids.append(root_tweet.replying_to_status_id)

        ssr_discovered_ids: Set[str] = set()
        for tid in query_ids:
            for s_id in self._extract_ssr_tweet_ids(tid, author.screen_name):
                ssr_discovered_ids.add(s_id)

        # Batch fetch all initial SSR discovered tweets
        batch_1 = self.fetch_tweets_batch(list(ssr_discovered_ids - set(all_discovered.keys())))
        all_discovered.update(batch_1)

        # 3. DOWNWARD TIMELINE TRAVERSAL (Author continuity & follow-ups)
        timeline_entries = self._fetch_timeline_entries(author.screen_name)
        timeline_fetch_ids = []
        for entry in timeline_entries:
            if "content" in entry and "tweet" in entry["content"]:
                raw_tw = entry["content"]["tweet"]
                tw_id = str(raw_tw.get("id_str") or raw_tw.get("id"))
                tw_conv_id = str(raw_tw.get("conversation_id_str") or "")
                tw_reply_to = str(raw_tw.get("in_reply_to_status_id_str") or "")

                is_in_thread = (
                    tw_conv_id == root_id or
                    tw_conv_id == conversation_id or
                    tw_reply_to in all_discovered or
                    tw_id == root_id
                )
                if is_in_thread and tw_id not in all_discovered:
                    timeline_fetch_ids.append(tw_id)

        batch_tl = self.fetch_tweets_batch(timeline_fetch_ids)
        all_discovered.update(batch_tl)

        # 4. FETCH ANY EXPLICITLY PASSED EXTRA QUOTE URLS
        if extra_quote_urls:
            extra_ids = []
            for u in extra_quote_urls:
                try:
                    q_id, _ = self.extract_tweet_info(u)
                    extra_ids.append(q_id)
                except Exception:
                    pass
            batch_extra = self.fetch_tweets_batch(extra_ids)
            all_discovered.update(batch_extra)

        # 5. DEEP ITERATIVE MULTI-WAVE COMMENT CRAWLING
        # Each wave: find comments with replies > 0 that haven't been expanded yet,
        # crawl their SSR pages, discover sub-replies, repeat until no new tweets.
        if include_comments:
            expanded_ids: Set[str] = set()  # IDs whose SSR pages we've already crawled
            total_comments_found = 0
            max_waves = 5  # Safety cap on expansion rounds

            for wave in range(max_waves):
                # Find tweets worth expanding: have replies, haven't been expanded yet
                candidates_to_expand = [
                    tw for tw in all_discovered.values()
                    if tw.id not in expanded_ids and (
                        tw.replies > 0 or
                        tw.replying_to_status_id in all_discovered or
                        tw.id in {root_id}
                    )
                ]
                # Prioritize: main thread tweets first, then comments with most replies
                candidates_to_expand.sort(
                    key=lambda t: (t.id in {root_id}, t.replies or 0),
                    reverse=True
                )
                candidates_to_expand = candidates_to_expand[:40]

                if not candidates_to_expand:
                    break

                wave_ssr_ids: Set[str] = set()
                expand_these = [c.id for c in candidates_to_expand if c.id not in expanded_ids]

                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    future_to_id = {executor.submit(self._extract_ssr_tweet_ids, tid, None): tid for tid in expand_these}
                    for future in as_completed(future_to_id):
                        try:
                            ids = future.result()
                            wave_ssr_ids.update(ids)
                        except Exception:
                            pass

                expanded_ids.update(expand_these)

                new_ids = list(wave_ssr_ids - set(all_discovered.keys()))
                if not new_ids:
                    break

                # Cap per wave to avoid runaway on viral threads
                new_ids = new_ids[:max_comments - total_comments_found]
                if not new_ids:
                    break

                batch_wave = self.fetch_tweets_batch(new_ids)
                all_discovered.update(batch_wave)
                total_comments_found += len(batch_wave)

                if self.verbose:
                    logger.info(f"[Comments] Wave {wave+1}: expanded {len(expand_these)} tweets, found {len(batch_wave)} new tweets (total: {total_comments_found})")

                if total_comments_found >= max_comments:
                    break

        # 6. STRICT LINEAR MAIN THREAD RECONSTRUCTION
        # Build strictly the primary author's sequential direct reply chain starting at root_id
        main_thread_tweets: List[Tweet] = []
        thread_ids_set = set()
        tweet_position_map: Dict[str, Tuple[int, str]] = {}

        if root_id in all_discovered:
            curr = all_discovered[root_id]
            main_thread_tweets.append(curr)
            visited_main = {root_id}

            # Walk strictly down the reply chain of the original thread
            while True:
                next_tw = None
                for cand in all_discovered.values():
                    if (
                        cand.id not in visited_main
                        and cand.author.screen_name.lower() == main_author_handle
                        and cand.replying_to_status_id == curr.id
                        and not cand.quote  # Direct continuation, not a separate quote tweet
                    ):
                        next_tw = cand
                        break
                if next_tw:
                    main_thread_tweets.append(next_tw)
                    visited_main.add(next_tw.id)
                    curr = next_tw
                else:
                    break
        else:
            main_thread_tweets = [focal_tweet]

        for i, t in enumerate(main_thread_tweets, 1):
            t.position_in_thread = i
            thread_ids_set.add(t.id)
            snippet = t.text.strip().split("\n")[0]
            if len(snippet) > 60:
                snippet = snippet[:57] + "..."
            tweet_position_map[t.id] = (i, snippet)

        # 7. REQUOTES & QUOTE THREADS (With exact quoted tweet pointer tracking)
        requote_objects: List[Requote] = []
        seen_requotes: Set[str] = set()
        all_requote_tweet_ids: Set[str] = set()

        for tw in all_discovered.values():
            if tw.quote and (tw.quote.id in thread_ids_set or tw.quote.id in all_discovered):
                if tw.id not in seen_requotes and tw.id not in thread_ids_set:
                    seen_requotes.add(tw.id)
                    q_tweets, q_comments = self.unroll_quote_thread(tw)
                    for qt in q_tweets:
                        all_requote_tweet_ids.add(qt.id)

                    # Determine exact quoted tweet in main thread
                    quoted_id = tw.quote.id
                    pos_info = tweet_position_map.get(quoted_id)
                    q_pos = pos_info[0] if pos_info else None
                    q_snip = pos_info[1] if pos_info else (tw.quote.text[:55] if tw.quote.text else None)

                    requote_obj = Requote(
                        root_quote_id=tw.id,
                        author=tw.author,
                        is_thread=len(q_tweets) > 1,
                        tweets=q_tweets,
                        quoted_status_id=quoted_id,
                        quoted_tweet_position=q_pos,
                        quoted_tweet_snippet=q_snip,
                        comments=q_comments
                    )
                    requote_objects.append(requote_obj)

        requote_objects = sorted(
            requote_objects,
            key=lambda r: (r.total_likes, r.total_retweets, r.tweet_count),
            reverse=True
        )

        # 8. COMMENTS & MULTI-LEVEL REPLY TREE
        # Include comments on the main thread that are not part of main thread or quote threads
        all_comments_flat: List[Tweet] = []
        for tw in all_discovered.values():
            if tw.id not in thread_ids_set and tw.id not in all_requote_tweet_ids:
                all_comments_flat.append(tw)

        comment_tree = self._build_nested_comment_tree(
            root_ids=thread_ids_set,
            all_comments=all_comments_flat,
            max_nesting_depth=max_comment_nesting
        )

        return Thread(
            root_id=root_id,
            conversation_id=conversation_id,
            author=author,
            tweets=main_thread_tweets,
            comment_tree=comment_tree if include_comments else [],
            comments=all_comments_flat if include_comments else [],
            requotes=requote_objects if include_requotes else [],
            source_url=f"https://x.com/{author.screen_name}/status/{root_id}" if author.screen_name else url_or_id
        )
