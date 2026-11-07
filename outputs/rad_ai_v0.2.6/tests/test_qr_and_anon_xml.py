import asyncio
import unittest
from unittest.mock import AsyncMock, Mock
from ayarlar import Settings
from rad.telegram import Telegram
from rad.domain import xml_root, snapshot, nodes


XML='''<hierarchy><node package="io.anonchat" bounds="[0,0][540,960]">
<node package="io.anonchat" class="android.widget.TextView" text="New partner" bounds="[70,25][165,49]"/>
<node package="io.anonchat" class="android.widget.TextView" text="online" bounds="[70,49][108,69]"/>
<node package="io.anonchat" class="android.widget.ScrollView" bounds="[0,72][540,630]">
<node><node package="io.anonchat" content-desc="Hello" bounds="[15,564][192,605]">
<node package="io.anonchat" class="android.widget.TextView" text="Hello" bounds="[27,572][177,596]"/>
</node><node class="android.widget.TextView" text="5:49 AM"/></node>
<node><node package="io.anonchat" content-desc="Hi back" bounds="[340,450][525,490]">
<node package="io.anonchat" class="android.widget.TextView" text="Hi back" bounds="[350,460][510,480]"/>
</node><node class="android.widget.TextView" text="5:48 AM"/></node>
<node package="io.anonchat" content-desc="About partner, Music" bounds="[0,200][540,300]"/>
</node>
<node package="io.anonchat" bounds="[81,642][459,680]">
<node package="io.anonchat" class="android.widget.EditText" text="Write a message..." bounds="[91,649][421,673]"/>
<node package="io.anonchat" clickable="true" bounds="[421,647][449,675]"/>
</node>
<node package="io.anonchat" clickable="true" bounds="[478,639][522,683]"/>
<node package="io.anonchat" content-desc="New partner" clickable="true" bounds="[15,831][525,886]"/>
</node></hierarchy>'''


class StructuralTests(unittest.TestCase):
    def test_messages_exclude_bio_and_timestamps(self):
        root=xml_root(XML)
        selectors={'package':'io.anonchat',**{k:{'rad-role':k} for k in ['identity','incoming','outgoing']}}
        identity,messages=snapshot(root,selectors)
        self.assertEqual(identity,'New partner')
        self.assertEqual(messages,[('assistant','Hi back'),('user','Hello')])

    def test_send_excludes_emoji_and_next_excludes_header(self):
        root=xml_root(XML)
        self.assertEqual(nodes(root,{'rad-role':'send'})[0].get('bounds'),'[478,639][522,683]')
        self.assertEqual(nodes(root,{'rad-role':'next'})[0].get('bounds'),'[15,831][525,886]')


class QRTests(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        adapter=Telegram(Settings(),AsyncMock(),Mock(),AsyncMock(),Mock())
        adapter.client=Mock()
        return adapter

    async def test_qr_waits_and_closes_on_success_without_sms(self):
        adapter=self.adapter()
        qr=Mock(url='tg://login?token=fake',wait=AsyncMock())
        adapter.client.qr_login=AsyncMock(return_value=qr)
        await adapter.qr_auth()
        adapter.client.qr_login.assert_awaited_once()
        self.assertEqual(adapter.emit.call_args.args[0]['type'],'qr_closed')
        adapter.ask.assert_not_called()

    async def test_expired_qr_refreshes(self):
        adapter=self.adapter()
        qr=Mock(url='tg://login?token=fake',wait=AsyncMock(side_effect=[asyncio.TimeoutError(),None]))
        adapter.client.qr_login=AsyncMock(return_value=qr)
        await adapter.qr_auth()
        self.assertEqual(adapter.client.qr_login.call_count,2)

    async def test_qr_cancel_stops_waiter(self):
        adapter=self.adapter()
        qr=Mock(url='tg://login?token=fake',wait=AsyncMock(side_effect=lambda:None))
        async def wait_forever():
            await asyncio.Event().wait()
        qr.wait=wait_forever
        adapter.client.qr_login=AsyncMock(return_value=qr)
        adapter.emit=lambda event:adapter.login_cancel.set() if event['type']=='qr' else None
        with self.assertRaisesRegex(ValueError,'cancelled'):
            await adapter.qr_auth()
