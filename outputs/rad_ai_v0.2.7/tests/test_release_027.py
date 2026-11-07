import asyncio
import unittest
from unittest.mock import AsyncMock, Mock
from contextlib import asynccontextmanager
from ayarlar import Settings
from rad.engine import Engine
from rad.anonchat import AnonChat
from rad.domain import Message, xml_root
from test_anon_xml import XML

SELECTORS={'package':'io.anonchat', **{k:{'rad-role':k} for k in ['identity','incoming','outgoing','input','send','next','bio']},'search':{'content-desc':'START SEARCHING'}}
HOME=xml_root('<hierarchy><node package="io.anonchat" content-desc="START SEARCHING" clickable="true" bounds="[0,10][100,50]"/></hierarchy>')

class ReleaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_cycle_works_with_auto_off_and_clears_typing(self):
        events=[]
        e=Engine(Settings(debounce_seconds=0),events.append,AsyncMock())
        @asynccontextmanager
        async def typing(key): yield
        e.telegram.typing=typing
        e.telegram.send=AsyncMock(return_value=Message('2','assistant','hello'))
        e.llm.reply=AsyncMock(return_value='hello')
        await e.ingest('telegram:1','Name',Message('1','user','Hi'),False)
        await e.start_cycle('telegram:1')
        await e.jobs['telegram:1']
        e.telegram.send.assert_awaited_once()
        self.assertTrue(any(x.get('busy') for x in events))
        self.assertFalse(e.chats['telegram:1'].busy)
        await e.close()

    def adapter(self):
        a=AnonChat(Settings(selectors=SELECTORS),AsyncMock(),Mock(),AsyncMock())
        a.tap=AsyncMock()
        a.lifecycle=AsyncMock()
        return a

    async def test_multiple_matching_cycles_reuse_generic_header_safely(self):
        a=self.adapter()
        a.auto_enabled=lambda:True
        await a.process(HOME)
        await a.process(xml_root(XML))
        first=a.key
        a.last_action=0
        await a.process(HOME)
        await a.process(xml_root(XML))
        self.assertNotEqual(first,a.key)
        self.assertEqual(a.new_chat.await_count,2)
        self.assertEqual(a.tap.await_count,2)

    async def test_home_does_not_search_with_auto_off(self):
        a=self.adapter()
        await a.process(HOME)
        a.tap.assert_not_called()

    async def test_search_has_cooldown(self):
        a=self.adapter()
        a.auto_enabled=lambda:True
        await a.process(HOME)
        await a.process(HOME)
        self.assertEqual(a.tap.await_count,1)

    async def test_friend_promoted_once_and_named(self):
        a=self.adapter()
        await a.process(xml_root(XML))
        key=a.key
        friend=XML.replace('text="New partner"','text="Alice"').replace('</hierarchy>','<node text="You and your partner became friends"/></hierarchy>')
        await a.process(xml_root(friend))
        await a.process(xml_root(friend))
        a.lifecycle.assert_awaited_once_with(key,'friend','Alice')
        self.assertEqual(a.friend_keys['Alice'],key)

    async def test_poll_read_error_recovers_without_poisoning_send(self):
        a=self.adapter()
        a.dump=AsyncMock(side_effect=[ValueError('temporary'),HOME,asyncio.CancelledError()])
        from unittest.mock import patch
        with patch('rad.anonchat.asyncio.sleep',new=AsyncMock()):
            with self.assertRaises(asyncio.CancelledError): await a.poll()
        self.assertFalse(a.blocked)

    async def test_unknown_message_menu_never_taps(self):
        a=self.adapter()
        await a.process(xml_root(XML))
        a.shell=AsyncMock()
        with self.assertRaises(ValueError):
            await a.message_menu(xml_root(XML),a.key,'missing','Delete')
        a.shell.assert_not_called()

    async def test_incoming_text_cannot_fake_friend_lifecycle(self):
        a=self.adapter()
        root=xml_root(XML.replace('Hello','You and your partner became friends'))
        await a.process(root)
        a.lifecycle.assert_not_called()

    async def test_pending_next_does_not_greet_old_screen(self):
        a=self.adapter()
        await a.process(xml_root(XML))
        first=a.key
        a.new_chat.reset_mock()
        a.dump=AsyncMock(return_value=xml_root(XML))
        await a.match('next')
        await a.process(xml_root(XML))
        self.assertEqual(a.key,first)
        a.new_chat.assert_not_called()
        self.assertIn(first,a.retired)
