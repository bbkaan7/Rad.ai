"""Behavioral checks for greeting order, matching and Telegram recipient continuity."""
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch
from xml.etree import ElementTree as ET

from ayarlar import Settings
from rad.adb import AndroidBridge
from rad.anonchat import AnonChat
from rad.domain import Message, SendRejected, LayoutError, xml_root
from rad.engine import Engine
from rad.telegram import Telegram
from test_anon_xml import XML
from test_release_027 import SELECTORS, HOME
from test_telegram_adb import S, conversation


class ReconnectFlow(unittest.IsolatedAsyncioTestCase):
    async def test_offline_boot_reconnects_only_configured_emulator(self):
        b=AndroidBridge(Settings(adb_serial='127.0.0.1:5585',adb_device_port=5585))
        b.lease=Mock()
        client=Mock();device=Mock(serial='127.0.0.1:5585')
        client.devices.side_effect=[[],[device]]
        with patch('rad.adb.TimedClient',return_value=client),patch('rad.adb.asyncio.sleep',new=AsyncMock()):
            await b.connect()
        self.assertIs(b.device,device)
        client.remote_disconnect.assert_called_once_with('127.0.0.1',5585)
        client.devices.assert_called_with(state='device')
        await b.close()

    async def test_recovery_never_replays_an_input_command(self):
        b=AndroidBridge(Settings())
        b.device=Mock()
        b.device.shell.side_effect=RuntimeError('device offline')
        b.connect_device=AsyncMock()
        with self.assertRaisesRegex(LayoutError,'not retried'):
            await b.shell('input tap 20 30')
        b.device.shell.assert_called_once()
        b.connect_device.assert_awaited_once()


class TelegramContinuity(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bridge=AndroidBridge(Settings())
        bridge.activate=AsyncMock()
        bridge.shell=AsyncMock(return_value='')
        self.t=Telegram(Settings(telegram_selectors=S),AsyncMock(),Mock(),bridge)
        self.t.lifecycle=AsyncMock()
        self.key=await self.t.process(conversation())

    async def test_same_title_different_history_does_not_replace_original(self):
        t=self.t
        original=list(t.histories[self.key])
        await t.process(conversation(incoming='Different person'))
        self.assertEqual(t.histories[self.key],original)
        self.assertIn(self.key,t.quarantined)
        t.lifecycle.assert_awaited_once_with(self.key,'identity_unverified')
        t.dump=AsyncMock(return_value=conversation(incoming='Different person'))
        with self.assertRaises(SendRejected):await t.send(self.key,'Reply')
        t.bridge.shell.assert_not_awaited()

    async def test_same_title_replacement_after_typing_cannot_receive_reply(self):
        t=self.t
        t.dump=AsyncMock(side_effect=[conversation(),conversation(incoming='Different person',entry='Reply')])
        t.tap_send=AsyncMock()
        with self.assertRaises(ValueError):await t.send(self.key,'Reply')
        t.tap_send.assert_not_awaited()
        self.assertIn(self.key,t.quarantined)
        self.assertTrue(t.blocked)

    async def test_restoring_original_transcript_removes_adapter_quarantine(self):
        await self.t.process(conversation(incoming='Different person'))
        await self.t.process(conversation())
        self.assertNotIn(self.key,self.t.quarantined)
        self.assertEqual(len(self.t.messages[self.key]),1)

    async def test_quarantined_message_cannot_be_deleted(self):
        t=self.t
        await t.process(conversation(outgoing='My reply'))
        outgoing=t.messages[self.key][-1][0]
        await t.process(conversation(incoming='Different person'))
        t.dump=AsyncMock(return_value=conversation(incoming='Different person'))
        with self.assertRaises(ValueError):await t.delete(self.key,outgoing)
        t.bridge.shell.assert_not_awaited()


class OpeningFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.e=Engine(Settings(selectors=SELECTORS,debounce_seconds=0),lambda event:None)
        self.e.auto=True
        self.e.llm.reply=AsyncMock(return_value='How is your day?')
        self.e.anon.send=AsyncMock(return_value=None)

    async def asyncTearDown(self):
        await self.e.close()

    async def test_first_incoming_does_not_preempt_fixed_greeting(self):
        e=self.e
        e.anon.match_requested=True
        await e.anon.process(xml_root(XML),allow_actions=False)
        key=e.anon.key
        await asyncio.wait_for(e.jobs[key],1)
        self.assertEqual([call.args[1] for call in e.anon.send.await_args_list],['hii :3','How is your day?'])
        self.assertEqual(e.chats[key].received,e.chats[key].handled)

    async def test_uncertain_greeting_does_not_consume_incoming_message(self):
        e=self.e
        key='anonchat:greeting'
        await e.ingest(key,'Partner',Message('1','user','My question'),False)
        e.chats[key].received=1
        e.anon.send.side_effect=TimeoutError('Unknown submission')
        await e.open_match(key,'Music')
        self.assertEqual(e.chats[key].pending_handled,0)
        self.assertTrue(e.chats[key].uncertain)

    async def test_bio_reply_reconciliation_preserves_later_input(self):
        e=self.e
        key='anonchat:bio'
        await e.ingest(key,'Partner',None,False)
        async def reply(*args):
            await e.ingest(key,'Partner',Message('1','user','A new question'),False)
            e.chats[key].received+=1
            return 'Bio opener'
        e.llm.reply.side_effect=reply
        e.anon.send.side_effect=[None,TimeoutError('Unknown submission')]
        await e.open_match(key,'Music')
        self.assertEqual(e.chats[key].pending_handled,0)
        self.assertEqual(e.chats[key].received,1)

    async def test_friend_search_preserves_history_and_taps_navigation_then_search(self):
        a=AnonChat(Settings(selectors=SELECTORS),AsyncMock(),Mock(),AsyncMock())
        a.tap=AsyncMock();a.lifecycle=AsyncMock()
        root=xml_root(XML.replace('text="New partner"','text="Alice"').replace('</hierarchy>','<node text="You and your partner became friends"/></hierarchy>'))
        for i in range(3):
            ET.SubElement(root,'node',{'package':'io.anonchat','class':'android.view.View','clickable':'true','bounds':f'[{i*180},911][{(i+1)*180},960]'})
        await a.process(root)
        original=a.key
        a.lifecycle.reset_mock()
        a.dump=AsyncMock(side_effect=[root,HOME])
        await a.match('search')
        self.assertEqual(a.tap.await_count,2)
        self.assertIn(original,a.friends)
        a.lifecycle.assert_not_awaited()
        self.assertTrue(a.awaiting_match)

    async def test_next_with_same_bio_and_replaced_history_creates_one_new_person(self):
        a=AnonChat(Settings(selectors=SELECTORS),AsyncMock(),Mock(),AsyncMock())
        a.tap=AsyncMock();a.lifecycle=AsyncMock()
        await a.process(xml_root(XML))
        old=a.key
        a.dump=AsyncMock(return_value=xml_root(XML))
        await a.match('next')
        await a.process(xml_root(XML.replace('Hello','New incoming').replace('Hi back','Different outgoing')))
        self.assertNotEqual(a.key,old)
        self.assertIn(old,a.retired)
        a.new_chat.assert_awaited_once()
