"""
Unit and Integration Tests for Unified Twitter/X Thread Scraper.
"""

import unittest
import os
import shutil
from scraper import TwitterThreadScraper
from models import Thread, Tweet, Author, MediaItem, QuoteTweet, Requote, CommentNode
from exporters import ThreadExporter


class TestTwitterThreadScraper(unittest.TestCase):

    def setUp(self):
        self.scraper = TwitterThreadScraper(verbose=False)
        self.test_output_dir = "test_output"

    def tearDown(self):
        if os.path.exists(self.test_output_dir):
            shutil.rmtree(self.test_output_dir, ignore_errors=True)

    def test_url_extraction(self):
        """Test extraction of tweet IDs and screen names across various URL formats."""
        test_cases = [
            ("https://x.com/jack/status/20", ("20", "jack")),
            ("https://twitter.com/naval/status/1002103360646823936", ("1002103360646823936", "naval")),
            ("https://mobile.twitter.com/elonmusk/status/1349129669258448897?s=20", ("1349129669258448897", "elonmusk")),
            ("https://fxtwitter.com/levelsio/status/987654321", ("987654321", "levelsio")),
            ("https://vxtwitter.com/sama/status/1122334455", ("1122334455", "sama")),
            ("https://fixupx.com/karpathy/status/9988776655", ("9988776655", "karpathy")),
            ("1002103360646823936", ("1002103360646823936", None)),
            ("status/20", ("20", None)),
        ]

        for input_url, expected in test_cases:
            tweet_id, screen_name = self.scraper.extract_tweet_info(input_url)
            self.assertEqual(tweet_id, expected[0], f"Failed for {input_url}")
            if expected[1]:
                self.assertEqual(screen_name, expected[1], f"Failed screen_name for {input_url}")

    def test_context_first_naming_and_mega_json(self):
        """Test conversion to context-first human-friendly folder names and Mega JSON schema."""
        author = Author(name="Aditya", screen_name="adityaarpitha", verified=True)
        commenter1 = Author(name="July", screen_name="julymemo")
        commenter2 = Author(name="Bob", screen_name="bob_reviewer")

        t1 = Tweet(
            id="101",
            url="https://x.com/adityaarpitha/status/101",
            text="This Huggingface incident is a warning shot.",
            author=author,
            created_at="2026-08-27",
            created_timestamp=1787830000,
            likes=10,
            position_in_thread=1
        )
        t2 = Tweet(
            id="102",
            url="https://x.com/adityaarpitha/status/102",
            text="4) Relational alignment perspective.",
            author=author,
            created_at="2026-08-27",
            created_timestamp=1787831000,
            likes=8,
            replying_to_status_id="101",
            position_in_thread=2
        )
        
        c1 = Tweet(
            id="201",
            url="https://x.com/julymemo/status/201",
            text="Level 1 Comment: How does this map to x-risk?",
            author=commenter1,
            created_at="2026-08-28",
            created_timestamp=1787890000,
            likes=4,
            replying_to_status_id="101",
            depth=1
        )

        c2 = Tweet(
            id="202",
            url="https://x.com/bob_reviewer/status/202",
            text="Level 2 Sub-reply: It maps via interface coupling.",
            author=commenter2,
            created_at="2026-08-28",
            created_timestamp=1787891000,
            likes=2,
            replying_to_status_id="201",
            depth=2
        )

        node_l2 = CommentNode(tweet=c2, replies=[], depth=2)
        node_l1 = CommentNode(tweet=c1, replies=[node_l2], depth=1)

        req_t1 = Tweet(
            id="301",
            url="https://x.com/adityaarpitha/status/301",
            text="So I believe alignment is ongoing maintenance [1/2]",
            author=author,
            created_at="2026-08-28",
            created_timestamp=1787892000,
            likes=15,
            position_in_thread=1
        )
        requote_thread = Requote(
            root_quote_id="301",
            author=author,
            is_thread=True,
            tweets=[req_t1],
            quoted_status_id="102",
            quoted_tweet_position=2,
            quoted_tweet_snippet="4) Relational alignment perspective.",
            comments=[node_l1]
        )

        thread = Thread(
            root_id="101",
            conversation_id="101",
            author=author,
            tweets=[t1, t2],
            comment_tree=[node_l1],
            comments=[c1, c2],
            requotes=[requote_thread]
        )

        # Export All
        saved = ThreadExporter.export_all(thread, base_output_dir=self.test_output_dir)
        folder = saved["folder"]
        
        # Verify context-first naming: starts with title, ends with ID
        folder_name = os.path.basename(folder)
        self.assertTrue(folder_name.startswith("This_Huggingface_incident_is_a_warning_shot"), f"Unexpected folder name: {folder_name}")
        self.assertTrue(folder_name.endswith("101"), f"Folder name doesn't end with ID: {folder_name}")

        # Verify all 7 files exist in this single folder
        self.assertTrue(os.path.exists(os.path.join(folder, "thread.md")))
        self.assertTrue(os.path.exists(os.path.join(folder, "comments.md")))
        self.assertTrue(os.path.exists(os.path.join(folder, "requotes.md")))
        self.assertTrue(os.path.exists(os.path.join(folder, "full_archive.md")))
        self.assertTrue(os.path.exists(os.path.join(folder, "thread_data.json")))
        self.assertTrue(os.path.exists(os.path.join(folder, "thread_data.txt")))
        self.assertTrue(os.path.exists(os.path.join(folder, "thread_view.html")))

        # Check requotes.md has the exact quoted tweet pointer
        with open(os.path.join(folder, "requotes.md"), "r", encoding="utf-8") as f:
            req_content = f.read()
            self.assertIn("Quoted Tweet #2 of Main Thread", req_content)
            self.assertIn("4) Relational alignment perspective.", req_content)

        # Check Mega JSON schema keys
        with open(os.path.join(folder, "thread_data.json"), "r", encoding="utf-8") as f:
            import json
            data = json.load(f)
            self.assertIn("thread_info", data)
            self.assertIn("main_thread", data)
            self.assertIn("comments_tree", data)
            self.assertIn("requotes", data)
            self.assertEqual(data["requotes"][0]["quoted_tweet_position"], 2)


if __name__ == "__main__":
    unittest.main()
