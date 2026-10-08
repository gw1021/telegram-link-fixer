import unittest
from datetime import datetime, timezone
from html import unescape
from urllib.parse import parse_qsl, urlsplit

from telegram import Chat, Message, User

from link_fixer_bot import build_message, collect_links, fix_url, format_author


class UrlTests(unittest.TestCase):
    def test_social_links_use_preview_domains(self):
        cases = [
            ("https://x.com/alice/status/123?s=20", "https://fixupx.com/alice/status/123"),
            ("http://www.twitter.com/alice/status/123?ref_src=test", "https://fixupx.com/alice/status/123"),
            ("https://mobile.twitter.com/alice/status/123/photo/1", "https://fixupx.com/alice/status/123/photo/1"),
            ("https://m.instagram.com/p/ABC/?igsh=tracking", "https://oginstagram.com/p/ABC/"),
            ("https://instagram.com/reel/ABC/?utm_source=test", "https://oginstagram.com/reel/ABC/"),
            ("https://instagram.com/reels/ABC/", "https://oginstagram.com/reels/ABC/"),
            ("https://instagram.com/tv/ABC/", "https://oginstagram.com/p/ABC/"),
            ("https://instagram.com/alice.tv/tv/ABC/", "https://oginstagram.com/alice.tv/p/ABC/"),
            ("https://instagram.com/alice/reel/ABC/", "https://oginstagram.com/alice/reel/ABC/"),
            ("https://www.tiktok.com/@alice/video/123?lang=ko", "https://tnktok.com/@alice/video/123"),
            ("https://tiktok.com/@alice/photo/123?is_from_webapp=1", "https://tnktok.com/@alice/photo/123"),
            ("https://www.reddit.com/r/python/comments/abc/title/?utm_source=test", "https://vxreddit.com/r/python/comments/abc/title/"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(fix_url(source), expected)

    def test_instagram_keeps_selected_carousel_item_without_tracking(self):
        self.assertEqual(
            fix_url("https://www.instagram.com/alice/p/ABC/?igsh=tracking&img_index=3&utm_source=share#item"),
            "https://oginstagram.com/alice/p/ABC/?img_index=3#item",
        )
        self.assertEqual(
            fix_url("https://instagram.com/p/ABC/2/?igsh=tracking"),
            "https://oginstagram.com/p/ABC/2/",
        )

    def test_tiktok_short_links_use_the_provider_short_link_routes(self):
        cases = [
            ("https://vm.tiktok.com/ZMabc123/?share_item_id=456", "https://tnktok.com/ZMabc123/"),
            ("https://vt.tiktok.com/ZSabc123", "https://tnktok.com/ZSabc123"),
            ("https://www.tiktok.com/t/ZTabc123/?_t=tracking", "https://tnktok.com/t/ZTabc123/"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(fix_url(source), expected)

    def test_reddit_short_links_and_old_domain_keep_the_post_or_comment(self):
        cases = [
            ("https://reddit.com/r/python/s/AbC123?utm_source=share", "https://vxreddit.com/r/python/s/AbC123"),
            ("https://redd.it/abc123?utm_medium=share", "https://vxreddit.com/abc123"),
            ("https://old.reddit.com/r/python/comments/abc/title/def/?context=3", "https://vxreddit.com/r/python/comments/abc/title/def/"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(fix_url(source), expected)

    def test_youtube_preserves_video_playlist_and_time(self):
        self.assertEqual(
            fix_url("https://www.youtube.com/watch?v=abc&list=PL123&t=90&si=tracking#chapter"),
            "https://www.youtube.com/watch?v=abc&list=PL123&t=90#chapter",
        )
        self.assertEqual(
            fix_url("https://youtu.be/abc?t=90&si=tracking"), "https://youtu.be/abc?t=90"
        )

    def test_generic_links_preserve_meaningful_query_values_and_fragment(self):
        source = "https://example.com:8443/path?a=1&a=2&empty=&q=%EA%B6%8C%EC%9A%B0+test&utm_source=x&FBCLID=y#section"
        result = urlsplit(fix_url(source))
        self.assertEqual(result.netloc, "example.com:8443")
        self.assertEqual(result.path, "/path")
        self.assertEqual(result.fragment, "section")
        self.assertEqual(
            parse_qsl(result.query, keep_blank_values=True),
            [("a", "1"), ("a", "2"), ("empty", ""), ("q", "권우 test")],
        )

    def test_unchanged_ignored_and_unsupported_links_are_not_rewritten(self):
        sources = [
            "https://example.com/?important=yes", "https://fixupx.com/alice/status/123",
            "https://youtube.com/watch?v=abc&list=PL123&t=90",
            "https://t.me/example/1?utm_source=test", "https://telegram.me/example?si=test",
            "https://x.com/alice", "https://instagram.com/share/abc/?igsh=test",
            "https://instagram.com/alice/", "https://tiktok.com/@alice",
            "https://reddit.com/r/python/", "https://instagram.com/p/",
            "https://tiktok.com/t/", "https://tiktok.com/@alice/video/123oops",
            "https://vm.tiktok.com/", "https://vt.tiktok.com/@alice",
            "https://reddit.com/r/python/s/", "https://redd.it/",
            "https://instagram.com.example.com/p/ABC/",
            "https://vt.tiktok.com.example.com/ZSabc123/",
            "https://old.reddit.com.example.com/r/python/comments/abc/",
            "https://oginstagram.com/p/ABC/?img_index=2",
            "https://tnktok.com/@alice/video/123", "https://vxreddit.com/r/python/s/AbC123",
        ]
        for source in sources:
            with self.subTest(source=source):
                self.assertIsNone(fix_url(source))

    def test_malformed_and_non_http_urls_are_rejected(self):
        for source in [
            "", "not a URL", "https://", "https://[invalid", "https://example.com:bad/?utm_a=x",
            "https://example.com:99999/?utm_a=x", "ftp://x.com/alice/status/123",
        ]:
            with self.subTest(source=source):
                self.assertIsNone(fix_url(source))


class CollectionTests(unittest.TestCase):
    def test_only_changed_messages_are_processed(self):
        for text in ["", "  ", "본문 https://x.com/alice/status/123", "https://example.com/"]:
            with self.subTest(text=text):
                self.assertIsNone(collect_links(text))

    def test_all_links_are_preserved_in_original_order(self):
        self.assertEqual(
            collect_links("https://t.me/example/1\nhttps://x.com/alice/status/123\n"
                          "https://example.com/\nhttps://twitter.com/alice/status/123"),
            (["https://fixupx.com/alice/status/123"],
             ["https://t.me/example/1", "https://fixupx.com/alice/status/123", "https://example.com/"]),
        )


class FormattingTests(unittest.TestCase):
    def message(self, user):
        return Message(
            message_id=1, date=datetime.now(timezone.utc),
            chat=Chat(id=-100123, type="supergroup"), from_user=user,
        )

    def test_names_keep_profile_identity_and_expected_order(self):
        cases = [
            ("권우", "최", "최권우"), ("민", "남궁", "남궁민"),
            ("John", "Smith", "John Smith"), ("최권우", None, "최권우"),
            ("별명🐱", None, "별명🐱"), ("닉네임", "긴별명", "닉네임 긴별명"),
        ]
        for first, last, expected in cases:
            with self.subTest(first=first, last=last):
                msg = self.message(User(id=123, first_name=first, last_name=last, is_bot=False))
                self.assertEqual(format_author(msg), f'<a href="tg://user?id=123">{expected}</a>')

    def test_html_special_characters_do_not_change_visible_name_or_url(self):
        msg = self.message(User(id=123, first_name='<b>A&B</b>', username="example_user", is_bot=False))
        link = "https://example.com/?a=1&b=2"
        body = build_message(msg, [link])
        self.assertIn("&lt;b&gt;A&amp;B&lt;/b&gt; (@example_user)", body)
        self.assertEqual(unescape(body.split("\n\n", 1)[1]), link)


if __name__ == "__main__":
    unittest.main()
