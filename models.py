"""
Data models for Twitter/X Thread Scraper.
Provides scalable, hierarchical representations for Authors, Media, Tweets,
Nested Comment Trees, Quote Threads, and the unified Mega JSON schema.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timezone


@dataclass
class MediaItem:
    """Represents an attached image, video, or animated GIF."""
    type: str  # 'photo', 'video', 'animated_gif'
    url: str  # Direct URL to high-res photo or highest-quality MP4
    thumbnail_url: Optional[str] = None
    alt_text: Optional[str] = None
    duration_ms: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    variants: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Author:
    """Represents a Twitter/X author profile."""
    name: str
    screen_name: str
    avatar_url: Optional[str] = None
    verified: bool = False
    verified_type: Optional[str] = None
    followers_count: Optional[int] = None
    description: Optional[str] = None
    profile_url: Optional[str] = None

    def __post_init__(self):
        if not self.profile_url and self.screen_name:
            self.profile_url = f"https://x.com/{self.screen_name}"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class QuoteTweet:
    """Represents an embedded quoted tweet reference."""
    id: str
    text: str
    author_name: str
    author_screen_name: str
    author_avatar: Optional[str] = None
    url: Optional[str] = None
    media: List[MediaItem] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "author_name": self.author_name,
            "author_screen_name": self.author_screen_name,
            "author_avatar": self.author_avatar,
            "url": self.url or f"https://x.com/{self.author_screen_name}/status/{self.id}",
            "media": [m.to_dict() for m in self.media]
        }


@dataclass
class Tweet:
    """Represents a single tweet in a thread, comment, or quote."""
    id: str
    url: str
    text: str
    author: Author
    created_at: str
    created_timestamp: int
    media: List[MediaItem] = field(default_factory=list)
    quote: Optional[QuoteTweet] = None
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    quotes: int = 0
    views: Optional[int] = None
    bookmarks: Optional[int] = None
    replying_to_status_id: Optional[str] = None
    conversation_id: Optional[str] = None
    is_note_tweet: bool = False
    lang: Optional[str] = None
    position_in_thread: int = 1
    depth: int = 0

    @property
    def formatted_date(self) -> str:
        if self.created_timestamp:
            try:
                dt = datetime.fromtimestamp(self.created_timestamp)
                return dt.strftime("%B %d, %Y at %I:%M %p")
            except Exception:
                pass
        return self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "position": self.position_in_thread,
            "depth": self.depth,
            "text": self.text,
            "author": self.author.to_dict(),
            "created_at": self.created_at,
            "created_timestamp": self.created_timestamp,
            "formatted_date": self.formatted_date,
            "media": [m.to_dict() for m in self.media],
            "quote": self.quote.to_dict() if self.quote else None,
            "metrics": {
                "likes": self.likes,
                "retweets": self.retweets,
                "replies": self.replies,
                "quotes": self.quotes,
                "views": self.views,
                "bookmarks": self.bookmarks
            },
            "replying_to_status_id": self.replying_to_status_id,
            "conversation_id": self.conversation_id,
            "is_note_tweet": self.is_note_tweet,
            "lang": self.lang
        }


@dataclass
class CommentNode:
    """
    Represents a comment and its nested tree of sub-replies.
    Scales to arbitrary depth (Comment -> Reply -> Sub-reply -> ...).
    """
    tweet: Tweet
    replies: List['CommentNode'] = field(default_factory=list)
    depth: int = 1

    @property
    def total_descendants(self) -> int:
        count = len(self.replies)
        for r in self.replies:
            count += r.total_descendants
        return count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tweet": self.tweet.to_dict(),
            "depth": self.depth,
            "total_descendants": self.total_descendants,
            "replies": [r.to_dict() for r in self.replies]
        }


@dataclass
class Requote:
    """
    Represents a Quote Tweet (requote) made to any tweet in the thread.
    Can be a single quote tweet or an entire unrolled multi-tweet quote thread.
    Tracks which exact tweet in the main thread was quoted.
    """
    root_quote_id: str
    author: Author
    is_thread: bool = False
    tweets: List[Tweet] = field(default_factory=list)
    quoted_status_id: Optional[str] = None
    quoted_tweet_position: Optional[int] = None
    quoted_tweet_snippet: Optional[str] = None
    comments: List[CommentNode] = field(default_factory=list)

    @property
    def tweet_count(self) -> int:
        return len(self.tweets)

    @property
    def total_likes(self) -> int:
        return sum(t.likes for t in self.tweets)

    @property
    def total_retweets(self) -> int:
        return sum(t.retweets for t in self.tweets)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_quote_id": self.root_quote_id,
            "author": self.author.to_dict(),
            "is_thread": self.is_thread,
            "tweet_count": self.tweet_count,
            "quoted_status_id": self.quoted_status_id,
            "quoted_tweet_position": self.quoted_tweet_position,
            "quoted_tweet_snippet": self.quoted_tweet_snippet,
            "total_likes": self.total_likes,
            "total_retweets": self.total_retweets,
            "tweets": [t.to_dict() for t in self.tweets],
            "comments_on_requote": [c.to_dict() for c in self.comments]
        }


@dataclass
class Thread:
    """
    Represents a complete unrolled Twitter/X thread with:
    - Main author thread sequence
    - Hierarchical nested comment tree (with sub-comments)
    - Requotes & multi-tweet quote threads
    """
    root_id: str
    conversation_id: str
    author: Author
    tweets: List[Tweet] = field(default_factory=list)
    comment_tree: List[CommentNode] = field(default_factory=list)
    comments: List[Tweet] = field(default_factory=list)  # Flat list of all comments
    requotes: List[Requote] = field(default_factory=list)
    source_url: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def tweet_count(self) -> int:
        return len(self.tweets)

    @property
    def comment_count(self) -> int:
        return len(self.comments)

    @property
    def top_level_comment_count(self) -> int:
        return len(self.comment_tree)

    @property
    def requote_count(self) -> int:
        return len(self.requotes)

    @property
    def single_requote_count(self) -> int:
        return sum(1 for r in self.requotes if not r.is_thread)

    @property
    def thread_requote_count(self) -> int:
        return sum(1 for r in self.requotes if r.is_thread)

    @property
    def total_likes(self) -> int:
        return sum(t.likes for t in self.tweets)

    @property
    def total_retweets(self) -> int:
        return sum(t.retweets for t in self.tweets)

    @property
    def total_media_count(self) -> int:
        return sum(len(t.media) for t in self.tweets)

    @property
    def title(self) -> str:
        """Derives a thread title from the root tweet's first line or snippet."""
        if not self.tweets:
            return "Twitter Thread"
        first_line = self.tweets[0].text.strip().split("\n")[0]
        if len(first_line) > 80:
            return first_line[:77] + "..."
        return first_line or "Twitter Thread"

    def to_dict(self) -> Dict[str, Any]:
        """Mega JSON schema tying the complete thread ecosystem together."""
        return {
            "thread_info": {
                "root_id": self.root_id,
                "conversation_id": self.conversation_id,
                "title": self.title,
                "author": self.author.to_dict(),
                "source_url": self.source_url,
                "fetched_at": self.fetched_at,
                "stats": {
                    "main_tweets_count": self.tweet_count,
                    "total_comments_count": self.comment_count,
                    "top_level_comments_count": self.top_level_comment_count,
                    "total_requotes_count": self.requote_count,
                    "single_requotes_count": self.single_requote_count,
                    "thread_requotes_count": self.thread_requote_count,
                    "total_likes": self.total_likes,
                    "total_retweets": self.total_retweets,
                    "total_media_count": self.total_media_count,
                }
            },
            "main_thread": [t.to_dict() for t in self.tweets],
            "comments_tree": [c.to_dict() for c in self.comment_tree],
            "all_comments_flat": [c.to_dict() for c in self.comments],
            "requotes": [r.to_dict() for r in self.requotes]
        }
