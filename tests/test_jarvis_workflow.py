"""Independent workflow metadata/replay/security tests; temporary mock app, no providers."""
import asyncio
import concurrent.futures
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fastapi.testclient import TestClient
from jarvis_app.config.settings import Settings
from jarvis_app.main import create_app
from jarvis_app.workflow.events import EventBus


class WorkflowJournal(unittest.TestCase):
    def test_ring_is_bounded_and_old_cursor_requires_reset(self):
        bus=EventBus(3)
        for i in range(8): bus.emit('test.started',count=i)
        snap=bus.snapshot()
        self.assertEqual([e['id'] for e in snap['events']],[6,7,8])
        self.assertEqual(snap['first_id'],6)
        self.assertTrue(bus.read(0)['reset'])
        self.assertFalse(bus.read(5)['reset'])

    def test_replay_is_exclusive_and_limited(self):
        bus=EventBus()
        for i in range(7): bus.emit('test.started',count=i)
        self.assertEqual([e['id'] for e in bus.read(3,limit=2)['events']],[4,5])
        self.assertEqual(bus.read(7)['events'],[])

    def test_reboot_and_future_cursor_require_reset(self):
        bus=EventBus()
        self.assertTrue(bus.read(0,instance_id='old-instance')['reset'])
        self.assertTrue(bus.read(100)['reset'])
        self.assertFalse(bus.read(0,instance_id=bus.instance_id)['reset'])

    def test_emit_snapshot_read_cannot_mutate_journal(self):
        bus=EventBus()
        event=bus.emit('test.started',model='local')
        event['data']['model']='tampered'
        snap=bus.snapshot();snap['events'][0]['data']['model']='tampered'
        read=bus.read();read['events'][0]['data']['model']='tampered'
        self.assertEqual(bus.snapshot()['events'][0]['data']['model'],'local')

    def test_private_fields_nested_values_credentials_and_nonfinite_numbers_are_removed(self):
        bus=EventBus()
        bus.emit('model.started',prompt='PRIVATE PROMPT',args={'token':'SECRET'},text='PRIVATE REPLY',
                 label='nvapi-AbCdEf123456_ghIJ-kl',model='x'*400,ms=float('nan'),count=float('inf'),tool={'nested':'SECRET'})
        wire=json.dumps(bus.snapshot())
        for secret in ['PRIVATE PROMPT','PRIVATE REPLY','SECRET','nvapi-','NaN','Infinity']:
            self.assertNotIn(secret,wire)
        data=bus.snapshot()['events'][0]['data']
        self.assertNotIn('prompt',data); self.assertNotIn('ms',data);self.assertNotIn('tool',data)
        self.assertEqual(data['model'],'[metadata omitted]')

    def test_concurrent_writers_have_unique_ordered_sequences(self):
        bus=EventBus(1000)
        def writer(n):
            with bus.run('chat'):
                for _ in range(30): bus.emit('model.started',count=n)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(writer,range(8)))
        events=bus.snapshot()['events']
        self.assertEqual([e['id'] for e in events],list(range(1,257)))
        runs={e['run_id'] for e in events};self.assertEqual(len(runs),8)

    def test_nested_spans_link_to_run_without_cross_run_leak(self):
        bus=EventBus()
        with bus.run('chat') as root:
            with bus.span('model',provider='mock') as model:
                bus.emit('provider.served',model='mock-1')
        events=bus.snapshot()['events']
        self.assertEqual({e['run_id'] for e in events},{root.run_id})
        self.assertEqual(events[1]['parent_id'],root.node_id)
        self.assertEqual(events[2]['node_id'],model.node_id)
        outside=bus.emit('outside')
        self.assertNotEqual(outside['run_id'],root.run_id)

    def test_span_errors_record_type_never_exception_text(self):
        bus=EventBus()
        with self.assertRaisesRegex(ValueError,'private'):
            with bus.run('chat'): raise ValueError('private user content and credential')
        event=bus.snapshot()['events'][-1]
        self.assertEqual(event['status'],'error')
        self.assertEqual(event['data']['error_code'],'ValueError')
        self.assertNotIn('private',json.dumps(event))

    def test_slow_reader_does_not_create_subscriber_queue(self):
        bus=EventBus(2)
        bus.emit('start');bus.read()
        for _ in range(2000): bus.emit('work')
        self.assertEqual(len(bus.snapshot()['events']),2)
        self.assertTrue(bus.read(1)['reset'])


PROVIDERS='''active: mock
providers:
  mock: {type: mock}
models:
  mock: {provider: mock, model: mock-1, label: Mock, capabilities: [tools]}
'''

