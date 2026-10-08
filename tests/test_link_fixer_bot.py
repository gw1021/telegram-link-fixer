import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import create_autospec

from telegram import Bot, Chat, Message, PhotoSize, Update, User
from telegram.error import BadRequest, Forbidden, TimedOut

import link_fixer_bot


SOURCE = "https://x.com/alice/status/123?utm_source=test"
FIXED = "https://fixupx.com/alice/status/123"
AUTHOR = '<a href="tg://user?id=123">홍길동 &lt;&amp;&gt;</a>'


class HandleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = create_autospec(Bot, instance=True)
        self.context = SimpleNamespace(bot=self.bot)

    def message(self, **kwargs):
        data = dict(
            message_id=10,
            date=datetime.now(timezone.utc),
            chat=Chat(id=-100123, type="supergroup"),
            from_user=User(id=123, first_name="홍길동 <&>", is_bot=False),
            text=SOURCE,
        )
        data.update(kwargs)
        msg = Message(**data)
        msg.set_bot(self.bot)
        return msg

    async def handle(self, msg):
        await link_fixer_bot.handle(Update(update_id=1, message=msg), self.context)

    async def test_replacement_is_sent_before_original_is_deleted(self):
        await self.handle(self.message())

        self.assertEqual(
            [call[0] for call in self.bot.mock_calls],
            ["send_message", "delete_message"],
        )
        sent = self.bot.send_message.call_args.kwargs
        self.assertEqual(sent["chat_id"], -100123)
        self.assertEqual(sent["text"], f"공유자: {AUTHOR}\n\n{FIXED}")
        self.assertEqual(sent["parse_mode"], "HTML")
        self.assertIsNone(sent["reply_parameters"])
        self.assertIsNone(sent["message_thread_id"])
        self.assertEqual(sent["link_preview_options"].url, FIXED)
        deleted = self.bot.delete_message.call_args.kwargs
        self.assertEqual(deleted["chat_id"], -100123)
        self.assertEqual(deleted["message_id"], 10)

    async def test_unmodified_links_survive_and_duplicates_are_removed(self):
        unchanged = "https://example.com/page?important=yes&other=1"
        ignored = "https://t.me/example/42"
        await self.handle(self.message(text=f"{unchanged}\n{SOURCE}\n{ignored}\n{SOURCE}"))

        sent = self.bot.send_message.call_args.kwargs
        self.assertEqual(
            sent["text"],
            f"공유자: {AUTHOR}\n\nhttps://example.com/page?important=yes&amp;other=1\n{FIXED}\n{ignored}",
        )
        self.assertEqual(sent["link_preview_options"].url, FIXED)
        self.bot.delete_message.assert_awaited_once()

    async def test_username_is_visible_and_profile_uses_account_id(self):
        await self.handle(self.message(from_user=User(
            id=456, first_name="최 🐱 <권우>", is_bot=False, username="example_user"
        )))

        sent = self.bot.send_message.call_args.kwargs
        self.assertEqual(
            sent["text"],
            '공유자: <a href="tg://user?id=456">최 🐱 &lt;권우&gt; (@example_user)</a>'
            f"\n\n{FIXED}",
        )
        self.assertEqual(sent["parse_mode"], "HTML")
        self.assertEqual(sent["link_preview_options"].url, FIXED)

    async def test_send_failure_never_deletes_original(self):
        # Timeout may mean Telegram accepted the send: still keep the original.
        for error in (TimedOut(), BadRequest("Message is too long")):
            with self.subTest(error=type(error).__name__):
                self.bot.reset_mock()
                self.bot.send_message.side_effect = error
                with self.assertLogs("linkfixer", level="ERROR"):
                    await self.handle(self.message())
                self.bot.delete_message.assert_not_awaited()

    async def test_delete_failure_is_logged_without_resending(self):
        self.bot.delete_message.side_effect = Forbidden("Not enough rights")
        with self.assertLogs("linkfixer", level="ERROR"):
            await self.handle(self.message())
        self.bot.send_message.assert_awaited_once()
        self.bot.delete_message.assert_awaited_once()

    async def test_media_caption_is_replied_to_without_deleting_media(self):
        await self.handle(self.message(
            text=None,
            caption=SOURCE,
            photo=[PhotoSize(file_id="photo", file_unique_id="photo", width=10, height=10)],
        ))

        self.bot.delete_message.assert_not_awaited()
        sent = self.bot.send_message.call_args.kwargs
        self.assertEqual(sent["text"], FIXED)
        self.assertEqual(sent["reply_parameters"].message_id, 10)

    async def test_forum_topic_and_original_reply_target_are_preserved(self):
        parent = self.message(message_id=5, text="앞선 대화")
        await self.handle(self.message(
            message_thread_id=2, is_topic_message=True, reply_to_message=parent
        ))

        sent = self.bot.send_message.call_args.kwargs
        self.assertEqual(sent["message_thread_id"], 2)
        self.assertEqual(sent["reply_parameters"].message_id, 5)
        self.assertTrue(sent["reply_parameters"].allow_sending_without_reply)

    async def test_non_forum_reply_does_not_create_a_topic(self):
        await self.handle(self.message(message_thread_id=5))
        self.assertIsNone(self.bot.send_message.call_args.kwargs["message_thread_id"])

    async def test_anonymous_admin_uses_chat_name_as_author(self):
        await self.handle(self.message(
            from_user=User(id=1087968824, first_name="Group", is_bot=True),
            sender_chat=Chat(id=-100123, type="supergroup", title="우리 모임 <&>"),
        ))
        self.assertEqual(
            self.bot.send_message.call_args.kwargs["text"],
            f"공유자: 우리 모임 &lt;&amp;&gt;\n\n{FIXED}",
        )
        self.bot.delete_message.assert_awaited_once()

    async def test_ineligible_messages_are_left_untouched(self):
        cases = [
            {"text": f"이거 봐 {SOURCE}"},
            {"text": "https://example.com/unchanged"},
            {"text": "https://t.me/example/42"},
            {"text": FIXED},
            {"text": None},
            {"from_user": User(id=456, first_name="Bot", is_bot=True)},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                self.bot.reset_mock()
                await self.handle(self.message(**kwargs))
                self.bot.send_message.assert_not_awaited()
                self.bot.delete_message.assert_not_awaited()

    async def test_edited_message_is_left_untouched(self):
        await link_fixer_bot.handle(
            Update(update_id=1, edited_message=self.message()), self.context
        )
        self.bot.send_message.assert_not_awaited()
        self.bot.delete_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
