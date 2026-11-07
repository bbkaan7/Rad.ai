import asyncio
import unittest
import uuid
from unittest.mock import AsyncMock
from ayarlar import Settings
from rad.adb import AndroidBridge, AndroidAttention
from rad.domain import LayoutError
from rad.device_lease import DeviceLease


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    def bridge(self):
        b=AndroidBridge(Settings())
        self.now=100.0
        b._clock=lambda:self.now
        b.activate=AsyncMock()
        b.watch('io.anonchat')
        b.watch('org.vidogram.messenger')
        return b

    async def test_second_poller_cannot_steal_focus_each_second(self):
        b=self.bridge()
        async with b.poll_session('io.anonchat') as allowed:self.assertTrue(allowed)
        for _ in range(5):
            self.now+=1
            async with b.poll_session('org.vidogram.messenger') as allowed:self.assertFalse(allowed)
        self.assertEqual(b.activate.await_count,1)
        self.now+=7
        async with b.poll_session('org.vidogram.messenger') as allowed:self.assertTrue(allowed)
        self.now+=12
        async with b.poll_session('io.anonchat') as allowed:self.assertTrue(allowed)

    async def test_failing_app_backs_off_without_starving_other_app(self):
        b=self.bridge()
        with self.assertRaises(LayoutError):
            async with b.poll_session('io.anonchat') as allowed:
                self.assertTrue(allowed)
                raise LayoutError('not ready')
        self.assertEqual(b.retry_after['io.anonchat'],105)
        async with b.poll_session('org.vidogram.messenger') as allowed:self.assertTrue(allowed)
        async with b.poll_session('io.anonchat') as allowed:self.assertFalse(allowed)
        b.poll_failure('io.anonchat',LayoutError())
        self.assertEqual(b.retry_after['io.anonchat'],110)

    async def test_permission_prompt_pauses_both_pollers(self):
        b=self.bridge()
        with self.assertRaises(AndroidAttention):
            async with b.poll_session('io.anonchat'):
                raise AndroidAttention('permission')
        async with b.poll_session('org.vidogram.messenger') as allowed:self.assertFalse(allowed)

    async def test_unwatch_removes_dead_owner(self):
        b=self.bridge()
        self.assertTrue(b.poll_allowed('io.anonchat'))
        b.unwatch('io.anonchat')
        self.assertTrue(b.poll_allowed('org.vidogram.messenger'))

    async def test_single_connected_app_never_rotates_away(self):
        b=self.bridge()
        b.unwatch('org.vidogram.messenger')
        for _ in range(4):
            self.now+=100
            self.assertTrue(b.poll_allowed('io.anonchat'))


class ActivationTests(unittest.IsolatedAsyncioTestCase):
    async def test_manually_opened_app_is_not_relaunched(self):
        b=AndroidBridge(Settings())
        b.foreground=AsyncMock(return_value='io.anonchat')
        b.shell=AsyncMock()
        await b.activate('io.anonchat')
        b.shell.assert_not_called()

    async def test_stale_cache_does_not_hide_external_foreground_change(self):
        b=AndroidBridge(Settings(adb_switch_seconds=0,adb_activities={'io.anonchat':'.MainActivity'}))
        b.active_package='io.anonchat'
        b.foreground=AsyncMock(side_effect=['org.vidogram.messenger','io.anonchat'])
        b.shell=AsyncMock(return_value='Status: ok')
        await b.activate('io.anonchat')
        command=b.shell.call_args.args[0]
        self.assertIn('--activity-reorder-to-front --activity-single-top',command)
        self.assertIn('-a android.intent.action.MAIN',command)

    async def test_permission_window_cannot_be_covered(self):
        b=AndroidBridge(Settings())
        b.foreground=AsyncMock(return_value='com.android.permissioncontroller')
        b.shell=AsyncMock()
        with self.assertRaises(AndroidAttention):await b.activate('io.anonchat')
        b.shell.assert_not_called()

    async def test_failed_launch_is_not_immediately_repeated(self):
        b=AndroidBridge(Settings())
        b.foreground=AsyncMock(return_value='com.uncube.launcher3')
        b.shell=AsyncMock(return_value='Error: not available')
        with self.assertRaises(LayoutError):await b.activate('io.anonchat')
        with self.assertRaisesRegex(LayoutError,'cooldown'):await b.activate('io.anonchat')
        self.assertEqual(b.shell.await_count,1)

    async def test_timeout_bounds_the_android_dump_process(self):
        b=AndroidBridge(Settings())
        b.shell=AsyncMock(return_value='<hierarchy><node package="io.anonchat"/></hierarchy>')
        await b.dump('io.anonchat')
        self.assertIn('toybox timeout -k 1 8 uiautomator dump',b.shell.call_args.args[0])


