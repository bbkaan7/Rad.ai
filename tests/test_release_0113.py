"""Accessibility transport, background notifications and repeat friend lifecycles."""
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock
from xml.etree import ElementTree as ET
from aiohttp import web, ClientSession, ClientTimeout
from ayarlar import Settings
from rad.accessibility import AccessibilityClient, hierarchy
from rad.adb import AndroidBridge
from rad.anonchat import AnonChat
from rad.engine import Engine
from rad.domain import xml_root, snapshot, LayoutError, nodes
from rad.telegram import Telegram
from test_anon_xml import XML
from test_release_027 import SELECTORS
from test_identity_edges_0210 import transcript
from test_telegram_adb import S, conversation


def payload(root,package='io.anonchat'):
    def tree(node):return {'attributes':dict(node.attrib),'children':[tree(c) for c in node]}
    return {'available':True,'package':package,'tree':tree(root[0])}


class TreeTests(unittest.TestCase):
    def test_in_memory_tree_preserves_message_directions_and_header(self):
        source=xml_root(XML)
        self.assertEqual(snapshot(hierarchy(payload(source),'io.anonchat'),SELECTORS),snapshot(source,SELECTORS))

    def test_wrong_app_or_unavailable_cannot_be_used_for_send(self):
        for data in ({'available':False},payload(xml_root(XML),'org.vidogram.messenger')):
            with self.assertRaises(LayoutError):hierarchy(data,'io.anonchat')

    def test_bad_attributes_rejected(self):
        p=payload(xml_root(XML));p['tree']['attributes']['text']=False
        with self.assertRaises(LayoutError):hierarchy(p,'io.anonchat')

    def test_unbounded_tree_rejected(self):
        p=payload(xml_root(XML));p['tree']['children']=[{'attributes':{},'children':[]}]*6001
        with self.assertRaises(LayoutError):hierarchy(p,'io.anonchat')


