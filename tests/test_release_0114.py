"""Hotfix regressions: pending greetings, navigation, ownership and model timeouts."""
import asyncio
import json
import tempfile
import unittest
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock,Mock,patch
from xml.etree import ElementTree as ET
from ayarlar import Settings,save,validate
from rad.adb import AndroidBridge
from rad.anonchat import AnonChat
from rad.anon_xml import conversation_menu
from rad.domain import nodes,xml_root,LayoutError
from rad.engine import Engine
from rad.llm import Ollama
from rad.telegram import Telegram
from rad.typing_draft import WaitingDraft,waiting_typing,clear_waiting
from test_anon_xml import XML
from test_release_027 import SELECTORS
from test_telegram_adb import S,conversation,dialogs
from test_release_0113 import payload


class NavigationTests(unittest.IsolatedAsyncioTestCase):
    async def test_closed_menu_is_opened_before_next_or_end(self):
        for action in ('next','end'):
            a=AnonChat(Settings(selectors=SELECTORS,accessibility_enabled=True),AsyncMock(),Mock(),AsyncMock())
            root=xml_root(XML);app=root[0]
            header=nodes(root,SELECTORS['identity'])[0];app.remove(header)
            wrapper=ET.SubElement(app,'node',{'clickable':'true','package':'io.anonchat','bounds':'[60,20][450,70]'})
            wrapper.append(header)
            for n in list(app):
                if n.get('content-desc')=='New partner':app.remove(n)
            opened=xml_root(ET.tostring(root,encoding='unicode'))
            ET.SubElement(opened[0],'node',{'package':'io.anonchat','content-desc':'New partner' if action=='next' else 'End chat','clickable':'true','bounds':'[15,831][525,886]'})
            a.dump=AsyncMock(return_value=opened);a.tap=AsyncMock()
            await a.match_view(root,action)
            self.assertEqual(a.tap.await_count,2)
            self.assertIs(a.tap.call_args_list[0].args[0],wrapper)
            self.assertEqual(a.tap.call_args_list[1].args[0].get('content-desc'),'New partner' if action=='next' else 'End chat')

    async def test_empty_chat_seen_before_auto_is_greeted_once_after_auto(self):
        e=Engine(Settings(selectors=SELECTORS),lambda event:None)
        e.open_match=AsyncMock()
        root=xml_root(XML)
        pane=next(n for n in root.iter('node') if n.get('class')=='android.widget.ScrollView')
        pane.clear();pane.attrib.update({'class':'android.widget.ScrollView','package':'io.anonchat','bounds':'[0,72][540,630]'})
        await e.anon.process(root,allow_actions=False)
        key=e.anon.key
        self.assertIn(key,e.anon.pending_greetings)
        await e.set_auto(True);await e.jobs[key]
        await e.anon.process(root,allow_actions=False)
        e.open_match.assert_awaited_once()
        self.assertEqual(e.anon.key,key)
        await e.close()

    async def test_telegram_foreground_chat_never_rotates_or_resumes_discovery(self):
        t=Telegram(Settings(accessibility_enabled=True,telegram_selectors=S),AsyncMock(),Mock())
        @asynccontextmanager
        async def allowed(*args):yield True
        t.polling_session=allowed;t.dump=AsyncMock(return_value=conversation())
        t.titles={t.key_for('Bob'):'Bob'};t.discovery_pending=True
        t.open_chat=AsyncMock();t.list_root=AsyncMock();t.discover_once=AsyncMock()
        for _ in range(3):await t.poll_once(True)
        t.open_chat.assert_not_awaited();t.list_root.assert_not_awaited();t.discover_once.assert_not_awaited()
        self.assertIn(t.key_for('Alice'),t.histories)

    async def test_telegram_list_poll_does_not_open_first_known_chat(self):
        t=Telegram(Settings(accessibility_enabled=True,telegram_selectors=S),AsyncMock(),Mock())
        @asynccontextmanager
        async def allowed(*args):yield True
        t.polling_session=allowed;t.dump=AsyncMock(return_value=dialogs());t.tap=AsyncMock()
        t.open_chat=AsyncMock();await t.poll_once(True)
        self.assertEqual(len(t.titles),2);t.tap.assert_not_awaited();t.open_chat.assert_not_awaited()


