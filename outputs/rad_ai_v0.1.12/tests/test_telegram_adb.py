import asyncio
import threading
import unittest
from unittest.mock import AsyncMock, Mock
from ayarlar import Settings, load
from rad.adb import AndroidBridge
from rad.telegram import Telegram
from rad.domain import xml_root, Message, LayoutError, nodes
from rad.telegram_xml import records, login_screen

S={"package":"org.telegram.messenger",**{k:{"tg-role":k} for k in ('chat_list','chat_rows','identity','input','send','incoming','outgoing','back','reply','delete','quote')},"input_placeholder":"Message"}

def conversation(title='Alice',incoming='Hello',outgoing='',entry='Message'):
    import xml.etree.ElementTree as ET
    root=ET.Element('hierarchy')
    app=ET.SubElement(root,'node',{'package':'org.telegram.messenger','bounds':'[0,0][540,960]'})
    def node(**attrs):
        return ET.SubElement(app,'node',{'package':'org.telegram.messenger',**{k.replace('_','-'):v for k,v in attrs.items()}})
    node(**{'class':'android.widget.TextView'},text=title,bounds='[60,24][300,60]')
    node(content_desc='Go back',bounds='[0,24][50,65]')
    node(**{'class':'android.widget.EditText'},text=entry,bounds='[30,800][450,860]')
    node(content_desc='Send',bounds='[460,800][535,860]')
    if incoming:
        node(**{'class':'android.view.View'},text=incoming+'\nReceived today at 12:00',bounds='[0,120][540,180]')
    if outgoing:
        node(**{'class':'android.view.View'},text=outgoing+'\nSent today at 12:01, Read',bounds='[0,200][540,260]')
    return root


def dialogs(names=('Alice','Bob')):
    import xml.etree.ElementTree as ET
    root=ET.Element('hierarchy')
    pane=ET.SubElement(root,'node',{'package':'org.telegram.messenger','scrollable':'true','bounds':'[0,70][540,960]'})
    for i,name in enumerate(names):
        ET.SubElement(pane,'node',{'package':'org.telegram.messenger','clickable':'true','content-desc':name+'. Received today at 12:00. Hello','bounds':f'[0,{80+i*100}][540,{160+i*100}]'})
    return root


class XMLTests(unittest.TestCase):
    def test_accessibility_direction_not_bubble_position(self):
        data=records(conversation(outgoing='Reply'),S)
        self.assertEqual([(r[2],r[3]) for r in data],[('user','Hello'),('assistant','Reply')])

    def test_last_direction_suffix_wins_over_text(self):
        data=records(conversation(incoming='Example\nSent yesterday at 10:00'),S)
        self.assertEqual(data[0][2],'user')
        self.assertIn('Sent yesterday',data[0][3])

    def test_signin_screen_is_not_a_chat(self):
        self.assertTrue(login_screen(xml_root('<hierarchy><node text="Start Messaging"/></hierarchy>')))

    def test_chat_list_and_composer_selectors_are_distinct(self):
        root=dialogs()
        self.assertEqual(len(nodes(root,S['chat_rows'])),2)
        self.assertEqual(len(nodes(root,S['chat_list'])),1)
        self.assertEqual(nodes(root,S['input']),[])


class TelegramADBTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        bridge=AndroidBridge(Settings())
        bridge.activate=AsyncMock()
        bridge.shell=AsyncMock(return_value='')
        t=Telegram(Settings(telegram_selectors=S,adb_poll_seconds=.25),AsyncMock(),Mock(),bridge)
        return t

    async def test_history_is_not_auto_answered_but_next_message_is(self):
        t=self.adapter()
        root=conversation()
        key=await t.process(root)
        self.assertFalse(any(c.args[3] for c in t.ingest.call_args_list))
        import xml.etree.ElementTree as ET
        ET.SubElement(root,'node',{'package':'org.telegram.messenger','text':'Second\nReceived today at 12:02','bounds':'[0,300][540,360]'})
        await t.process(root)
        notified=[c.args[2].text for c in t.ingest.call_args_list if c.args[3]]
        self.assertEqual(notified,['Second'])
        self.assertEqual(len(t.histories[key]),2)

    async def test_send_verifies_text_and_outgoing_xml(self):
        t=self.adapter()
        key=await t.process(conversation())
        t.dump=AsyncMock(side_effect=[conversation(),conversation(entry='Reply'),conversation(outgoing='Reply')])
        await t.send(key,'Reply')
        self.assertFalse(t.blocked)
        commands=[c.args[0] for c in t.bridge.shell.call_args_list]
        self.assertEqual(commands,['input tap 240 830','input text Reply','input tap 497 830'])
        self.assertTrue(any(c.args[2] and c.args[2].text=='Reply' for c in t.ingest.call_args_list))

    async def test_failed_typed_verification_never_taps_send(self):
        t=self.adapter()
        key=await t.process(conversation())
        t.dump=AsyncMock(side_effect=[conversation(),conversation(title='Bob',entry='Reply')])
        with self.assertRaisesRegex(ValueError,'recipient changed'):
            await t.send(key,'Reply')
        self.assertTrue(t.blocked)
        self.assertEqual(t.bridge.shell.await_count,2)

    async def test_duplicate_display_names_are_not_selected(self):
        t=self.adapter()
        self.assertEqual(t.rows(dialogs(('Alice','Alice'))),[])

    async def test_round_robin_yields_after_one_chat(self):
        t=self.adapter()
        t.dump=AsyncMock(side_effect=[dialogs(),conversation('Alice'),dialogs(),dialogs(),conversation('Bob'),dialogs()])
        await t.poll_once()
        await t.poll_once()
        self.assertIn(t.key_for('Alice'),t.histories)
        self.assertIn(t.key_for('Bob'),t.histories)
        self.assertEqual(t.cursor,2)

    async def test_unicode_rejected_before_device_access(self):
        t=self.adapter()
        with self.assertRaises(ValueError):
            await t.send('telegram:unknown','hello \U0001f600')
        t.bridge.activate.assert_not_called()
        t.bridge.shell.assert_not_called()

    async def test_existing_draft_is_not_overwritten(self):
        t=self.adapter()
        key=await t.process(conversation())
        t.dump=AsyncMock(return_value=conversation(entry='Owner draft'))
        with self.assertRaisesRegex(ValueError,'not empty'):
            await t.send(key,'Reply')
        t.bridge.shell.assert_not_called()


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_sessions_serialize_switch_and_entire_transaction(self):
        b=AndroidBridge(Settings())
        events=[]
        async def activate(package): events.append('open '+package)
        b.activate=activate
        started=asyncio.Event()
        finish=asyncio.Event()
        async def first():
            async with b.session('io.anonchat'):
                events.append('typing')
                started.set()
                await finish.wait()
                events.append('send')
        async def second():
            async with b.session('org.telegram.messenger'):
                events.append('read')
        a=asyncio.create_task(first())
        await started.wait()
        c=asyncio.create_task(second())
        await asyncio.sleep(0)
        self.assertEqual(events,['open io.anonchat','typing'])
        finish.set()
        await asyncio.gather(a,c)
        self.assertEqual(events,['open io.anonchat','typing','send','open org.telegram.messenger','read'])

    async def test_cancel_does_not_release_lock_until_shell_thread_finishes(self):
        b=AndroidBridge(Settings())
        b.activate=AsyncMock()
        started=threading.Event()
        finish=threading.Event()
        entered=asyncio.Event()
        def shell():
            started.set()
            finish.wait(2)
        async def first():
            async with b.session('io.anonchat'):
                await b.blocking(shell)
        async def second():
            async with b.session('org.telegram.messenger'):
                entered.set()
        task=asyncio.create_task(first())
        await asyncio.to_thread(started.wait,1)
        task.cancel()
        other=asyncio.create_task(second())
        await asyncio.sleep(.02)
        self.assertFalse(entered.is_set())
        finish.set()
        await asyncio.gather(task,other,return_exceptions=True)
        self.assertTrue(entered.is_set())

    async def test_foreground_mismatch_invalidates_cached_package(self):
        b=AndroidBridge(Settings())
        b.active_package='org.telegram.messenger'
        b.shell=AsyncMock(return_value='<hierarchy><node package="other.app"/></hierarchy>')
        with self.assertRaises(LayoutError):
            await b.dump('org.telegram.messenger')
        self.assertIsNone(b.active_package)

    async def test_package_cannot_inject_shell_syntax(self):
        b=AndroidBridge(Settings())
        b.shell=AsyncMock()
        with self.assertRaises(ValueError):
            await b.activate('org.telegram.messenger; touch x')
        b.shell.assert_not_called()

