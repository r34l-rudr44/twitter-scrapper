"""
Lightweight Web Interface for Twitter/X Thread Scraper.
Runs a local web UI to paste links, visualize threads, and download exports.
"""

import os
from flask import Flask, request, jsonify, render_template_string, Response
from scraper import TwitterThreadScraper
from exporters import ThreadExporter

app = Flask(__name__)
scraper = TwitterThreadScraper()

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Twitter / X Thread Scraper</title>
    <style>
        :root {
            --bg: #0f1419;
            --card-bg: #1e2732;
            --card-border: #2f3336;
            --text-primary: #f7f9f9;
            --text-secondary: #8b98a5;
            --accent: #1d9bf0;
            --accent-hover: #1a8cd8;
            --success: #00ba7c;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: var(--bg);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2.5rem 1rem;
        }
        .container {
            width: 100%;
            max-width: 720px;
        }
        header {
            text-align: center;
            margin-bottom: 2rem;
        }
        h1 {
            font-size: 2.2rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #1d9bf0, #8ec5fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        p.subtitle {
            color: var(--text-secondary);
            font-size: 1.05rem;
        }
        .input-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.25);
        }
        .input-group {
            display: flex;
            gap: 0.75rem;
        }
        input[type="text"] {
            flex: 1;
            padding: 0.85rem 1.1rem;
            font-size: 1rem;
            border-radius: 10px;
            border: 1px solid var(--card-border);
            background: #15181c;
            color: #fff;
            outline: none;
            transition: border-color 0.2s;
        }
        input[type="text"]:focus {
            border-color: var(--accent);
        }
        button.btn-primary {
            padding: 0.85rem 1.5rem;
            font-size: 1rem;
            font-weight: 600;
            background: var(--accent);
            color: #fff;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            transition: background 0.2s, transform 0.1s;
        }
        button.btn-primary:hover {
            background: var(--accent-hover);
        }
        button.btn-primary:active {
            transform: scale(0.98);
        }
        .sample-buttons {
            display: flex;
            gap: 0.5rem;
            margin-top: 0.85rem;
            flex-wrap: wrap;
            align-items: center;
        }
        .sample-tag {
            font-size: 0.8rem;
            color: var(--text-secondary);
        }
        .sample-btn {
            background: rgba(255,255,255,0.06);
            border: 1px solid var(--card-border);
            color: var(--text-secondary);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 0.8rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        .sample-btn:hover {
            color: var(--text-primary);
            border-color: var(--accent);
        }
        .loading {
            display: none;
            text-align: center;
            padding: 2rem;
            color: var(--text-secondary);
        }
        .spinner {
            border: 3px solid rgba(255,255,255,0.1);
            border-top: 3px solid var(--accent);
            border-radius: 50%;
            width: 32px;
            height: 32px;
            animation: spin 0.8s linear infinite;
            margin: 0 auto 0.75rem auto;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .error-card {
            display: none;
            background: rgba(244, 33, 46, 0.1);
            border: 1px solid #f4212e;
            color: #ff7b82;
            padding: 1rem;
            border-radius: 10px;
            margin-bottom: 1.5rem;
        }
        .result-container {
            display: none;
        }
        .export-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            padding: 0.75rem 1.25rem;
            border-radius: 12px;
            margin-bottom: 1.5rem;
        }
        .export-btns {
            display: flex;
            gap: 0.5rem;
        }
        .btn-export {
            background: #273340;
            border: 1px solid var(--card-border);
            color: #fff;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 0.85rem;
            cursor: pointer;
            text-decoration: none;
            transition: background 0.2s;
        }
        .btn-export:hover { background: #374656; }
        .thread-stream {
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        .tweet-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 1.25rem;
        }
        .tweet-meta {
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 0.75rem;
        }
        .badge-num {
            background: rgba(29,155,240,0.15);
            color: var(--accent);
            padding: 2px 8px;
            border-radius: 10px;
            font-weight: 600;
        }
        .tweet-content {
            font-size: 1.05rem;
            line-height: 1.6;
            margin-bottom: 0.85rem;
            white-space: pre-wrap;
        }
        .media-box img, .media-box video {
            max-width: 100%;
            border-radius: 8px;
            margin-top: 0.5rem;
        }
        .tweet-stats {
            display: flex;
            gap: 1rem;
            font-size: 0.85rem;
            color: var(--text-secondary);
            padding-top: 0.75rem;
            border-top: 1px solid var(--card-border);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Twitter / X Thread Scraper</h1>
            <p class="subtitle">Extract and unroll full threads from any link — zero login walls</p>
        </header>

        <div class="input-card">
            <div class="input-group">
                <input type="text" id="urlInput" placeholder="Paste tweet or thread link (e.g. https://x.com/naval/status/1002103360646823936)..." autocomplete="off">
                <button class="btn-primary" id="scrapeBtn" onclick="scrape()">Scrape</button>
            </div>
            <div class="sample-buttons">
                <span class="sample-tag">Try sample:</span>
                <button class="sample-btn" onclick="fillUrl('https://x.com/naval/status/1002103360646823936')">Naval: How to Get Rich</button>
                <button class="sample-btn" onclick="fillUrl('https://x.com/jack/status/20')">Jack: First Tweet</button>
            </div>
        </div>

        <div class="error-card" id="errorBox"></div>

        <div class="loading" id="loadingBox">
            <div class="spinner"></div>
            <p>Fetching and unrolling thread...</p>
        </div>

        <div class="result-container" id="resultContainer">
            <div class="export-bar">
                <span id="statsLabel"><strong>0</strong> Tweets Extracted</span>
                <div class="export-btns">
                    <button class="btn-export" onclick="downloadExport('md')">📥 Markdown</button>
                    <button class="btn-export" onclick="downloadExport('json')">📥 JSON</button>
                    <button class="btn-export" onclick="downloadExport('txt')">📥 Text</button>
                    <button class="btn-export" onclick="downloadExport('html')">📥 HTML</button>
                </div>
            </div>
            <div class="thread-stream" id="threadStream"></div>
        </div>
    </div>

    <script>
        let currentThread = null;

        function fillUrl(url) {
            document.getElementById('urlInput').value = url;
            scrape();
        }

        async function scrape() {
            const url = document.getElementById('urlInput').value.trim();
            if (!url) return;

            const errorBox = document.getElementById('errorBox');
            const loadingBox = document.getElementById('loadingBox');
            const resultContainer = document.getElementById('resultContainer');
            const threadStream = document.getElementById('threadStream');
            const statsLabel = document.getElementById('statsLabel');

            errorBox.style.display = 'none';
            resultContainer.style.display = 'none';
            loadingBox.style.display = 'block';

            try {
                const res = await fetch('/api/scrape', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });
                const data = await res.json();

                if (!res.ok || data.error) {
                    throw new Error(data.error || 'Failed to scrape thread');
                }

                currentThread = data;
                loadingBox.style.display = 'none';
                resultContainer.style.display = 'block';

                statsLabel.innerHTML = `<strong>${data.tweet_count}</strong> Tweets by <strong>@${data.author.screen_name}</strong>`;
                threadStream.innerHTML = '';

                data.tweets.forEach(tweet => {
                    const card = document.createElement('div');
                    card.className = 'tweet-card';

                    let mediaHtml = '';
                    if (tweet.media && tweet.media.length > 0) {
                        tweet.media.forEach(m => {
                            if (m.type === 'photo') {
                                mediaHtml += `<div class="media-box"><a href="${m.url}" target="_blank"><img src="${m.url}" loading="lazy"></a></div>`;
                            } else if (m.type === 'video') {
                                mediaHtml += `<div class="media-box"><video controls poster="${m.thumbnail_url || ''}"><source src="${m.url}" type="video/mp4"></video></div>`;
                            }
                        });
                    }

                    let quoteHtml = '';
                    if (tweet.quote) {
                        quoteHtml = `<div style="background:rgba(255,255,255,0.05); border-left:3px solid var(--accent); padding:8px 12px; margin-top:8px; border-radius:4px; font-size:0.9rem;">
                            <strong>@${tweet.quote.author_screen_name}</strong>: ${escapeHtml(tweet.quote.text)}
                        </div>`;
                    }

                    card.innerHTML = `
                        <div class="tweet-meta">
                            <span class="badge-num">Tweet ${tweet.position} of ${data.tweet_count}</span>
                            <span>${tweet.formatted_date}</span>
                        </div>
                        <div class="tweet-content">${escapeHtml(tweet.text)}</div>
                        ${mediaHtml}
                        ${quoteHtml}
                        <div class="tweet-stats">
                            <span>❤️ ${tweet.metrics.likes.toLocaleString()}</span>
                            <span>🔁 ${tweet.metrics.retweets.toLocaleString()}</span>
                            <span>💬 ${tweet.metrics.replies.toLocaleString()}</span>
                        </div>
                    `;
                    threadStream.appendChild(card);
                });

            } catch (err) {
                loadingBox.style.display = 'none';
                errorBox.textContent = err.message;
                errorBox.style.display = 'block';
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        async function downloadExport(format) {
            if (!currentThread) return;
            const res = await fetch(`/api/export/${format}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentThread)
            });
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${currentThread.author.screen_name}_thread.${format}`;
            document.body.appendChild(a);
            a.click();
            a.remove();
        }

        document.getElementById('urlInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') scrape();
        });
    </script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL or Tweet ID is required."}), 400

    try:
        thread = scraper.scrape_thread(url)
        return jsonify(thread.to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/export/<fmt>", methods=["POST"])
def api_export(fmt):
    data = request.get_json() or {}
    try:
        from models import Thread, Tweet, Author, MediaItem, QuoteTweet
        author_data = data.get("author", {})
        author = Author(
            name=author_data.get("name", ""),
            screen_name=author_data.get("screen_name", ""),
            avatar_url=author_data.get("avatar_url"),
            verified=author_data.get("verified", False),
            profile_url=author_data.get("profile_url")
        )

        tweets = []
        for t in data.get("tweets", []):
            media = [MediaItem(**m) for m in t.get("media", [])]
            quote = QuoteTweet(**t["quote"]) if t.get("quote") else None
            tweets.append(Tweet(
                id=t["id"],
                url=t["url"],
                text=t["text"],
                author=author,
                created_at=t["created_at"],
                created_timestamp=t["created_timestamp"],
                media=media,
                quote=quote,
                likes=t["metrics"]["likes"],
                retweets=t["metrics"]["retweets"],
                replies=t["metrics"]["replies"],
                position_in_thread=t["position"]
            ))

        thread = Thread(
            root_id=data.get("root_id", ""),
            conversation_id=data.get("conversation_id", ""),
            author=author,
            tweets=tweets,
            source_url=data.get("source_url", "")
        )

        if fmt == "md":
            content = ThreadExporter.to_markdown(thread)
            mimetype = "text/markdown"
        elif fmt == "json":
            content = ThreadExporter.to_json(thread)
            mimetype = "application/json"
        elif fmt == "txt":
            content = ThreadExporter.to_text(thread)
            mimetype = "text/plain"
        elif fmt == "html":
            content = ThreadExporter.to_html(thread)
            mimetype = "text/html"
        else:
            return jsonify({"error": "Unsupported format"}), 400

        return Response(content, mimetype=mimetype)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Twitter Thread Scraper Web UI on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
