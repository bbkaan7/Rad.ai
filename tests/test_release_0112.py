"""Behavioral coverage for question routing and incoming friendship requests."""
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock
from xml.etree import ElementTree as ET
from ayarlar import Settings
from rad.domain import Message, LayoutError, xml_root
from rad.engine import Engine
from rad.anonchat import AnonChat
from rad.friend_requests import acceptance_control
from rad.intent import is_question, first_question_pair
from test_anon_xml import XML
from test_release_027 import SELECTORS
from test_telegram_adb import S, conversation
from rad.telegram import Telegram
from rad.adb import AndroidBridge


def request_xml(notice='Alex sent you a friend request',button='Accept'):
    root=xml_root('<hierarchy><node package="io.anonchat" class="android.app.Dialog" bounds="[0,0][540,960]"/></hierarchy>')
    pane=root[0]
    ET.SubElement(pane,'node',{'package':'io.anonchat','text':notice})
    control=ET.SubElement(pane,'node',{'package':'io.anonchat','clickable':'true','bounds':'[10,300][100,340]'})
    ET.SubElement(control,'node',{'package':'io.anonchat','text':button})
    return root


class QuestionGrammar(unittest.TestCase):
    def test_informal_and_indirect_questions_without_punctuation(self):
        for text in ['where u from','how old are you','wyd','hbu','can you help me','tell me your name','you got any hobbies','what do you do']:
            with self.subTest(text=text):self.assertTrue(is_question(text))

    def test_statements_are_not_questions(self):
        for text in ['hello','I am fine','I know where you live','what a nice day','yes','I like music']:
            with self.subTest(text=text):self.assertFalse(is_question(text))

    def test_only_adjacent_unanswered_user_questions_form_pair(self):
        first=Message('1','user','where u from'); second=Message('2','user','how old are you')
        self.assertIs(first_question_pair([first,second],{'1':1,'2':2},0),first)
        self.assertIsNone(first_question_pair([first,second],{'1':1,'2':2},1))
        self.assertIsNone(first_question_pair([first,Message('x','assistant','hello'),second],{'1':1,'2':2},0))


class ReplyFlow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.e=Engine(Settings(debounce_seconds=0),lambda event:None)
        self.e.llm.reply=AsyncMock(return_value='A reply')
        self.e.telegram.send=AsyncMock(return_value=None)

    async def asyncTearDown(self):await self.e.close()

    async def test_older_question_receives_reply_and_second_stays_queued(self):
        e=self.e;key='telegram:test'
        await e.ingest(key,'Test',Message('1','user','where u from'),True)
        await e.ingest(key,'Test',Message('2','user','how old are you'),True)
        await e.respond(key,once=True)
        calls=e.telegram.send.await_args_list
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0].kwargs,{'reply_to':'1'})
        self.assertEqual(calls[1].kwargs,{})
        first_context=e.llm.reply.await_args_list[0].args[0]
        self.assertEqual(first_context[-1]['content'],'where u from')
        self.assertNotIn('how old are you',str(first_context))
        self.assertEqual(e.chats[key].handled,2)

    async def test_statement_and_question_do_not_trigger_reply(self):
        await self.e.ingest('telegram:t','T',Message('1','user','Hello'),True)
        await self.e.ingest('telegram:t','T',Message('2','user','where u from'),True)
        await self.e.respond('telegram:t',once=True)
        self.e.telegram.send.assert_awaited_once_with('telegram:t','A reply')

    async def test_questions_in_different_chats_never_form_a_pair(self):
        for key in ['telegram:a','telegram:b']:
            await self.e.ingest(key,'T',Message('1','user','where u from'),True)
            await self.e.respond(key,once=True)
        self.assertTrue(all(not c.kwargs for c in self.e.telegram.send.await_args_list))

    async def test_uncertain_first_reply_does_not_mark_second_question_answered(self):
        e=self.e;key='telegram:t'
        for number,text in enumerate(['where u from','how old are you'],1):
            await e.ingest(key,'T',Message(str(number),'user',text),True)
        e.telegram.send.side_effect=TimeoutError('Verification timed out')
        e.telegram.reconcile=AsyncMock()
        await e.respond(key,once=True)
        await e.reconcile(key)
        self.assertEqual(e.chats[key].handled,1)
        self.assertEqual(e.chats[key].received,2)


