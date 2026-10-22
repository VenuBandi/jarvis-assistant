"""Independent read-only assignment bridge/privacy/update tests in isolated roots."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from jarvis_app.workflow.events import EventBus
from jarvis_app.workflow.assignments import AssignmentBridge

NOW=lambda:datetime.now(timezone.utc).isoformat()

class AssignmentRecords(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.bus=EventBus()
        self.bridge=AssignmentBridge(self.bus,self.root)
        self.plan='artifacts/handoff/plan.json'
        self.status='artifacts/handoff/WTEST/status.json'

    def tearDown(self):self.bridge.stop();self.tmp.cleanup()

    def write(self,path,data):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(data));return p

    def task(self,**status):
        self.write(self.plan,{'tasks':[{'id':'WTEST','title':'Fixture assignment','who':'FixtureAgent','checker':'FixtureReviewer'}]})
        self.write(self.status,{'state':'running','last_activity':NOW(),**status})

    def events(self,kind=None):
        items=self.bus.snapshot()['events']
        return [e for e in items if (not kind or e['kind']==kind) and e['data'].get('task_id')=='WTEST']

    def test_running_record_is_not_claimed_live_execution(self):
        self.task();self.bridge.scan()
        event=self.events('assignment.recorded')[-1]
        self.assertEqual(event['status'],'unknown')
        self.assertEqual(event['data']['recorded_state'],'running')
        self.assertEqual(event['data']['source'],'flightops')
        self.assertEqual(event['data']['visibility'],'assignment_record')
        self.assertEqual(event['data']['agent'],'FixtureAgent')
        self.assertEqual(event['data']['checker'],'FixtureReviewer')

    def test_done_does_not_infer_accepted_review(self):
        self.task(state='done',msg='Reviewer accepted! all verified')
        self.bridge.scan()
        review=self.events('assignment.review')[-1]
        self.assertEqual(review['data']['review_state'],'unverified')

    def test_only_explicit_structured_review_is_reported(self):
        self.task(state='done',review={'verdict':'accept_with_notes'})
        self.bridge.scan()
        self.assertEqual(self.events('assignment.review')[-1]['data']['review_state'],'accepted_with_notes')

    def test_stale_missing_or_old_active_timestamp_is_visible(self):
        self.task(last_activity='2000-01-01T00:00:00+00:00')
        self.bridge.scan()
        self.assertTrue(self.events('assignment.recorded')[-1]['data']['stale'])

    def test_unchanged_scans_dedupe_and_real_update_keeps_identity(self):
        self.task();self.bridge.scan()
        first=self.events('assignment.recorded')[-1]
        before=self.bus.snapshot()['cursor']
        self.bridge.scan();self.assertEqual(self.bus.snapshot()['cursor'],before)
        self.task(state='done',review_state='accept')
        self.bridge.scan();last=self.events('assignment.recorded')[-1]
        self.assertEqual(first['node_id'],last['node_id'])
        self.assertEqual(first['run_id'],last['run_id'])
        self.assertEqual(last['data']['recorded_state'],'done')
        self.assertGreater(last['id'],first['id'])

    def test_output_references_existence_only_no_contents_or_private_payloads(self):
        output=self.root/'reports/result.md';output.parent.mkdir(parents=True);output.write_text('PRIVATE OUTPUT BODY')
        self.task(outputs=['reports/result.md'],msg='PRIVATE MESSAGE',args={'password':'PRIVATE ARGS'})
        self.bridge.scan()
        wire=json.dumps(self.bus.snapshot())
        for value in ['PRIVATE OUTPUT BODY','PRIVATE MESSAGE','PRIVATE ARGS']:self.assertNotIn(value,wire)
        self.assertTrue(any(e['data'].get('output_path')=='reports/result.md' for e in self.events('assignment.output')))

    def test_secret_absolute_traversal_and_data_paths_are_not_forwarded(self):
        self.task(outputs=['.aws/credentials','data/private.csv','../outside.txt','/private/tmp/secret.txt','artifacts/keys/api_token','reports/../../data/private.csv'])
        self.bridge.scan()
        paths=[e['data'].get('output_path') for e in self.events('assignment.output')]
        self.assertEqual(paths,[])

    def test_symlink_source_is_never_followed(self):
        self.task()
        target=self.root/'outside.json';target.write_text(json.dumps({'state':'done','brain':'PRIVATE_SYMLINK_PROVIDER'}))
        source=self.root/self.status;source.unlink();source.symlink_to(target)
        self.bridge.scan()
        self.assertNotIn('PRIVATE_SYMLINK_PROVIDER',json.dumps(self.bus.snapshot()))

    def test_symlink_output_is_not_exposed(self):
        self.task(outputs=['reports/result.md'])
        p=self.root/'reports';p.mkdir()
        target=self.root/'private.txt';target.write_text('PRIVATE')
        (p/'result.md').symlink_to(target)
        self.bridge.scan()
        self.assertFalse(any(e['data'].get('output_path')=='reports/result.md' and e['data'].get('available') for e in self.events('assignment.output')))

    def test_malformed_and_oversized_sources_fail_closed(self):
        p=self.root/self.plan;p.parent.mkdir(parents=True)
        p.write_text('{invalid')
        self.bridge.scan()
        self.assertEqual(self.events(),[])
        p.write_text(' '*1_048_577)
        self.bridge.scan()
        self.assertEqual(self.events(),[])

    def test_deleted_source_marks_previous_nodes_unavailable(self):
        self.task();self.bridge.scan()
        previous={e['node_id'] for e in self.events()}
        (self.root/self.plan).unlink()
        self.bridge.scan()
        removed=self.events('assignment.unavailable')
        self.assertTrue(removed)
        self.assertTrue(previous.issubset({e['node_id'] for e in removed}))
        self.assertTrue(all(e['status']=='unknown' and e['data'].get('available') is False for e in removed))

    def test_output_deletion_updates_existence_without_source_edit(self):
        output=self.root/'reports/result.md';output.parent.mkdir(parents=True);output.write_text('result')
        self.task(outputs=['reports/result.md']);self.bridge.scan()
        self.assertTrue(self.events('assignment.output')[-1]['data']['available'])
        before=(self.root/self.status).read_bytes()
        output.unlink();self.bridge.scan()
        self.assertFalse(self.events('assignment.output')[-1]['data']['available'])
        self.assertEqual((self.root/self.status).read_bytes(),before)

    def test_source_files_remain_byte_identical_after_scans(self):
        self.task(outputs=['reports/missing.md'])
        before={str(p):p.read_bytes() for p in self.root.rglob('*.json')}
        self.bridge.scan();self.bridge.scan()
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*.json')})

    def test_unsafe_task_id_does_not_escape_handoff_directory(self):
        self.write(self.plan,{'tasks':[{'id':'../../PRIVATE_ESCAPE','who':'secret'}]})
        self.bridge.scan()
        self.assertNotIn('PRIVATE_ESCAPE',json.dumps(self.bus.snapshot()))


if __name__=='__main__':unittest.main()
