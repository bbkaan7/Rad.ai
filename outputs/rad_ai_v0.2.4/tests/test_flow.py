import unittest
from unittest.mock import Mock, patch
import numpy as np

from assistant.core import Conversation, Observation
from assistant.flow import prepare_current, deliver_parts, reply_parts
from assistant.model import Ollama
from assistant.desktop import Desktop


class FlowTests(unittest.TestCase):
    def test_arrival_during_generation_regenerates_complete_group(self):
        session = Conversation('telegram','a')
        initial = Observation('a','Hello')
        fresh = Observation('a','Hello [NEXT_INCOMING] How are you?')
        model = Mock(side_effect=['Old reply','Complete reply'])
        result = prepare_current(session,initial,model,Mock(side_effect=[fresh,fresh]),lambda:None)
        self.assertEqual(result,(fresh,'Complete reply'))
        self.assertIn('Hello [NEXT_INCOMING] How are you?',model.call_args.args[0][-1]['content'])
        self.assertEqual(session.history,[])
        self.assertEqual(session.pending,fresh)

    def test_changed_recipient_never_refreshes_into_another_chat(self):
        session=Conversation('telegram','a')
        with self.assertRaisesRegex(ValueError,'Conversation changed'):
            prepare_current(session,Observation('a','Hello'),lambda _: 'Hi',
                            lambda:Observation('b','Hello'),lambda:None)

    def test_multiple_messages_commit_only_verified_parts(self):
        session=Conversation('telegram','a')
        observed=Observation('a','Two questions')
        session.prepare(observed,lambda _: 'First [NEXT_MESSAGE] Second')
        driver=Mock()
        driver.observe.return_value=Observation('a','')
        driver.send.side_effect=[True,False]
        deliver_parts(session,driver,observed,session.draft)
        self.assertTrue(session.uncertain)
        self.assertEqual(session.draft,'Second')
        self.assertEqual([m['content'] for m in session.history],['Two questions','First'])

    def test_new_arrival_between_parts_cancels_unsent_remainder(self):
        session=Conversation('telegram','a')
        observed=Observation('a','Question')
        session.prepare(observed,lambda _: 'First [NEXT_MESSAGE] Second')
        driver=Mock()
        driver.observe.return_value=Observation('a','New question')
        driver.send.return_value=True
        deliver_parts(session,driver,observed,session.draft)
        self.assertEqual(driver.send.call_count,1)
        self.assertFalse(session.uncertain)

    def test_planner_and_writer_are_separate_calls(self):
        model=Ollama({})
        model.request=Mock(side_effect=['{"mode":"separate","count":2}',
                                       '{"messages":["Hello!","How are you?"]}'])
        self.assertEqual(model([{'role':'user','content':'Hi'}]),'Hello! [NEXT_MESSAGE] How are you?')
        self.assertEqual(model.request.call_count,2)

    def test_invalid_plan_stops_before_writer(self):
        model=Ollama({})
        model.request=Mock(return_value='{"mode":"separate","count":99}')
        with self.assertRaises(ValueError):
            model([])
        self.assertEqual(model.request.call_count,1)

    def test_invalid_split_rejected(self):
        with self.assertRaises(ValueError):
            reply_parts('Hello [NEXT_MESSAGE] ')

    def test_group_reads_each_incoming_bubble_and_caches_unchanged_text(self):
        driver=object.__new__(Desktop)
        driver.profile={'incoming_color':[1,2,3], 'outgoing_color':[4,5,6]}
        driver.message_region=Mock(return_value=[0,0,200,200])
        driver.ocr=Mock(side_effect=['First','Second'])
        frame=np.zeros((200,200,3),dtype=np.uint8)
        frame[80:100,0:80]=30
        frame[120:140,0:80]=60
        def boxes(pane,color,*args):
            return [(0,10,80,20),(0,80,80,20),(0,120,80,20)] if color==[1,2,3] else [(100,40,80,20)]
        with patch('assistant.desktop.bubble_rectangles',side_effect=boxes):
            self.assertEqual(driver.incoming_group(frame),'First [NEXT_INCOMING] Second')
            self.assertEqual(driver.incoming_group(frame),'First [NEXT_INCOMING] Second')
        self.assertEqual(driver.ocr.call_count,2)


if __name__=='__main__':
    unittest.main()
