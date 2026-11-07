import asyncio
from contextlib import asynccontextmanager
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock
import xml.etree.ElementTree as ET

from ayarlar import Settings
from rad.domain import Chat, Message, LayoutError, center, input_command, tail_delta, snapshot, xml_root
from rad.engine import Engine
from rad.anonchat import AnonChat


class DomainTests(TestCase):
    def test_context_exactly_last_five_and_isolated(self):
        a,b=Chat('a','A'),Chat('b','B')
        for i in range(8):
            a.append(Message(str(i),'user' if i%2==0 else 'assistant',str(i)))
        self.assertEqual([m['content'] for m in a.context()],['3','4','5','6','7'])
        self.assertEqual(b.context(),[])
        self.assertFalse(a.append(Message('7','assistant','duplicate')))

    def test_bounds_are_from_xml(self):
        self.assertEqual(center(ET.fromstring('<node bounds="[10,20][50,80]"/>')),(30,50))
        with self.assertRaises(LayoutError):
            center(ET.fromstring('<node bounds="[50,80][10,20]"/>'))

    def test_shell_text_is_quoted_and_unicode_fails_before_typing(self):
        self.assertEqual(input_command('hi; $(touch x)'),"input text 'hi;%s$(touch%sx)'")
        for text in ('hello 😃','line\nbreak','%s'):
            with self.assertRaises(ValueError):
                input_command(text)

    def test_ordered_overlap_preserves_duplicate_occurrences(self):
        self.assertEqual(tail_delta(['a','b'],['b','b','c']),['b','c'])
        self.assertEqual(tail_delta(['a','b'],['a','b']),[])
        with self.assertRaises(LayoutError):
            tail_delta(['a'],['z'])

    def test_invalid_xml_is_not_read_as_chat(self):
        with self.assertRaises(LayoutError):
            xml_root('ERROR: could not get idle state')


class Adapter:
    def __init__(self):
        self.sent=[]
        self.after_send=None
    @asynccontextmanager
    async def typing(self,key):
        yield
    async def send(self,key,text):
        self.sent.append(text)
        if self.after_send:
            await self.after_send()
            self.after_send=None
        return Message('out'+str(len(self.sent)),'assistant',text)
    async def close(self):
        pass


class AsyncTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.events=[]
        self.engine=Engine(Settings(debounce_seconds=0),self.events.append,AsyncMock())
        self.adapter=Adapter()
        self.engine.telegram=self.adapter
        self.engine.llm=Mock(reply=AsyncMock(return_value='Reply'),close=AsyncMock())
        await self.engine.set_auto(True)

    async def asyncTearDown(self):
        await self.engine.close()

    async def settle(self):
        for _ in range(100):
            await asyncio.sleep(0)
            if all(t.done() for t in self.engine.jobs.values()):
                return
        self.fail('reply worker did not settle')

    async def test_second_message_during_generation_waits_for_next_batch(self):
        async def model(context):
            if len(context)==1:
                await self.engine.ingest('telegram:1','A',Message('2','user','Second'),True)
                return 'First answer'
            return 'both answered'
        self.engine.llm.reply.side_effect=model
        await self.engine.ingest('telegram:1','A',Message('1','user','First'),True)
        await self.settle()
        self.assertEqual(self.adapter.sent,['First answer','both answered'])
        self.assertEqual([m['content'] for m in self.engine.llm.reply.call_args.args[0]],['First','Second','First answer'])

    async def test_arrival_during_send_is_not_lost(self):
        async def during_send():
            await self.engine.ingest('telegram:1','A',Message('2','user','Second'),True)
        self.adapter.after_send=during_send
        await self.engine.ingest('telegram:1','A',Message('1','user','First'),True)
        await self.settle()
        self.assertEqual(len(self.adapter.sent),2)
        self.assertEqual(self.engine.chats['telegram:1'].handled,2)

    async def test_auto_off_while_llm_running_suppresses_send(self):
        async def model(context):
            await self.engine.set_auto(False)
            return 'late'
        self.engine.llm.reply.side_effect=model
        await self.engine.ingest('telegram:1','A',Message('1','user','First'),True)
        await self.settle()
        self.assertEqual(self.adapter.sent,[])

    async def test_manual_takeover_invalidates_generation(self):
        async def model(context):
            await self.engine.manual('telegram:1','Owner reply')
            return 'bot reply'
        self.engine.llm.reply.side_effect=model
        await self.engine.ingest('telegram:1','A',Message('1','user','First'),True)
        await self.settle()
        self.assertEqual(self.adapter.sent,['Owner reply'])
        self.assertTrue(self.engine.chats['telegram:1'].paused)

    async def test_uncertain_send_is_not_retried(self):
        self.adapter.send=AsyncMock(side_effect=TimeoutError('unknown outcome'))
        await self.engine.ingest('telegram:1','A',Message('1','user','First'),True)
        await self.settle()
        self.assertTrue(self.engine.chats['telegram:1'].uncertain)
        self.assertEqual(self.adapter.send.call_count,1)

    async def test_history_load_never_autoreplies(self):
        await self.engine.ingest('telegram:1','A',Message('1','user','Old'),False)
        await self.settle()
        self.assertEqual(self.adapter.sent,[])

    async def test_duplicate_event_does_not_generate_twice(self):
        message=Message('1','user','Hi')
        await self.engine.ingest('telegram:1','A',message,True)
        await self.settle()
        await self.engine.ingest('telegram:1','A',message,True)
        await self.settle()
        self.assertEqual(len(self.adapter.sent),1)