class AccessibilityTests(unittest.IsolatedAsyncioTestCase):
    def client(self):return AccessibilityClient(AndroidBridge(Settings(accessibility_enabled=True)))

    async def test_event_wakes_reader_without_poll_interval(self):
        c=self.client();c.session='a'
        await c.consume({'session':'a','events':[{'seq':1,'type':'snapshot','package':'io.anonchat'}]})
        await asyncio.wait_for(c.wait('io.anonchat',10),.1)
        self.assertFalse(c.wake['io.anonchat'].is_set())

    async def test_replayed_notification_emitted_only_once(self):
        c=self.client();c.on_notification=AsyncMock();c.session='a'
        b={'session':'a','events':[{'seq':1,'type':'notification','package':'io.anonchat'}]}
        await c.consume(b);await c.consume(b)
        c.on_notification.assert_awaited_once()

    async def test_restarted_service_resets_cursor(self):
        c=self.client();c.session='old';c.cursor=500;c.on_notification=AsyncMock()
        await c.consume({'session':'new','events':[{'seq':1,'type':'notification','package':'io.anonchat'}]})
        self.assertEqual(c.cursor,1);c.on_notification.assert_awaited_once()

    async def test_event_gap_refreshes_all_platforms(self):
        c=self.client();c.session='a'
        await c.consume({'session':'a','events':[{'seq':500,'type':'snapshot','package':'io.anonchat'}]})
        self.assertTrue(c.wake['org.vidogram.messenger'].is_set())

    async def test_no_silent_xml_fallback(self):
        b=AndroidBridge(Settings(accessibility_enabled=True));b.shell=AsyncMock()
        with self.assertRaises(LayoutError):await b.dump('io.anonchat')
        b.shell.assert_not_awaited()

    async def test_a11y_dump_uses_fresh_tree_not_shell(self):
        b=AndroidBridge(Settings(accessibility_enabled=True));b.shell=AsyncMock();b.accessibility=Mock()
        b.accessibility.snapshot=AsyncMock(return_value=xml_root(XML))
        self.assertEqual(snapshot(await b.dump('io.anonchat'),SELECTORS)[0],'New partner')
        b.shell.assert_not_awaited()

    async def test_background_poller_never_launches_over_foreground_app(self):
        b=AndroidBridge(Settings(accessibility_enabled=True));b.activate=AsyncMock()
        b.watch('io.anonchat');b.accessibility=Mock()
        b.accessibility.request=AsyncMock(return_value={'available':True,'package':'org.vidogram.messenger'})
        async with b.poll_session('io.anonchat') as allowed:self.assertFalse(allowed)
        b.activate.assert_not_awaited()

    async def test_foreground_event_tree_is_used_once_inside_transaction(self):
        b=AndroidBridge(Settings(accessibility_enabled=True));b.activate=AsyncMock()
        b.watch('io.anonchat');b.accessibility=Mock()
        b.accessibility.request=AsyncMock(return_value=payload(xml_root(XML)))
        b.accessibility.snapshot=AsyncMock(return_value=xml_root(XML))
        async with b.poll_session('io.anonchat') as allowed:
            self.assertTrue(allowed)
            await b.dump('io.anonchat')
            b.accessibility.snapshot.assert_not_awaited()
            await b.dump('io.anonchat')
            b.accessibility.snapshot.assert_awaited_once()
        self.assertIsNone(b.read_snapshot)

    async def test_system_permission_window_never_triggers_background_launch(self):
        b=AndroidBridge(Settings(accessibility_enabled=True));b.activate=AsyncMock()
        b.watch('io.anonchat');b.accessibility=Mock()
        b.accessibility.request=AsyncMock(return_value={'available':False})
        async with b.poll_session('io.anonchat') as allowed:self.assertFalse(allowed)
        b.activate.assert_not_awaited()

    async def test_real_http_auth_and_snapshot(self):
        seen=[]
        async def handler(request):
            seen.append(request.headers.get('Authorization'))
            return web.json_response(payload(xml_root(XML)))
        app=web.Application();app.router.add_get('/snapshot',handler)
        runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
        c=self.client();port=site._server.sockets[0].getsockname()[1];c.base=f'http://127.0.0.1:{port}'
        c.http=ClientSession(headers={'Authorization':'Bearer test-token'},timeout=ClientTimeout(total=2))
        try:
            self.assertEqual(snapshot(await c.snapshot('io.anonchat'),SELECTORS)[0],'New partner')
            self.assertEqual(seen,['Bearer test-token'])
        finally:await c.close();await runner.cleanup()


class FriendshipTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        a=AnonChat(Settings(selectors=SELECTORS),AsyncMock(),Mock(),AsyncMock())
        a.lifecycle=AsyncMock();a.tap=AsyncMock();return a

    async def test_promotion_without_bio_keeps_original_history(self):
        a=self.adapter();await a.process(transcript());key=a.key;ids=[m.id for m in a.visible_messages]
        r=transcript('Alice',friend=True)
        for parent in r.iter():
            for n in list(parent):
                if n.get('content-desc','').startswith('About partner'):parent.remove(n)
        await a.process(r)
        self.assertEqual(a.key,key);self.assertEqual(ids,[m.id for m in a.visible_messages])
        self.assertIn(key,a.friends)

    async def test_second_friend_then_revisit_first_retains_both(self):
        a=self.adapter();await a.process(transcript());alice=a.key
        await a.process(transcript('Alice',friend=True))
        a.awaiting_match=a.saw_gap=True
        await a.process(transcript(incoming='Second question',outgoing='Second reply'));bob=a.key
        await a.process(transcript('Bob','Second question','Second reply',friend=True))
        self.assertNotEqual(alice,bob)
        await a.process(transcript('Alice',friend=True))
        self.assertEqual(a.key,alice);self.assertEqual(a.friend_keys,{'Alice':alice,'Bob':bob})
        self.assertIn(bob,a.sessions)

    async def test_search_home_does_not_close_friend(self):
        a=self.adapter();await a.process(transcript('Alice',friend=True));key=a.key
        a.lifecycle.reset_mock()
        await a.process(xml_root('<hierarchy><node content-desc="START SEARCHING"/></hierarchy>'))
        self.assertNotIn(key,a.retired);a.lifecycle.assert_not_awaited()

    async def test_open_saved_friend_does_not_delete_live_temp(self):
        a=self.adapter();await a.process(transcript('Alice','Alice hello','Alice reply',friend=True));alice=a.key
        a.awaiting_match=a.saw_gap=True
        await a.process(transcript());temp=a.key
        a.lifecycle.reset_mock()
        await a.process(transcript('Alice','Alice hello','Alice reply',friend=True))
        self.assertEqual(a.key,alice);self.assertNotIn(temp,a.retired)
        a.lifecycle.assert_not_awaited()
        await a.process(transcript())
        self.assertEqual(a.key,temp)

    async def test_historic_friend_notice_does_not_start_search_on_every_visit(self):
        a=self.adapter();a.auto_enabled=lambda:True;a.last_action=0
        a.ready_to_leave=lambda _:False
        await a.process(transcript('Alice',friend=True));key=a.key
        a.pending_friend_departure.discard(key);a.ready_to_leave=lambda _:True
        a.tap.reset_mock();await a.process(transcript('Alice',friend=True))
        a.tap.assert_not_awaited()

    async def test_accept_rename_with_overlap_survives_missing_confirmation_banner(self):
        from test_release_0112 import request_xml
        a=self.adapter();await a.process(transcript());key=a.key
        a.auto_enabled=lambda:True;a.dump=AsyncMock(return_value=transcript('Alice'))
        await a.process(request_xml())
        self.assertEqual(a.key,key);self.assertIn(key,a.friends)
        self.assertEqual(a.friend_keys['Alice'],key)

    async def test_unknown_target_cannot_navigate_or_send(self):
        a=self.adapter();await a.process(transcript())
        with self.assertRaises(LayoutError):await a.open_target_view(transcript(),'anonchat:unknown')
        a.tap.assert_not_awaited()


class InboxTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events=[];self.e=Engine(Settings(concurrent_monitoring=True),self.events.append)
    async def asyncTearDown(self):await self.e.close()

    def event(self):return {'id':'11111111-1111-1111-1111-111111111111','posted_at':10,'package':'io.anonchat','title':'Alice','text':'Hello','group':False}

    async def test_preview_is_immediate_but_never_becomes_llm_context(self):
        event=self.event();await self.e.inbox.receive(event)
        self.assertEqual(self.events[-1]['type'],'notification')
        self.assertEqual(self.e.chats,{})
        await self.e.inbox.receive(event)
        self.assertEqual(sum(e['type']=='notification' for e in self.events),1)

    async def test_group_notification_not_routed_to_private_chat(self):
        event=self.event();event['group']=True;await self.e.inbox.receive(event)
        self.assertFalse(self.e.inbox.pending)

    async def test_background_chat_waits_for_send_transaction(self):
        self.e.locks['anonchat:test']=asyncio.Lock()
        async with self.e.locks['anonchat:test']:
            self.assertFalse(await self.e.inbox.verify(self.event()))

    async def test_selecting_tab_does_not_stop_other_platform(self):
        await self.e.select_platform('telegram')
        self.assertIsNone(self.e.android.selected_package)


class TelegramBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_connect_imports_open_conversation_before_poll(self):
        settings=Settings(telegram_selectors=S)
        b=AndroidBridge(settings);b.connect=AsyncMock();b.activate=AsyncMock()
        a=Telegram(settings,AsyncMock(),Mock(),b);a.dump=AsyncMock(return_value=conversation())
        try:
            await a.connect()
            self.assertTrue(a.titles);self.assertTrue(a.histories)
            self.assertTrue(a.ingest.await_count)
        finally:await a.close()
