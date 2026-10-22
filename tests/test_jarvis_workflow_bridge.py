"""OmniRoute bridge: synthetic local metadata, no network or user logs."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from jarvis_app.workflow.events import EventBus
from jarvis_app.workflow.omniroute import OmniRouteBridge

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.bus=EventBus(); self.bridge=OmniRouteBridge(self.bus,None)
    def summary(self,sid='one',**kw):
        return {'id':sid,'status':200,'provider':'provider-a','model':'model-a','requestedModel':'provider-a/model-a','duration':42,'timestamp':'2026-10-21T00:00:00Z',**kw}
    def test_metadata_only_and_deduplicated(self):
        row=self.summary(account='SECRET_ACCOUNT',connectionId='PRIVATE_CONNECTION',error='RAW_ERROR',apiKeyId='API_KEY',messages='PRIVATE_MESSAGE')
        self.assertTrue(self.bridge.ingest(row)); self.assertFalse(self.bridge.ingest(row))
        snap=self.bus.snapshot(); self.assertEqual(len(snap['events']),1)
        for text in ['SECRET_ACCOUNT','PRIVATE_CONNECTION','RAW_ERROR','API_KEY','PRIVATE_MESSAGE']:
            self.assertNotIn(text,json.dumps(snap))
        data=snap['events'][0]['data']; self.assertEqual(data['ms'],42); self.assertEqual(data['recorded_at'],row['timestamp'])
    def test_correlated_failed_combo_route_change(self):
        self.bridge.ingest(self.summary('one',status=429,comboExecutionKey='combo'))
        self.bridge.ingest(self.summary('two',provider='provider-b',model='model-b',comboExecutionKey='combo'))
        events=self.bus.snapshot()['events']; fallback=next(e for e in events if e['kind']=='provider.fallback')
        self.assertEqual(fallback['data']['from_provider'],'provider-a'); self.assertEqual(fallback['data']['to_provider'],'provider-b')
        self.assertEqual(fallback['parent_id'],events[0]['node_id']); self.assertEqual(events[-1]['parent_id'],fallback['node_id'])
        self.assertEqual(len({e['run_id'] for e in events}),1)
    def test_unrelated_or_successful_alias_change_not_fallback(self):
        self.bridge.ingest(self.summary('one',status=429)); self.bridge.ingest(self.summary('two',provider='provider-b'))
        self.bridge.ingest(self.summary('three',requestedModel='alias',comboExecutionKey='x'))
        self.bridge.ingest(self.summary('four',provider='provider-b',comboExecutionKey='x'))
        self.assertFalse(any(e['kind']=='provider.fallback' for e in self.bus.snapshot()['events']))
    def test_missing_route_is_not_proof(self):
        self.bridge.ingest(self.summary('one',status=500,provider=None,model=None,comboExecutionKey='combo'))
        self.bridge.ingest(self.summary('two',comboExecutionKey='combo'))
        self.assertFalse(any(e['kind']=='provider.fallback' for e in self.bus.snapshot()['events']))
    def test_invalid_records(self):
        for row in [None,{},self.summary(status=True),self.summary(status=999),self.summary(id=[])]:
            self.assertFalse(self.bridge.ingest(row))
        self.assertEqual(self.bus.snapshot()['cursor'],0)
    def test_scan_partial_cache_and_bodies(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/datetime.now(timezone.utc).date().isoformat(); folder.mkdir(); path=folder/'one.json'
            path.write_text('{"summary":'); bridge=OmniRouteBridge(self.bus,Path(tmp)); self.assertEqual(bridge.scan(initial=True),0)
            path.write_text(json.dumps({'summary':self.summary(),'requestBody':{'messages':'PRIVATE_BODY'},'responseBody':{'choices':'PRIVATE_ANSWER'},'error':'PRIVATE_ERROR'}))
            self.assertEqual(bridge.scan(),1)
            with patch.object(Path,'read_bytes',side_effect=AssertionError('cache expected')): self.assertEqual(bridge.scan(),0)
            self.assertNotIn('PRIVATE_',json.dumps(self.bus.snapshot()))
    def test_disabled_reports_unknown(self):
        self.bridge.start(); self.assertIsNone(self.bridge._thread)
        event=self.bus.snapshot()['events'][0]; self.assertEqual(event['status'],'unknown'); self.assertFalse(event['data']['available'])

if __name__=='__main__': unittest.main()
