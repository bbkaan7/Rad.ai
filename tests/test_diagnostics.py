"""Injected failures prove log fidelity, privacy, bounded growth and resilience."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from rad import diagnostics as d


class LogTests(unittest.TestCase):
    def setUp(self):
        self.previous=d.LOG_PATH
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'rad_error.log'
        d.configure(self.path)

    def tearDown(self):
        d.configure(self.previous)
        self.temp.cleanup()

    def entries(self):
        return [json.loads(line.split(' ',1)[1]) for line in self.path.read_text(encoding='utf-8').splitlines()]

    def test_chained_exception_has_original_line_variables_and_safe_message(self):
        def failure():
            phase='verify_outgoing';attempt=3;password='private-password';text='private-message'
            try:raise ValueError('Bad XML token=abc123 '+password+' '+text)
            except ValueError as error:raise RuntimeError('Could not verify send') from error
        try:failure()
        except Exception as error:d.record('anonchat.send',error,key='anonchat:private',phase='verify_outgoing')
        row=self.entries()[0]
        self.assertEqual(row['stage'],'anonchat.send')
        self.assertEqual(row['chain'][0]['message'],'Could not verify send')
        self.assertEqual([c['type'] for c in row['chain']],['RuntimeError','ValueError'])
        frames=[f for f in row['frames'] if f['function']=='failure']
        self.assertTrue(all(f['line']>0 for f in frames))
        self.assertTrue(any(f['variables']['attempt']==3 for f in frames))
        self.assertEqual(frames[0]['variables']['phase'],'verify_outgoing')
        raw=self.path.read_text(encoding='utf-8')
        for secret in ['private-password','private-message','abc123','anonchat:private']:
            self.assertNotIn(secret,raw)

    def test_nested_operations_share_correlation_and_keep_error(self):
        @d.logged('inner')
        async def inner():raise ValueError('Target was not visible')
        @d.logged('outer')
        async def outer():await inner()
        with self.assertRaises(ValueError):asyncio.run(outer())
        rows=self.entries()
        self.assertEqual([r['stage'] for r in rows],['inner','outer'])
        self.assertEqual(len({r['operation_id'] for r in rows}),1)
        self.assertEqual([s['stage'] for s in rows[-1]['recent_steps']],['outer.start','inner.start'])

    def test_step_history_is_bounded(self):
        @d.logged('bounded')
        async def failure():
            for i in range(100):d.step('verify',attempt=i)
            raise RuntimeError('Verification failed')
        with self.assertRaises(RuntimeError):asyncio.run(failure())
        steps=self.entries()[0]['recent_steps']
        self.assertEqual(len(steps),30)
        self.assertEqual(steps[-1]['state']['attempt'],99)

    def test_cancelled_task_is_not_reported_as_failure(self):
        @d.logged('cancel')
        async def task():raise asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):asyncio.run(task())
        self.assertEqual(self.entries(),[])

    def test_concurrent_writers_produce_complete_json_records(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i:d.record('test.concurrent',ValueError('Synthetic failure'),attempt=i),range(30)))
        rows=self.entries()
        self.assertEqual(len(rows),30)
        self.assertEqual({r['state']['attempt'] for r in rows},set(range(30)))

    def test_rotation_is_bounded(self):
        d.LOGGER.handlers[0].maxBytes=1500
        for i in range(30):d.record('test.rotation',ValueError('Synthetic failure'),attempt=i)
        files=list(self.path.parent.glob('rad_error.log*'))
        self.assertGreater(len(files),1)
        self.assertLessEqual(len(files),4)

    def test_logging_failure_does_not_escape(self):
        with patch.object(d,'configure',side_effect=OSError('Disk full')),patch('sys.stderr'):
            self.assertIsNone(d.record('test.disk',ValueError('Synthetic failure')))

    def test_arbitrary_object_repr_is_not_invoked(self):
        class Private:
            def __repr__(self):raise AssertionError('Do not inspect object contents')
        d.record('test.object',ValueError('Synthetic failure'),value=Private())
        self.assertEqual(self.entries()[0]['state']['value'],{'type':'Private'})

    def test_asyncio_handler_writes_background_failure(self):
        import sys, threading
        loop=asyncio.new_event_loop();old_sys=sys.excepthook;old_thread=threading.excepthook
        try:
            d.install(loop)
            loop.call_exception_handler({'exception':RuntimeError('Background failure')})
            self.assertEqual(self.entries()[0]['stage'],'asyncio.unhandled')
        finally:
            loop.close();sys.excepthook=old_sys;threading.excepthook=old_thread