class ADBTests(IsolatedAsyncioTestCase):
    def fixture(self,input_text='',outgoing='',identity='Alice'):
        root=ET.Element('hierarchy')
        for resource,text,bounds in [('chat',identity,'[0,0][100,20]'),
                ('input',input_text,'[0,200][100,240]'),('send','','[100,200][140,240]')]:
            ET.SubElement(root,'node',{'package':'app.test','resource-id':resource,'text':text,'bounds':bounds})
        if outgoing:
            ET.SubElement(root,'node',{'package':'app.test','resource-id':'out','text':outgoing,'bounds':'[100,100][200,130]'})
        return root

    def configured(self):
        selectors={'package':'app.test',**{key:{'resource-id':value} for key,value in
            [('identity','chat'),('incoming','in'),('outgoing','out'),('input','input'),('send','send')]}}
        adapter=AnonChat(Settings(selectors=selectors),AsyncMock(),Mock(),AsyncMock())
        adapter.identity,adapter.key='Alice','anonchat:test'
        adapter.shell=AsyncMock(return_value='')
        return adapter

    async def test_send_verifies_typed_text_and_outgoing_occurrence(self):
        adapter=self.configured()
        adapter.dump=AsyncMock(side_effect=[self.fixture(),self.fixture('hi'),self.fixture(outgoing='hi')])
        await adapter.send('anonchat:test','hi')
        commands=[call.args[0] for call in adapter.shell.call_args_list]
        self.assertEqual(commands,['input tap 50 220','input text hi','input tap 120 220'])
        self.assertFalse(adapter.blocked)
        self.assertTrue(any(call.args[2] and call.args[2].text=='hi' for call in adapter.ingest.call_args_list))

    async def test_changed_chat_blocks_before_typing(self):
        adapter=self.configured()
        adapter.dump=AsyncMock(return_value=self.fixture(identity='Bob'))
        with self.assertRaisesRegex(ValueError,'changed'):
            await adapter.send('anonchat:test','hi')
        adapter.shell.assert_not_called()

    async def test_wrong_typed_text_blocks_send_button(self):
        adapter=self.configured()
        adapter.dump=AsyncMock(side_effect=[self.fixture(),self.fixture('wrong')])
        with self.assertRaisesRegex(ValueError,'Typed text'):
            await adapter.send('anonchat:test','hi')
        self.assertTrue(adapter.blocked)
        self.assertEqual(adapter.shell.call_count,2)

    async def test_missing_selectors_fails_before_connect(self):
        adapter=AnonChat(Settings(),AsyncMock(),Mock(),AsyncMock())
        with self.assertRaisesRegex(ValueError,'selectors'):
            await adapter.connect()

    async def test_unsupported_input_does_not_touch_device(self):
        adapter=AnonChat(Settings(),AsyncMock(),Mock(),AsyncMock())
        adapter.shell=AsyncMock()
        with self.assertRaises(ValueError):
            await adapter.send('a','😃')
        adapter.shell.assert_not_called()
