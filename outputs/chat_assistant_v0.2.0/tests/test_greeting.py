import unittest
from assistant.core import Conversation, Observation


class GreetingTests(unittest.TestCase):
    def test_greeting_commits_no_invented_incoming_message(self):
        session = Conversation("anonchat", "a")
        empty = Observation("a", "")
        reply = session.prepare_greeting(empty, lambda _: "Hello!")
        session.begin_send(empty, reply)
        session.resolve_send(True)
        self.assertEqual(session.history, [{"role": "assistant", "content": "Hello!"}])
        with self.assertRaises(ValueError):
            session.prepare_greeting(empty, lambda _: "Again")

    def test_new_message_blocks_stale_greeting(self):
        session = Conversation("anonchat", "a")
        reply = session.prepare_greeting(Observation("a", ""), lambda _: "Hello!")
        with self.assertRaisesRegex(ValueError, "Incoming text changed"):
            session.begin_send(Observation("a", "Hi"), reply)

    def test_existing_incoming_or_changed_recipient_blocks_greeting(self):
        session = Conversation("anonchat", "a")
        for observation in (Observation("a", "Hi"), Observation("b", "")):
            with self.assertRaises(ValueError):
                session.prepare_greeting(observation, lambda _: self.fail("Must not call model"))

    def test_pause_discards_late_greeting(self):
        session = Conversation("anonchat", "a")
        def model(_):
            session.pause()
            return "Hello!"
        with self.assertRaisesRegex(ValueError, "discarded"):
            session.prepare_greeting(Observation("a", ""), model)
        self.assertIsNone(session.pending)
