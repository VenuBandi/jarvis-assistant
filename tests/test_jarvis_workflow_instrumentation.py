"""Metadata-only workflow instrumentation and permission regression checks."""
import json
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_jarvis_app_core import Base
from jarvis_app.models.base import ToolCall


class Events:
    def __init__(self):
        self.items = []

    def emit(self, kind, **data):
        self.items.append({'kind': kind, **data})

    @contextmanager
    def span(self, kind, **data):
        self.emit(kind + '.started', **data)
        result = {}
        class Span:
            def finish(self, **values):
                result.update(values)
        try:
            yield Span()
        except Exception:
            self.emit(kind + '.error', error_code='operation_failed')
            raise
        else:
            self.emit(kind + '.completed', **result)


class TestInstrumentation(Base):
    def setUp(self):
        super().setUp()
        self.events = Events()
        self.agent.events = self.events
        self.agent.models.events = self.events
        self.conv = "workflow-test"
        self.agent.db.add_message(self.conv, "user", "test request")

    def test_failed_validation_root_status(self):
        response = self.c.post('/api/model/validate', json={'name': 'down'}, headers=self.h)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['ok'])
        roots = [e for e in self.app.state.workflow_events.snapshot()['events'] if e['kind'] == 'run.error']
        self.assertTrue(roots)
        self.assertEqual(roots[-1]['data']['label'], 'Validate model')

    def test_lifespan_exception_always_stops_bridge(self):
        import asyncio
        from unittest.mock import patch
        bridge = self.app.state.workflow_bridge
        async def exercise():
            async with self.app.router.lifespan_context(self.app):
                raise RuntimeError('synthetic lifespan failure')
        with patch.object(bridge, 'start') as started, patch.object(bridge, 'stop') as stopped:
            with self.assertRaises(RuntimeError):
                asyncio.run(exercise())
            started.assert_called_once()
            stopped.assert_called_once()

    def test_absent_provider_model_remains_unknown(self):
        from jarvis_app.models.base import ChatResult
        from unittest.mock import patch
        adapter = self.agent.models.adapter('mock')
        with patch.object(adapter, 'chat', return_value=ChatResult(text='hello', model='requested', model_reported=False)):
            self.agent.handle(self.conv, 'hello')
        served = next(e for e in self.events.items if e['kind'] == 'model.served')
        self.assertEqual(served['served_model'], 'unknown')

    def test_model_metadata_never_contains_prompt(self):
        self.agent.handle(self.conv, 'private sentinel transcript')
        kinds = [e['kind'] for e in self.events.items]
        self.assertIn('model.requested', kinds)
        self.assertIn('model.served', kinds)
        self.assertNotIn('private sentinel', json.dumps(self.events.items))

    def test_invalid_denied_pending_and_rejected(self):
        self.agent._tool_step(self.conv, ToolCall('a', 'unknown', {}))
        self.agent.tools.disabled_permissions.add('memory_write')
        denied = self.agent._tool_step(self.conv, ToolCall('b', 'remember', {'text': 'private sentinel'}))
        self.assertEqual(denied['status'], 'denied')
        self.agent.tools.disabled_permissions.clear()
        invalid = self.agent._tool_step(self.conv, ToolCall('c', 'remember', {'text': 'x'}))
        self.assertEqual(invalid['status'], 'invalid')
        pending = self.agent._tool_step(self.conv, ToolCall('d', 'remember', {'text': 'private sentinel'}))
        self.agent.confirm(pending['pending']['id'], False)
        self.assertTrue(any(e.get('status') == 'waiting' for e in self.events.items))
        self.assertTrue(any(e.get('status') == 'rejected' for e in self.events.items))
        self.assertNotIn('private sentinel', json.dumps(self.events.items))
        self.assertFalse(any(e['kind'] == 'memory.write' for e in self.events.items))

    def test_confirmation_rechecks_permission(self):
        pending = self.agent._tool_step(self.conv, ToolCall('a', 'remember', {'text': 'private sentinel'}))
        self.agent.tools.disabled_permissions.add('memory_write')
        res = self.agent.confirm(pending['pending']['id'], True)
        self.assertEqual(res.steps[0]['status'], 'denied')
        self.assertEqual(self.agent.db.memories(), [])

    def test_successful_memory_write_and_disabled_noop(self):
        for enabled, expected in [(True, 1), (False, 0)]:
            self.agent.settings.memory_enabled = enabled
            pending = self.agent._tool_step(self.conv, ToolCall(str(enabled), 'remember', {'text': 'private sentinel'}))
            self.agent.confirm(pending['pending']['id'], True)
            writes = [e for e in self.events.items if e['kind'] == 'memory.write']
            self.assertEqual(writes[-1]['count'], expected)
        self.assertNotIn('private sentinel', json.dumps(self.events.items))

    def test_real_memory_operations_have_distinct_graph_nodes(self):
        from jarvis_app.workflow.events import EventBus
        bus = EventBus()
        self.agent.events = self.agent.models.events = bus
        with bus.run(action='chat') as run:
            self.agent.handle(self.conv, 'hello')
            pending = self.agent._tool_step(self.conv, ToolCall('memory', 'remember', {'text': 'private sentinel'}))
            self.agent.confirm(pending['pending']['id'], True)
            self.agent._tool_step(self.conv, ToolCall('list', 'list_memory', {}))
        events = bus.snapshot()['events']
        memory = [e for e in events if e['kind'] == 'memory.completed']
        self.assertGreaterEqual(len(memory), 3)
        self.assertTrue(all(e['run_id'] == run.run_id for e in memory))
        for node in memory:
            self.assertNotEqual(node['node_id'], node['parent_id'])
            parent = next(e for e in events if e['node_id'] == node['parent_id'])
            self.assertIn(parent['kind'], ['model.started', 'tool.execution.started'])
            self.assertIn(node['data']['operation'], ['read', 'write'])
            self.assertGreaterEqual(node['data']['count'], 0)
        writes = [e for e in events if e['kind'] == 'memory.write']
        self.assertEqual(writes[0]['count'] if 'count' in writes[0] else writes[0]['data']['count'], 1)
        self.assertNotIn('private sentinel', json.dumps(events))

    def test_real_bus_hierarchy_latency_and_worker_context(self):
        from jarvis_app.workflow.events import EventBus
        bus = EventBus()
        self.agent.events = self.agent.models.events = bus
        with bus.run(action='chat') as run:
            self.agent.handle(self.conv, 'hello')
        events = bus.snapshot()['events']
        self.assertTrue(all(e['run_id'] == run.run_id for e in events))
        model = next(e for e in events if e['kind'] == 'model.completed')
        self.assertGreaterEqual(model['data']['ms'], 0)
        self.assertEqual(model['parent_id'], run.node_id)
        self.assertTrue(any(e['kind'] == 'model.served' for e in events))
        # Registry workers retain the run context for nested model-switch events.
        with bus.run(action='tool') as tool_run:
            self.agent._tool_step(self.conv, ToolCall('switch', 'switch_model', {'name': 'other'}))
        switched = [e for e in bus.snapshot()['events'] if e['kind'] == 'model.switch']
        self.assertEqual(switched[-1]['run_id'], tool_run.run_id)

    def test_switch_retains_selected_on_failure(self):
        old = self.agent.models.active
        self.assertFalse(self.agent.models.switch('down')['ok'])
        self.assertEqual(self.agent.models.active, old)
        self.assertTrue(any(e['kind'] == 'model.switch.retained' for e in self.events.items))
        self.assertNotIn('sk-ant-', json.dumps(self.events.items))


if __name__ == '__main__':
    unittest.main()