class VidogramTests(unittest.IsolatedAsyncioTestCase):
    def configured(self):
        import copy
        selectors=copy.deepcopy(S)
        selectors['package']='org.vidogram.messenger'
        selectors['scan_chat_list']=False
        for value in selectors.values():
            if isinstance(value,dict): value['package']='org.vidogram.messenger'
        bridge=AndroidBridge(Settings())
        bridge.activate=AsyncMock()
        bridge.shell=AsyncMock()
        t=Telegram(Settings(telegram_selectors=selectors),AsyncMock(),Mock(),bridge)
        root=conversation()
        for node in root.iter('node'): node.set('package','org.vidogram.messenger')
        return t,root

    async def test_vidogram_reads_current_chat_without_returning_to_opaque_list(self):
        t,root=self.configured()
        t.dump=AsyncMock(return_value=root)
        await t.poll_once()
        self.assertIn(t.key_for('Alice'),t.histories)
        t.bridge.shell.assert_not_called()
        t.dump.assert_awaited_once()

    async def test_search_field_is_not_message_input(self):
        t,root=self.configured()
        entry=nodes(root,t.selectors['input'])[0]
        entry.set('content-desc','Search Chats')
        self.assertEqual(nodes(root,t.selectors['input']),[])
        self.assertEqual(nodes(root,t.selectors['identity']),[])

    async def test_send_hit_target_excludes_overlapping_editor(self):
        t,root=self.configured()
        nodes(root,t.selectors['input'])[0].set('bounds','[57,909][487,949]')
        nodes(root,t.selectors['send'])[0].set('bounds','[433,907][533,951]')
        await t.tap_send(root)
        t.bridge.shell.assert_awaited_once_with('input tap 510 929')

    async def test_explicit_launcher_alias_is_used(self):
        b=AndroidBridge(Settings(adb_activities={'org.vidogram.messenger':'org.telegram.messenger.DefaultIcon'},adb_switch_seconds=0))
        b.shell=AsyncMock(return_value='Status: ok')
        b.foreground=AsyncMock(side_effect=['io.anonchat','org.vidogram.messenger'])
        await b.activate('org.vidogram.messenger')
        b.shell.assert_awaited_once_with('am start -W --activity-reorder-to-front --activity-single-top -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -n org.vidogram.messenger/org.telegram.messenger.DefaultIcon')

    async def test_activity_shell_injection_rejected(self):
        b=AndroidBridge(Settings(adb_activities={'org.vidogram.messenger':'bad;command'}))
        b.shell=AsyncMock()
        with self.assertRaises(ValueError):await b.activate('org.vidogram.messenger')
        b.shell.assert_not_called()
    async def test_transient_xml_failure_retries_only_read(self):
        b=AndroidBridge(Settings())
        b.shell=AsyncMock(side_effect=['ERROR: could not get idle state','<hierarchy><node package="org.vidogram.messenger"/></hierarchy>'])
        root=await b.dump('org.vidogram.messenger')
        self.assertEqual(root.tag,'hierarchy')
        self.assertEqual(b.shell.await_count,2)
