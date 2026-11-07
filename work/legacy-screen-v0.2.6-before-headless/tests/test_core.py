import unittest

from assistant.core import Conversation, Observation


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.chat = Conversation("telegram", "alice")
        self.observed = Observation("alice", "Hi there")

    def prepare(self):
        return self.chat.prepare(self.observed, lambda _: "Hello!")

    def test_context_is_not_shared_between_platforms(self):
        other = Conversation("anonchat", "alice")
        self.prepare()
        self.chat.begin_send(self.observed, "Hello!")
        self.chat.resolve_send(True)
        self.assertEqual(other.history, [])
        self.assertNotEqual(other.session_id, self.chat.session_id)

    def test_generation_does_not_commit_history(self):
        self.prepare()
        self.assertEqual(self.chat.history, [])

    def test_changed_recipient_blocks_generation(self):
        with self.assertRaisesRegex(ValueError, "Conversation changed"):
            self.chat.prepare(Observation("bob", "Hi"), lambda _: "Hello")

    def test_changed_recipient_blocks_send(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "Conversation changed"):
            self.chat.begin_send(Observation("bob", "Hi there"), "Hello")
        self.assertFalse(self.chat.uncertain)

    def test_new_incoming_blocks_stale_draft(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "Incoming text changed"):
            self.chat.begin_send(Observation("alice", "Are you there?"), "Hello")

    def test_pending_send_cannot_be_retried(self):
        self.prepare()
        self.chat.begin_send(self.observed, "Hello")
        with self.assertRaises(ValueError):
            self.chat.begin_send(self.observed, "Hello")
        with self.assertRaises(ValueError):
            self.prepare()

    def test_confirmed_delivery_commits_edited_reply(self):
        self.prepare()
        self.chat.begin_send(self.observed, "Hello, how are you?")
        self.chat.resolve_send(True)
        self.assertEqual(self.chat.history[-1]["content"], "Hello, how are you?")
        with self.assertRaisesRegex(ValueError, "already handled"):
            self.prepare()

    def test_failed_send_can_be_read_again_after_resolution(self):
        self.prepare()
        self.chat.begin_send(self.observed, "Hello")
        self.chat.resolve_send(False)
        self.assertEqual(self.chat.history, [])
        self.assertEqual(self.prepare(), "Hello!")

    def test_pause_during_generation_discards_reply(self):
        def model(_):
            self.chat.pause()
            return "Hello"
        with self.assertRaisesRegex(ValueError, "discarded"):
            self.chat.prepare(self.observed, model)
        self.assertIsNone(self.chat.pending)

    def test_pause_preserves_uncertain_send_for_reconciliation(self):
        self.prepare()
        self.chat.begin_send(self.observed, "Hello")
        self.chat.pause()
        self.assertTrue(self.chat.uncertain)
        self.chat.resolve_send(True)
        self.assertEqual(len(self.chat.history), 2)

    def test_invalid_model_output_is_rejected(self):
        for reply in ("", "  \n ", "x" * 1501):
            with self.assertRaises(ValueError):
                self.chat.prepare(self.observed, lambda _: reply)

    def test_model_error_clears_old_draft(self):
        self.prepare()
        def fail(_):
            raise TimeoutError("Model unavailable")
        with self.assertRaises(TimeoutError):
            self.chat.prepare(self.observed, fail)
        self.assertIsNone(self.chat.pending)
        self.assertEqual(self.chat.draft, "")

    def test_next_turn_receives_confirmed_context(self):
        self.prepare()
        self.chat.begin_send(self.observed, "Hello!")
        self.chat.resolve_send(True)
        captured = []
        def model(messages):
            captured.extend(messages)
            return "Fine, thanks!"
        self.chat.prepare(Observation("alice", "How are you?"), model)
        self.assertEqual([m["role"] for m in captured], ["user", "assistant", "user"])

    def test_rewrite_keeps_original_incoming_and_does_not_send(self):
        self.prepare()
        captured = []
        def model(messages):
            captured.extend(messages)
            return "Hey!"
        self.assertEqual(self.chat.rewrite("Hello there!", "Make it shorter", model), "Hey!")
        self.assertEqual(self.chat.pending, self.observed)
        self.assertEqual(self.chat.history, [])
        self.assertFalse(self.chat.uncertain)
        self.assertEqual(captured[-2]["content"], "Hello there!")
        self.assertIn("Make it shorter", captured[-1]["content"])

    def test_rewrite_failure_preserves_old_draft(self):
        self.prepare()
        with self.assertRaises(ValueError):
            self.chat.rewrite("Hello!", "Shorter", lambda _: "")
        self.assertEqual(self.chat.draft, "Hello!")

    def test_rewrite_cannot_run_during_unresolved_send(self):
        self.prepare()
        self.chat.begin_send(self.observed, "Hello!")
        with self.assertRaises(ValueError):
            self.chat.rewrite("Hello!", "Shorter", lambda _: "Hey")

    def test_pause_discards_rewrite_result(self):
        self.prepare()
        def model(_):
            self.chat.pause()
            return "Hey!"
        with self.assertRaisesRegex(ValueError, "discarded"):
            self.chat.rewrite("Hello!", "Shorter", model)
        self.assertIsNone(self.chat.pending)


if __name__ == "__main__":
    unittest.main()