class DraftTests(unittest.IsolatedAsyncioTestCase):
    async def adapter(self):
        settings=Settings(telegram_selectors=S,accessibility_enabled=True,typing_delay_seconds=.01,typing_interval_seconds=.01)
        b=AndroidBridge(settings);b.accessibility=Mock();b.accessibility.draft_edit=True
        t=Telegram(settings,AsyncMock(),Mock(),b)
        self.root=conversation();key=await t.process(self.root)
        async def read():return self.root
        async def state():return payload(self.root,t.package)
        async def edit(package,header,before,after):
            entry=nodes(self.root,S['input'])[0];current=entry.get('text')
            if current=='Message':current=''
            if current!=before:return False
            entry.set('text',after);return True
        t.dump=read;b.accessibility.request=AsyncMock(side_effect=lambda *args:state())
        # AsyncMock side effects must await the fixture coroutine themselves.
        async def request(*args):return await state()
        b.accessibility.request=AsyncMock(side_effect=request)
        b.accessibility.edit_draft=AsyncMock(side_effect=edit)
        return t,key

    async def test_temporary_text_is_cleared_on_success_without_send(self):
        t,key=await self.adapter();t.send=AsyncMock()
        async with waiting_typing(t,key):
            await asyncio.sleep(.06)
            self.assertTrue(nodes(self.root,S['input'])[0].get('text'))
        self.assertEqual(nodes(self.root,S['input'])[0].get('text'),'')
        self.assertNotIn(key,t.waiting_drafts);t.send.assert_not_awaited()

    async def test_timeout_cleans_owned_draft_and_preserves_original_error(self):
        t,key=await self.adapter()
        with self.assertRaisesRegex(TimeoutError,'model timeout'):
            async with waiting_typing(t,key):
                await asyncio.sleep(.04);raise TimeoutError('model timeout')
        self.assertEqual(nodes(self.root,S['input'])[0].get('text'),'')

    async def test_owner_edit_is_never_erased(self):
        t,key=await self.adapter()
        async with waiting_typing(t,key):
            await asyncio.sleep(.04)
            nodes(self.root,S['input'])[0].set('text','Owner draft')
        self.assertEqual(nodes(self.root,S['input'])[0].get('text'),'Owner draft')
        with self.assertRaises(LayoutError):await clear_waiting(t,key,self.root)
        nodes(self.root,S['input'])[0].set('text','')
        await clear_waiting(t,key,self.root)
        self.assertNotIn(key,t.waiting_drafts)

    async def test_other_chat_or_background_app_receives_no_waiting_text(self):
        t,key=await self.adapter();draft=WaitingDraft(t,key)
        self.root=conversation(title='Bob');await draft.advance()
        t.bridge.accessibility.edit_draft.assert_not_awaited()
        t.bridge.accessibility.request=AsyncMock(return_value={'available':True,'package':'io.anonchat'})
        await draft.advance();t.bridge.accessibility.edit_draft.assert_not_awaited()

    async def test_fast_generation_does_not_touch_android(self):
        t,key=await self.adapter()
        async with waiting_typing(t,key):pass
        t.bridge.accessibility.request.assert_not_awaited();t.bridge.accessibility.edit_draft.assert_not_awaited()

    async def test_cancel_waits_for_cleanup(self):
        t,key=await self.adapter()
        async def run():
            async with waiting_typing(t,key):await asyncio.sleep(60)
        task=asyncio.create_task(run());await asyncio.sleep(.04);task.cancel()
        await asyncio.gather(task,return_exceptions=True)
        self.assertEqual(nodes(self.root,S['input'])[0].get('text'),'')


class SettingsTests(unittest.TestCase):
    def test_atomic_save_keeps_platform_selectors_and_model(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json';s=Settings(model='owner-model',selectors=SELECTORS,telegram_selectors=S)
            save(s,path);saved=json.loads(path.read_text())
            self.assertEqual(saved['selectors'],SELECTORS);self.assertEqual(saved['model'],'owner-model')
            self.assertEqual(saved['llm_timeout_seconds'],300)
            self.assertEqual(list(Path(folder).glob('*.tmp')),[])

    def test_invalid_timing_is_rejected(self):
        for value in (-1,float('nan'),float('inf'),0,2000):
            with self.assertRaises(ValueError):validate(replace(Settings(),llm_timeout_seconds=value))


class ModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_names_model_stage_and_does_not_send_or_retry(self):
        ollama=Ollama(Settings());ollama.http=Mock()
        context=Mock();context.__aenter__=AsyncMock(side_effect=TimeoutError());context.__aexit__=AsyncMock()
        ollama.http.post=Mock(return_value=context)
        with self.assertRaisesRegex(TimeoutError,'Ollama did not finish within 300'):
            await ollama.reply([{'role':'user','content':'Hello'}])
        ollama.http.post.assert_called_once()
