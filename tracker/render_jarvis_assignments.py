"""Real handoff-file -> read-only bridge -> SSE -> React Flow browser validation.
Runs only an isolated temporary MockProvider app and synthetic local source files.
"""
import base64
import json
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import uvicorn

from render_jarvis_workflow import CDP, CHROME, CONFIG, OUT, http_json, create_app, Settings


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='jarvis-assignment-browser-') as tmp:
        tmp=Path(tmp);project=tmp/'project'
        folder=project/'artifacts/handoff/WTEST';folder.mkdir(parents=True)
        plan=project/'artifacts/handoff/plan.json'
        plan.write_text(json.dumps({'tasks':[{'id':'WTEST','title':'Fixture assignment','who':'FixtureAgent','checker':'FixtureReviewer','brain':'FixtureBrain'}]}))
        status=folder/'status.json'
        def update(state,**extra):
            from datetime import datetime,timezone
            status.write_text(json.dumps({'state':state,'last_activity':datetime.now(timezone.utc).isoformat(),'outputs':['reports/result.md'],**extra}))
        update('running')
        config=tmp/'providers.yaml';config.write_text(CONFIG)
        settings=Settings(data_dir=tmp/'data',providers_file=config,workflow_omniroute_logs=None,workflow_project_root=project)
        app=create_app(settings);token=(settings.data_dir/'api_token').read_text()
        listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);thread.start()
        end=time.monotonic()+10
        while not server.started and time.monotonic()<end:time.sleep(.05)
        if not server.started:raise RuntimeError('Temporary server failed')
        browser=subprocess.Popen([CHROME,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
            '--remote-debugging-port=0',f'--user-data-dir={tmp/"chrome"}','--window-size=1440,1100','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            active=tmp/'chrome/DevToolsActivePort';end=time.monotonic()+10
            while not active.exists() and time.monotonic()<end:time.sleep(.05)
            debugport=int(active.read_text().splitlines()[0])
            target=next(t for t in http_json(f'http://127.0.0.1:{debugport}/json/list') if t.get('type')=='page')
            cdp=CDP(target['webSocketDebuggerUrl'])
            for command in ['Page.enable','Runtime.enable','Network.enable']:cdp.command(command)
            cdp.command('Page.addScriptToEvaluateOnNewDocument',{'source':"window.__workflowErrors=[];addEventListener('error',e=>window.__workflowErrors.push(e.message));addEventListener('unhandledrejection',e=>window.__workflowErrors.push(String(e.reason)));"})
            origin=f'http://127.0.0.1:{port}';time.sleep(.5)
            navigation=cdp.command('Page.navigate',{'url':origin+'/workflow'})
            if navigation.get('errorText'):raise RuntimeError(navigation['errorText'])
            cdp.wait("document.querySelector('.connection')?.textContent.includes('Connected')")
            first=http_json(origin+'/api/workflow/snapshot',token)
            event=next(e for e in first['events'] if e['kind']=='assignment.recorded' and e['data'].get('task_id')=='WTEST')
            run=event['run_id']
            cdp.wait("!!document.querySelector('#source-select')")
            cdp.evaluate("(()=>{const s=document.querySelector('#source-select');s.value='flightops';s.dispatchEvent(new Event('change',{bubbles:true}));})()")
            cdp.wait("[...document.querySelector('#run-select').options].some(o=>o.value==="+json.dumps(run)+")")
            cdp.evaluate("(()=>{const s=document.querySelector('#run-select');s.value="+json.dumps(run)+";s.dispatchEvent(new Event('change',{bubbles:true}));})()")
            cdp.wait("document.querySelectorAll('.assignment-node').length>=3")
            checks={'connected':True,'recorded_running_not_live':event['status']=='unknown',
                'no_running_assignment_nodes':cdp.evaluate("document.querySelectorAll('.assignment-node.running').length===0"),
                'source_filter':cdp.evaluate("document.querySelector('#source-select').value==='flightops'"),
                'record_notice':cdp.evaluate("!!document.querySelector('.record-notice')"),
                'unverified_review':any(e['kind']=='assignment.review' and e['data'].get('review_state')=='unverified' for e in first['events'])}
            output=project/'reports/result.md';output.parent.mkdir(parents=True);output.write_text('PRIVATE OUTPUT BODY DO NOT SEND')
            update('done',review_state='accept')
            end=time.monotonic()+12;latest=first
            while time.monotonic()<end:
                latest=http_json(origin+'/api/workflow/snapshot',token)
                if any(e['id']>first['cursor'] and e['kind']=='assignment.recorded' and e['data'].get('recorded_state')=='done' for e in latest['events']):break
                time.sleep(.1)
            checks['real_file_update']=latest['cursor']>first['cursor']
            cdp.wait("[...document.querySelectorAll('.assignment-node')].some(e=>e.textContent.includes('done'))")
            checks['sse_updated_ui']=True
            checks['private_body_excluded']='PRIVATE OUTPUT BODY' not in json.dumps(latest)
            checks['output_exists']=any(e['data'].get('output_path')=='reports/result.md' and e['data'].get('available') for e in latest['events'])
            checks['explicit_review']=any(e['kind']=='assignment.review' and e['data'].get('review_state')=='accepted' for e in latest['events'])
            cdp.evaluate("document.querySelector('.assignment-node')?.click()")
            for width,height,name in [(1440,1100,'desktop'),(390,1100,'mobile')]:
                cdp.command('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<500})
                time.sleep(.3);cdp.evaluate("document.querySelector('.react-flow__controls-fitview')?.click()");time.sleep(.3)
                checks[name+'_overflow']=cdp.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                png=cdp.command('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
                (OUT/f'jarvis_assignments_{name}.png').write_bytes(base64.b64decode(png['data']))
            requests=[e['params']['request'] for e in cdp.events if e['method']=='Network.requestWillBeSent']
            checks['sse_requested']=any('/api/workflow/events' in r['url'] for r in requests)
            checks['no_posts']=all(r['method']=='GET' for r in requests)
            checks['local_only']=all(r['url'].startswith(origin) or r['url'].startswith('data:') for r in requests)
            checks['no_errors']=cdp.evaluate('window.__workflowErrors.length===0')
            report={'checks':checks,'events':len(latest['events']),'node_count':cdp.evaluate("document.querySelectorAll('.assignment-node').length"),'errors':cdp.evaluate('window.__workflowErrors')}
            (OUT/'jarvis_assignments_validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
            if not all(checks.values()):raise SystemExit(1)
            cdp.ws.close()
        finally:
            browser.terminate()
            try:browser.wait(timeout=5)
            except subprocess.TimeoutExpired:browser.kill();browser.wait()
            server.should_exit=True;thread.join(timeout=5);listener.close()


if __name__=='__main__':main()