class WorkflowApi(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        config=root/'providers.yaml';config.write_text(PROVIDERS)
        self.settings=Settings(data_dir=root/'data',providers_file=config,workflow_omniroute_logs=None,workflow_project_root=None)
        self.app=create_app(self.settings)
        self.client=TestClient(self.app)
        self.headers={'X-Jarvis-Token':(self.settings.data_dir/'api_token').read_text()}

    def tearDown(self):
        self.client.close();self.tmp.cleanup()

    def test_workflow_apis_require_token_and_loopback_host(self):
        for route in ['/api/workflow/snapshot','/api/workflow/events']:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code,401)
                self.assertEqual(self.client.get(route,headers={'X-Jarvis-Token':'wrong'}).status_code,401)
                self.assertEqual(self.client.get(route,headers={**self.headers,'Host':'evil.example.com'}).status_code,403)

    def test_workflow_html_refuses_bad_host_and_keeps_original_chat(self):
        self.assertEqual(self.client.get('/workflow',headers={'Host':'evil.example.com'}).status_code,403)
        page=self.client.get('/workflow')
        self.assertEqual(page.status_code,200)
        self.assertNotIn('__JARVIS_TOKEN__',page.text)
        self.assertEqual(self.client.get('/').status_code,200)
        result=self.client.post('/api/chat',json={'text':'hello'},headers=self.headers)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['reply'],'Echo: hello')
        self.assertEqual(result.json()['model'],'mock:mock-1')

    def test_real_chat_and_tool_events_exclude_prompt_and_tool_args(self):
        secret='private_workflow_secret_xyz'
        for text in [secret,'tool:get_time {}','tool:remember '+json.dumps({'text':secret})]:
            response=self.client.post('/api/chat',json={'text':text},headers=self.headers)
            self.assertEqual(response.status_code,200)
        snapshot=self.client.get('/api/workflow/snapshot',headers=self.headers)
        self.assertEqual(snapshot.status_code,200)
        events=snapshot.json()['events']
        self.assertGreater(len(events),10)
        self.assertNotIn(secret,json.dumps(events))
        self.assertTrue(any(e['kind'].startswith('model.') for e in events))
        self.assertTrue(any('tool' in e['kind'] for e in events))
        model_nodes={e['node_id'] for e in events if e['kind'].startswith('model.')}
        memory_nodes={e['node_id'] for e in events if e['kind'].startswith('memory.')}
        self.assertTrue(memory_nodes)
        self.assertTrue(memory_nodes.isdisjoint(model_nodes),'Memory reads must remain distinct graph operations')
        self.assertEqual(self.client.get('/api/memory',headers=self.headers).json(),[])


class WorkflowStream(unittest.IsolatedAsyncioTestCase):
    async def test_replay_order_and_initial_heartbeat(self):
        from jarvis_app.workflow.stream import stream_events
        class Request:
            async def is_disconnected(self): return False
        bus=EventBus()
        for _ in range(3):bus.emit('test')
        stream=stream_events(Request(),bus,after=1,poll_s=.001)
        try:
            for ident in (2,3):
                frame=await asyncio.wait_for(anext(stream),1)
                self.assertIn('event: workflow',frame)
                self.assertIn('id: '+str(ident)+'\n',frame)
            self.assertIn('event: heartbeat',await asyncio.wait_for(anext(stream),1))
        finally:await stream.aclose()

    async def test_gap_and_reboot_stream_reset_contains_current_snapshot(self):
        from jarvis_app.workflow.stream import stream_events
        class Request:
            async def is_disconnected(self):return False
        bus=EventBus(2)
        for _ in range(4):bus.emit('test')
        for cursor,instance in [(0,None),(4,'previous-instance')]:
            stream=stream_events(Request(),bus,after=cursor,instance_id=instance)
            try:
                frame=await asyncio.wait_for(anext(stream),1)
                self.assertIn('event: reset',frame)
                payload=json.loads(frame.split('data: ',1)[1])
                self.assertEqual(payload['cursor'],4)
                self.assertEqual(len(payload['events']),2)
            finally:await stream.aclose()

    async def test_disconnect_mid_batch_stops_delivery(self):
        from jarvis_app.workflow.stream import stream_events
        class Request:
            calls=0
            async def is_disconnected(self):
                self.calls+=1
                return self.calls>2
        bus=EventBus()
        for _ in range(5):bus.emit('test')
        stream=stream_events(Request(),bus)
        self.assertIn('id: 1\n',await anext(stream))
        with self.assertRaises(StopAsyncIteration):await anext(stream)

    async def test_idle_stream_cancellation_finishes_promptly(self):
        from jarvis_app.workflow.stream import stream_events
        class Request:
            async def is_disconnected(self):return False
        stream=stream_events(Request(),EventBus(),poll_s=.01)
        self.assertIn('event: heartbeat',await anext(stream))
        pending=asyncio.create_task(anext(stream))
        await asyncio.sleep(.02)
        pending.cancel()
        with self.assertRaises(asyncio.CancelledError):await pending
        await stream.aclose()


if __name__=='__main__': unittest.main()
