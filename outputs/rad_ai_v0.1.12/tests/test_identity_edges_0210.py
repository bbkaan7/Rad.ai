"""Regression coverage for lifecycle races and cross-person isolation."""

import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

from ayarlar import Settings
from rad.anonchat import AnonChat
from rad.domain import Message, xml_root
from rad.engine import Engine
from test_anon_xml import XML
from test_release_027 import SELECTORS


def transcript(name="New partner", incoming="Hello", outgoing="Hi back", *, friend=False):
    text = XML.replace('text="New partner"', f'text="{name}"')
    text = text.replace("Hello", incoming).replace("Hi back", outgoing)
    if friend:
        text = text.replace("</hierarchy>", '<node text="You and your partner became friends"/></hierarchy>')
    return xml_root(text)


class AnonIdentityEdges(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        selectors = {**SELECTORS, "input_placeholder": "Write a message..."}
        adapter = AnonChat(Settings(selectors=selectors), AsyncMock(), Mock(), AsyncMock())
        adapter.lifecycle = AsyncMock()
        adapter.tap = AsyncMock()
        adapter.shell = AsyncMock()
        return adapter

    async def test_historic_friend_notice_cannot_merge_two_people(self):
        adapter = self.adapter()
        await adapter.process(transcript("Alice", "Alice incoming", "Alice outgoing", friend=True))
        alice = adapter.key
        alice_ids = [message.id for message in adapter.visible_messages]
        await adapter.process(transcript("Bob", "Bob incoming", "Bob outgoing", friend=True))
        bob = adapter.key
        self.assertNotEqual(alice, bob)
        self.assertEqual(adapter.friend_keys["Alice"], alice)
        self.assertEqual(adapter.friend_keys["Bob"], bob)
        await adapter.process(transcript("Alice", "Alice incoming", "Alice outgoing", friend=True))
        self.assertEqual(adapter.key, alice)
        self.assertEqual([message.id for message in adapter.visible_messages], alice_ids)

    async def test_generic_acceptance_then_named_header_keeps_same_friend(self):
        adapter = self.adapter()
        await adapter.process(transcript())
        key = adapter.key
        ids = [message.id for message in adapter.visible_messages]
        await adapter.process(transcript(friend=True))
        # The acceptance notice can leave the viewport before the header is renamed.
        await adapter.process(transcript("Alice"))
        self.assertEqual(adapter.key, key)
        self.assertEqual(adapter.friend_keys["Alice"], key)
        self.assertEqual([message.id for message in adapter.visible_messages], ids)
        self.assertIn(key, adapter.friends)

    async def test_replacement_partner_after_typing_never_receives_draft(self):
        adapter = self.adapter()
        before = transcript()
        await adapter.process(before)
        typed = xml_root(XML.replace("About partner, Music", "About partner, Travel")
                         .replace('text="Write a message..."', 'text="A response"'))
        adapter.dump = AsyncMock(side_effect=[before] + [typed] * 6)
        with self.assertRaises(ValueError):
            await adapter.send(adapter.key, "A response")
        # Focusing the original composer is permitted; touching Send is not.
        self.assertEqual(adapter.tap.await_count, 1)
        self.assertTrue(adapter.blocked)

    async def test_replacement_partner_blocks_outgoing_message_menu(self):
        adapter = self.adapter()
        await adapter.process(transcript())
        outgoing = next(message for message in adapter.visible_messages if message.role == "assistant")
        changed = xml_root(XML.replace("About partner, Music", "About partner, Travel"))
        adapter.dump = AsyncMock(return_value=changed)
        with self.assertRaises(ValueError):
            await adapter.delete(adapter.key, outgoing)
        adapter.shell.assert_not_awaited()
        adapter.tap.assert_not_awaited()


class EngineIdentityEdges(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events = []
        self.engine = Engine(Settings(selectors=SELECTORS, debounce_seconds=0), self.events.append)
        self.engine.llm = Mock(reply=AsyncMock(return_value="A response"), close=AsyncMock())

    async def asyncTearDown(self):
        await self.engine.close()

    async def test_closed_temporary_chat_is_removed_without_stale_resurrection(self):
        engine = self.engine
        key = "anonchat:temporary"
        await engine.ingest(key, "AnonChat · New partner", Message("1", "user", "Hello"), False)
        retired = engine.chats[key]
        await engine.lifecycle(key, "ended")
        self.assertNotIn(key, engine.chats)
        self.assertTrue(any(event.get("type") == "chat_removed" and event.get("key") == key for event in self.events))
        self.events.clear()
        engine.view(retired)
        engine.recheck(key)
        await engine.ingest(key, "AnonChat · New partner", Message("2", "user", "Late snapshot"), True)
        self.assertNotIn(key, engine.chats)
        self.assertFalse(any(event.get("type") == "chat" and event.get("key") == key for event in self.events))

    async def test_closed_friend_retains_original_key_and_history(self):
        engine = self.engine
        key = "anonchat:friend"
        await engine.ingest(key, "AnonChat · New partner", Message("1", "user", "Hello"), False)
        original = engine.chats[key]
        await engine.lifecycle(key, "friend", "Alice")
        await engine.lifecycle(key, "ended")
        self.assertIs(engine.chats[key], original)
        self.assertEqual(original.category, "Friends")
        self.assertEqual([message.text for message in original.messages], ["Hello"])
        self.assertFalse(any(event.get("type") == "chat_removed" for event in self.events))

    async def test_handoff_keeps_context_after_nonfriend_source_is_removed(self):
        engine = self.engine
        source = "anonchat:source"
        target = "telegram:target"
        await engine.ingest(source, "AnonChat · New partner", Message("1", "user", "I like music"), False)
        person_id = engine.chats[source].person_id
        await engine.create_handoff(source)
        code = next(event["code"] for event in self.events if event.get("type") == "handoff")
        await engine.lifecycle(source, "ended")
        self.assertNotIn(source, engine.chats)
        await engine.ingest(target, "Different display name", Message("1", "user", code), True)
        self.assertEqual(engine.chats[target].person_id, person_id)
        self.assertIn({"role": "user", "content": "I like music"}, engine.chats[target].linked_context)
        self.assertEqual(engine.chats[target].received, 0)

    async def test_reconciliation_only_handles_generated_batch(self):
        engine = self.engine
        key = "telegram:pending"
        await engine.ingest(key, "Alice", Message("1", "user", "First question"), True)

        async def generation(context):
            await engine.ingest(key, "Alice", Message("2", "user", "Second question"), True)
            return "Answer to the first question"

        engine.llm.reply.side_effect = generation
        engine.telegram.send = AsyncMock(side_effect=TimeoutError("Submission needs verification"))
        engine.telegram.reconcile = AsyncMock()
        await engine.respond(key, once=True)
        self.assertTrue(engine.chats[key].uncertain)
        await engine.reconcile(key)
        self.assertEqual(engine.chats[key].handled, 1)
        self.assertEqual(engine.chats[key].received, 2)

    async def test_cycle_can_answer_pending_input_despite_last_outgoing(self):
        engine = self.engine
        key = "telegram:queued"
        await engine.ingest(key, "Alice", Message("1", "user", "A pending question"), True)
        await engine.ingest(key, "Alice", Message("2", "assistant", "Earlier answer finished later"), False)
        engine.telegram.send = AsyncMock(return_value=Message("3", "assistant", "A response"))
        await engine.start_cycle(key)
        await asyncio.wait_for(engine.jobs[key], timeout=1)
        engine.telegram.send.assert_awaited_once()
        self.assertEqual(engine.chats[key].handled, 1)
