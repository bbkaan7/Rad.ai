import asyncio
import unittest
from unittest.mock import AsyncMock,Mock
from xml.etree import ElementTree as ET
from ayarlar import Settings
from rad.anonchat import AnonChat
from rad.adb import AndroidBridge
from rad.domain import xml_root,nodes,snapshot,Message,SendRejected,ForegroundDeferred
from rad.engine import Engine
from rad.handoff import Handoffs
from test_anon_xml import XML
from test_release_027 import SELECTORS

class ParserHotfixTests(unittest.TestCase):
    def test_nested_scroller_cannot_become_header(self):
        root=xml_root(XML)
        pane=nodes(root,{'rad-role':'bio'})[0]
        ET.SubElement(pane,'node',{'package':'io.anonchat','class':'android.widget.ScrollView','bounds':'[0,300][540,610]'})
        self.assertEqual(snapshot(root,SELECTORS)[0],'New partner')

    def test_header_and_history_work_without_composer(self):
        root=xml_root(XML)
        for p in root.iter():
            for n in list(p):
                if n.get('class')=='android.widget.EditText':p.remove(n)
        self.assertEqual(snapshot(root,SELECTORS)[0],'New partner')
        self.assertEqual(len(snapshot(root,SELECTORS)[1]),2)

    def test_grouped_message_without_timestamp_is_read(self):
        root=xml_root(XML)
        for p in root.iter():
            for n in list(p):
                if n.get('text')=='5:49 AM':p.remove(n)
        self.assertIn(('user','Hello'),snapshot(root,SELECTORS)[1])

    def test_last_seen_subtitle_is_not_a_second_identity(self):
        r=xml_root(XML.replace('text="New partner"','text="Alice"').replace('text="online"','text="last seen 2 hours ago"'))
        self.assertEqual(snapshot(r,SELECTORS)[0],'Alice')

    def test_friends_list_is_not_a_conversation(self):
        r=xml_root('<hierarchy><node package="io.anonchat" bounds="[0,0][540,960]"><node package="io.anonchat" class="android.widget.TextView" text="Friends" bounds="[0,25][540,49]"/><node package="io.anonchat" class="android.widget.ScrollView" bounds="[0,72][540,900]"/></node></hierarchy>')
        self.assertEqual(nodes(r,{'rad-role':'identity'}),[])

class StateHotfixTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        a=AnonChat(Settings(selectors=SELECTORS),AsyncMock(),Mock(),AsyncMock())
        a.lifecycle=AsyncMock();a.tap=AsyncMock()
        return a

    async def test_bio_scrolling_out_does_not_create_chat(self):
        a=self.adapter();await a.process(xml_root(XML));key=a.key
        root=xml_root(XML)
        for p in root.iter():
            for n in list(p):
                if n.get('content-desc','').startswith('About partner'):p.remove(n)
        await a.process(root)
        self.assertEqual(a.key,key)
        a.lifecycle.assert_not_called()

    async def test_friend_promotion_keeps_message_objects_and_key(self):
        a=self.adapter();await a.process(xml_root(XML));key=a.key
        ids=[m.id for m in a.visible_messages]
        friend=XML.replace('text="New partner"','text="Alice"').replace('</hierarchy>','<node text="You and your partner became friends"/></hierarchy>')
        await a.process(xml_root(friend))
        self.assertEqual(a.key,key)
        self.assertEqual(ids,[m.id for m in a.visible_messages])
        self.assertEqual(a.friend_keys['Alice'],key)
        a.lifecycle.assert_awaited_once_with(key,'friend','Alice')

    async def test_old_closed_notice_does_not_close_live_friend_chat(self):
        a=self.adapter();await a.process(xml_root(XML));key=a.key
        friend=XML.replace('text="New partner"','text="Alice"').replace('</hierarchy>','<node text="You ended chat"/><node text="You and your partner became friends"/></hierarchy>')
        await a.process(xml_root(friend));await a.process(xml_root(friend))
        a.lifecycle.assert_awaited_once_with(key,'friend','Alice')
        self.assertNotIn(key,a.retired)

    async def test_closed_notice_without_composer_archives_same_chat(self):
        a=self.adapter();await a.process(xml_root(XML));key=a.key
        root=xml_root(XML.replace('</hierarchy>','<node text="Chat was ended by your partner"/></hierarchy>'))
        for p in root.iter():
            for n in list(p):
                if n.get('class')=='android.widget.EditText':p.remove(n)
        await a.process(root);await a.process(root)
        self.assertEqual(a.key,key)
        a.lifecycle.assert_awaited_once_with(key,'ended')

    async def test_message_cannot_fake_closed_notice(self):
        a=self.adapter();await a.process(xml_root(XML.replace('Hello','Chat was ended by your partner')))
        a.lifecycle.assert_not_called()

    async def test_list_or_unreadable_view_is_not_a_new_person(self):
        a=self.adapter();await a.process(xml_root(XML));key=a.key
        await a.process(xml_root('<hierarchy><node package="io.anonchat" text="Alice"/></hierarchy>'))
        await a.process(xml_root(XML))
        self.assertEqual(a.key,key)
        a.lifecycle.assert_not_called()

    async def test_reply_job_prevents_auto_next_after_friendship(self):
        a=self.adapter();await a.process(xml_root(XML));a.auto_enabled=lambda:True
        a.ready_to_leave=lambda key:False
        await a.process(xml_root(XML.replace('</hierarchy>','<node text="You and your partner became friends"/></hierarchy>')))
        a.tap.assert_not_called()

    async def test_selected_platform_blocks_other_poller_and_actions(self):
        b=AndroidBridge(Settings());b.watch('io.anonchat');b.watch('org.vidogram.messenger')
        b.select_platform('org.vidogram.messenger');b.activate=AsyncMock()
        self.assertFalse(b.poll_allowed('io.anonchat'))
        self.assertTrue(b.poll_allowed('org.vidogram.messenger'))
        with self.assertRaises(ForegroundDeferred):
            async with b.session('io.anonchat'):pass
        b.activate.assert_not_called()

    async def test_selection_change_does_not_interrupt_transaction(self):
        b=AndroidBridge(Settings());b.select_platform('io.anonchat');b.activate=AsyncMock()
        async with b.session('io.anonchat'):
            b.select_platform('org.vidogram.messenger')
            self.assertTrue(b.lock.locked())
        self.assertFalse(b.lock.locked())

    async def test_rejected_preflight_is_not_uncertain_send(self):
        e=Engine(Settings(selectors=SELECTORS),lambda x:None)
        await e.ingest('telegram:a','A',Message('1','user','Hi'),False)
        e.telegram.send=AsyncMock(side_effect=SendRejected('Draft present'))
        with self.assertRaises(SendRejected):await e.manual('telegram:a','Hi')
        self.assertFalse(e.chats['telegram:a'].uncertain)
        await e.close()

    async def test_closed_chat_cannot_start_cycle(self):
        e=Engine(Settings(),lambda x:None)
        await e.ingest('anonchat:a','A',Message('1','user','Hi'),False)
        await e.lifecycle('anonchat:a','ended')
        with self.assertRaisesRegex(ValueError,'Chat closed'):await e.start_cycle('anonchat:a')
        await e.close()

    async def test_verified_handoff_keeps_distinct_routes(self):
        e=Engine(Settings(),lambda x:None)
        await e.ingest('anonchat:a','Alex',Message('1','user','I like music'),False)
        code=e.handoffs.issue('anonchat:a')
        await e.ingest('telegram:b','Alex',Message('1','user',code),True)
        await e.ingest('telegram:c','Alex',Message('1','user','Hello'),True)
        self.assertEqual(e.chats['anonchat:a'].person_id,e.chats['telegram:b'].person_id)
        self.assertNotEqual(e.chats['telegram:b'].person_id,e.chats['telegram:c'].person_id)
        self.assertEqual(e.chats['telegram:b'].linked_context[0]['content'],'I like music')
        self.assertNotIn('telegram:c',e.handoffs.links)
        await e.close()

class ReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def test_check_send_reads_without_resending(self):
        a=AnonChat(Settings(selectors=SELECTORS),AsyncMock(),Mock(),AsyncMock())
        await a.process(xml_root(XML))
        a.pending_send={'key':a.key,'text':'Hi back','before':[]}
        a.blocked=True
        a.dump=AsyncMock(return_value=xml_root(XML))
        a.shell=AsyncMock()
        await a.reconcile(a.key)
        a.shell.assert_not_called()
        self.assertFalse(a.blocked)
        self.assertIsNone(a.pending_send)

    async def test_no_evidence_keeps_send_blocked(self):
        a=AnonChat(Settings(selectors=SELECTORS),AsyncMock(),Mock(),AsyncMock())
        await a.process(xml_root(XML))
        a.pending_send={'key':a.key,'text':'Not sent','before':[]}
        a.blocked=True
        a.dump=AsyncMock(return_value=xml_root(XML));a.shell=AsyncMock()
        with self.assertRaisesRegex(ValueError,'unverified'):await a.reconcile(a.key)
        self.assertTrue(a.blocked)
        a.shell.assert_not_called()

class HandoffTests(unittest.TestCase):
    def test_expired_code_cannot_link(self):
        h=Handoffs();h.clock=lambda:1;code=h.issue('anon:a');h.clock=lambda:602
        self.assertIsNone(h.consume(code,'tg:a'))

    def test_one_time_exact_code_and_no_reassignment(self):
        h=Handoffs();code=h.issue('anon:a')
        self.assertIsNone(h.consume('please link '+code,'tg:a'))
        self.assertEqual(h.consume(code,'tg:a'),'anon:a')
        self.assertIsNone(h.consume(code,'tg:b'))
        other=h.issue('anon:b');self.assertIsNone(h.consume(other,'tg:a'))