class FriendRequestFlow(unittest.IsolatedAsyncioTestCase):
    def adapter(self):
        a=AnonChat(Settings(selectors=SELECTORS),AsyncMock(),Mock(),AsyncMock())
        a.auto_enabled=lambda:True;a.tap=AsyncMock();a.dump=AsyncMock(return_value=request_xml())
        return a

    async def test_dialog_without_chat_header_accepts_clickable_parent_once(self):
        a=self.adapter();root=request_xml()
        await a.process(root);await a.process(root)
        a.tap.assert_awaited_once()
        self.assertEqual(a.tap.await_args.args[0].get('bounds'),'[10,300][100,340]')

    async def test_auto_off_does_not_accept(self):
        a=self.adapter();a.auto_enabled=lambda:False
        await a.process(request_xml())
        a.tap.assert_not_awaited()

    async def test_failed_verification_does_not_repeat_accept_tap(self):
        a=self.adapter();a.dump.side_effect=TimeoutError('XML read failed')
        with self.assertRaises(TimeoutError):await a.process(request_xml())
        await a.process(request_xml())
        a.tap.assert_awaited_once()

    async def test_real_acceptance_promotes_existing_history(self):
        e=Engine(Settings(selectors=SELECTORS),lambda event:None)
        try:
            await e.anon.process(xml_root(XML),allow_actions=False)
            key=e.anon.key;ids=[m.id for m in e.chats[key].messages]
            e.auto=True;e.anon.tap=AsyncMock()
            accepted=xml_root(XML.replace('text="New partner"','text="Alex"').replace('</hierarchy>','<node text="You and your partner became friends"/></hierarchy>'))
            e.anon.dump=AsyncMock(return_value=accepted)
            await e.anon.process(request_xml())
            self.assertEqual(e.anon.key,key)
            self.assertEqual(e.chats[key].category,'Friends')
            self.assertEqual([m.id for m in e.chats[key].messages],ids)
        finally:await e.close()

    def test_outgoing_request_and_unrelated_accept_are_not_incoming(self):
        self.assertIsNone(acceptance_control(request_xml('You have sent a friend request'),SELECTORS))
        self.assertIsNone(acceptance_control(request_xml('Terms and conditions'),SELECTORS))

    def test_request_text_inside_message_is_not_a_control(self):
        root=xml_root(XML.replace('Hello','Accept friend request'))
        self.assertIsNone(acceptance_control(root,SELECTORS))

    def test_ambiguous_requests_are_not_clicked(self):
        root=request_xml()
        ET.SubElement(root[0],'node',{'package':'io.anonchat','text':'Accept','clickable':'true','bounds':'[10,400][100,440]'})
        with self.assertRaises(LayoutError):acceptance_control(root,SELECTORS)


class PhysicalReply(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_long_press_reply_preview_and_send_are_executed(self):
        bridge=AndroidBridge(Settings());bridge.activate=AsyncMock();bridge.shell=AsyncMock()
        t=Telegram(Settings(telegram_selectors=S),AsyncMock(),Mock(),bridge)
        key=await t.process(conversation())
        target=t.messages[key][0][0].id
        menu=xml_root('<hierarchy><node package="org.telegram.messenger" text="Reply" bounds="[10,20][100,60]"/></hierarchy>')
        quoted=conversation()
        ET.SubElement(quoted,'node',{'package':'org.telegram.messenger','content-desc':'Reply to Alice: Hello','bounds':'[10,700][500,780]'})
        typed=conversation(entry='Answer')
        ET.SubElement(typed,'node',{'package':'org.telegram.messenger','content-desc':'Reply to Alice: Hello','bounds':'[10,700][500,780]'})
        t.dump=AsyncMock(side_effect=[conversation(),menu,quoted,typed,conversation(outgoing='Answer')])
        await t.send(key,'Answer',reply_to=target)
        commands=[call.args[0] for call in bridge.shell.await_args_list]
        self.assertTrue(commands[0].startswith('input swipe '))
        self.assertEqual(commands[1],'input tap 55 40')
        self.assertIn('input text Answer',commands)
        self.assertEqual(commands[-1],'input tap 497 830')

    async def test_missing_quote_prevents_telegram_text_and_send(self):
        bridge=AndroidBridge(Settings());bridge.activate=AsyncMock();bridge.shell=AsyncMock()
        t=Telegram(Settings(telegram_selectors=S),AsyncMock(),Mock(),bridge)
        key=await t.process(conversation())
        target=t.messages[key][0][0].id
        menu=xml_root('<hierarchy><node package="org.telegram.messenger" text="Reply" bounds="[10,20][100,60]"/></hierarchy>')
        t.dump=AsyncMock(side_effect=[conversation(),menu,conversation()])
        with self.assertRaisesRegex(ValueError,'preview'):await t.send(key,'Answer',reply_to=target)
        self.assertEqual(bridge.shell.await_count,2)

    async def test_anon_long_press_reply_preview_and_send_are_executed(self):
        selectors={**SELECTORS,'input_placeholder':'Write a message...'}
        a=AnonChat(Settings(selectors=selectors),AsyncMock(),Mock(),AsyncMock())
        a.shell=AsyncMock()
        await a.process(xml_root(XML))
        target=next(m.id for m in a.visible_messages if m.role=='user')
        menu=xml_root('<hierarchy><node package="io.anonchat" text="Reply" bounds="[10,20][100,60]"/></hierarchy>')
        quoted=xml_root(XML)
        ET.SubElement(quoted,'node',{'package':'io.anonchat','content-desc':'Hello','bounds':'[10,690][500,720]'})
        after=xml_root(XML)
        pane=next(n for n in after.iter('node') if n.get('class')=='android.widget.ScrollView')
        group=ET.SubElement(pane,'node')
        bubble=ET.SubElement(group,'node',{'package':'io.anonchat','content-desc':'Answer','bounds':'[350,610][530,629]'})
        ET.SubElement(bubble,'node',{'package':'io.anonchat','class':'android.widget.TextView','text':'Answer','bounds':'[360,612][520,627]'})
        typed=xml_root(XML.replace('text="Write a message..."','text="Answer"'))
        ET.SubElement(typed,'node',{'package':'io.anonchat','content-desc':'Hello','bounds':'[10,690][500,720]'})
        a.dump=AsyncMock(side_effect=[xml_root(XML),menu,quoted,typed,after])
        await a.send(a.key,'Answer',reply_to=target)
        commands=[call.args[0] for call in a.shell.await_args_list]
        self.assertTrue(commands[0].startswith('input swipe '))
        self.assertEqual(commands[1],'input tap 55 40')
        self.assertEqual(commands[-1],'input tap 500 661')

    def test_original_bubble_is_not_mistaken_for_reply_preview(self):
        a=AnonChat(Settings(selectors=SELECTORS),AsyncMock(),Mock(),AsyncMock())
        with self.assertRaisesRegex(ValueError,'preview'):a.verify_reply_preview(xml_root(XML),'Hello')