class LeaseTests(unittest.TestCase):
    def test_second_controller_is_rejected_until_first_releases(self):
        identity=uuid.uuid4().hex
        a,b=DeviceLease(identity),DeviceLease(identity)
        try:
            a.acquire()
            with self.assertRaisesRegex(ValueError,'Another Rad.ai'):b.acquire()
            a.close()
            b.acquire()
        finally:
            a.close();b.close()
            a.path.unlink(missing_ok=True)
import xml.etree.ElementTree as ET
from unittest.mock import Mock
from rad.telegram import Telegram
from rad.telegram_xml import local_search_candidates
from rad.domain import Message
from test_telegram_adb import S, conversation


def search_fixture(names=('Alice',),global_only=False):
    r=ET.Element('hierarchy')
    def n(text,cls,bounds,**extras):
        return ET.SubElement(r,'node',{'package':'org.telegram.messenger','text':text,'class':cls,'bounds':bounds,**extras})
    n('Alice','android.widget.EditText','[10,20][400,70]',**{'content-desc':'Search Chats','focused':'true'})
    n('Recent','android.widget.TextView','[10,80][400,110]')
    if global_only:n('Global search','android.widget.TextView','[10,110][400,130]')
    for i,name in enumerate(names):n(name+', last seen recently','android.view.ViewGroup',f'[0,{140+i*70}][500,{200+i*70}]')
    if not global_only:n('Global search','android.widget.TextView','[10,400][400,430]')
    return r


class ChatRoutingTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        b=AndroidBridge(Settings())
        b.activate=AsyncMock()
        b.shell=AsyncMock(return_value='')
        return Telegram(Settings(telegram_selectors=S),AsyncMock(),Mock(),b)

    async def test_global_search_results_cannot_be_selected(self):
        self.assertEqual(local_search_candidates(search_fixture(global_only=True),'Alice','org.telegram.messenger'),[])

    async def test_unique_local_result_opens_and_checks_header(self):
        t=self.adapter();s=search_fixture()
        t.dump=AsyncMock(side_effect=[s,s,conversation('Alice')])
        r=await t.search_local(s,'Alice')
        self.assertEqual(t.identity(r),'Alice')
        self.assertEqual(t.bridge.shell.await_count,2)
        self.assertTrue(all(c.args[0].startswith('input tap ') for c in t.bridge.shell.call_args_list))

    async def test_duplicate_local_names_are_rejected_before_opening(self):
        t=self.adapter();s=search_fixture(('Alice','Alice'))
        t.dump=AsyncMock(return_value=s)
        with self.assertRaisesRegex(ValueError,'Multiple local chats'):
            await t.search_local(s,'Alice')
        self.assertEqual(t.bridge.shell.await_count,1)

    async def test_opened_wrong_header_is_rejected(self):
        t=self.adapter();s=search_fixture()
        t.dump=AsyncMock(side_effect=[s,s,conversation('Bob')])
        with self.assertRaisesRegex(ValueError,'different conversation'):
            await t.search_local(s,'Alice')

    async def test_two_conversations_have_separate_histories(self):
        t=self.adapter()
        a=await t.process(conversation('Alice',incoming='A-only'))
        b=await t.process(conversation('Bob',incoming='B-only'))
        self.assertNotEqual(a,b)
        self.assertEqual(t.histories[a][0][1],'A-only')
        self.assertEqual(t.histories[b][0][1],'B-only')

    async def test_owner_draft_blocks_conversation_switch(self):
        t=self.adapter()
        with self.assertRaisesRegex(ValueError,'unsent draft'):
            await t.search_local(conversation('Bob',entry='Owner draft'),'Alice')
        t.bridge.shell.assert_not_called()


class BackgroundTests(unittest.IsolatedAsyncioTestCase):
    async def test_stopped_app_is_backgrounded(self):
        b=AndroidBridge(Settings())
        b.device=object()
        b.foreground=AsyncMock(return_value='org.vidogram.messenger')
        b.shell=AsyncMock()
        self.assertTrue(await b.background('org.vidogram.messenger'))
        b.shell.assert_awaited_once_with('input keyevent KEYCODE_HOME')

    async def test_does_not_dismiss_other_app_or_permission_prompt(self):
        b=AndroidBridge(Settings())
        b.device=object()
        b.foreground=AsyncMock(return_value='com.android.permissioncontroller')
        b.shell=AsyncMock()
        self.assertFalse(await b.background('org.vidogram.messenger'))
        b.shell.assert_not_awaited()
