"""Real Chrome + SSE validation against an isolated temporary MockProvider app.

/opt/anaconda3/bin/python3 tracker/render_jarvis_workflow.py
No production model, approvals, memory or tokens are changed; no paid calls.
"""
import base64
import json
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
import websocket

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from jarvis_app.main import create_app
from jarvis_app.config.settings import Settings

CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
OUT=ROOT/'artifacts/logs/render'
CONFIG='''active: mock
providers:
  mock: {type: mock}
models:
  mock: {provider: mock, model: mock-1, label: Mock, capabilities: [tools]}
'''


class CDP:
    def __init__(self,url):
        self.ws=websocket.create_connection(url,timeout=10,suppress_origin=True)
        self.seq=0
        self.events=[]
    def command(self,method,params=None):
        self.seq+=1
        ident=self.seq
        self.ws.send(json.dumps({'id':ident,'method':method,'params':params or {}}))
        while True:
            value=json.loads(self.ws.recv())
            if value.get('id')==ident:
                if 'error' in value: raise RuntimeError(value['error'])
                return value.get('result',{})
            if value.get('method'): self.events.append(value)
    def evaluate(self,expression):
        result=self.command('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True})
        if 'exceptionDetails' in result: raise RuntimeError(result['exceptionDetails'])
        return result['result'].get('value')
    def wait(self,expression,timeout=12):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            value=self.evaluate(expression)
            if value:return value
            time.sleep(.1)
        raise RuntimeError('Browser condition not reached: '+expression+'; url='+str(self.evaluate('location.href'))+'; body='+str(self.evaluate('document.body.innerText')).replace('\n',' ')[:1500]+'; errors='+str(self.evaluate('window.__workflowErrors')))


def http_json(url,token=None,body=None):
    headers={'X-Jarvis-Token':token} if token else {}
    data=None
    if body is not None:
        data=json.dumps(body).encode();headers['Content-Type']='application/json'
    with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=headers),timeout=15) as r:
        return json.load(r)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='jarvis-workflow-browser-') as tmp:
        tmp=Path(tmp)
        config=tmp/'providers.yaml';config.write_text(CONFIG)
        settings=Settings(data_dir=tmp/'data',providers_file=config,workflow_omniroute_logs=None,workflow_project_root=None)
        app=create_app(settings)
        token=(settings.data_dir/'api_token').read_text()
        listener=socket.socket();listener.bind(('127.0.0.1',0))
        port=listener.getsockname()[1]
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning'))
        thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True);thread.start()
        deadline=time.monotonic()+10
        while not server.started and time.monotonic()<deadline:time.sleep(.05)
        if not server.started: raise RuntimeError('Temporary app did not start')
        browser=subprocess.Popen([CHROME,'--headless=new','--disable-gpu','--no-first-run',
            '--no-default-browser-check','--remote-debugging-port=0',f'--user-data-dir={tmp/"chrome"}',
            '--window-size=1440,1100','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            active=tmp/'chrome/DevToolsActivePort'
            deadline=time.monotonic()+10
            while not active.exists() and time.monotonic()<deadline:time.sleep(.05)
            debugport=int(active.read_text().splitlines()[0])
            targets=http_json(f'http://127.0.0.1:{debugport}/json/list')
            target=next(t for t in targets if t.get('type')=='page')
            cdp=CDP(target['webSocketDebuggerUrl'])
            cdp.command('Page.enable');cdp.command('Runtime.enable');cdp.command('Network.enable')
            cdp.command('Page.addScriptToEvaluateOnNewDocument',{'source':"window.__workflowErrors=[];addEventListener('error',e=>window.__workflowErrors.push(e.message));addEventListener('unhandledrejection',e=>window.__workflowErrors.push(String(e.reason)));"})
            origin=f'http://127.0.0.1:{port}'
            time.sleep(.5)
            navigation=cdp.command('Page.navigate',{'url':origin+'/workflow'})
            if navigation.get('errorText'):raise RuntimeError('Navigation failed: '+str(navigation))
            cdp.wait("document.querySelector('.connection')?.textContent.includes('Connected')")
            initial=http_json(origin+'/api/workflow/snapshot',token)
            result=http_json(origin+'/api/chat',token,{'text':'workflow browser privacy sentinel'})
            if result['reply']!='Echo: workflow browser privacy sentinel':raise AssertionError('Original chat response changed')
            http_json(origin+'/api/chat',token,{'text':'tool:get_time {}'})
            snapshot=http_json(origin+'/api/workflow/snapshot',token)
            run_id=next(e['run_id'] for e in reversed(snapshot['events']) if e['kind'].startswith('tool.'))
            cdp.wait("[...document.querySelector('#run-select').options].some(o=>o.value==="+json.dumps(run_id)+")")
            cdp.evaluate("(()=>{const s=document.querySelector('#run-select');s.value="+json.dumps(run_id)+";s.dispatchEvent(new Event('change',{bubbles:true}));})()")
            cdp.wait("document.querySelectorAll('.op-node').length>=3")
            cdp.wait("document.querySelectorAll('.timeline-events button').length>=3")
            checks={
                'connected':cdp.evaluate("document.querySelector('.connection').textContent.includes('Connected')"),
                'real_events_generated':snapshot['cursor']>initial['cursor'],
                'no_prompt_in_events':'workflow browser privacy sentinel' not in json.dumps(snapshot),
                'react_flow':cdp.evaluate("!!document.querySelector('.react-flow')"),
                'nodes':cdp.evaluate("document.querySelectorAll('.op-node').length>=3"),
                'distinct_memory_events':any(e['kind'].startswith('memory.') and e['run_id']==run_id and e['node_id'] not in {m['node_id'] for m in snapshot['events'] if m['kind'].startswith('model.')} for e in snapshot['events']),
                'memory_nodes_visible':cdp.evaluate("[...document.querySelectorAll('.op-node .node-kind')].some(e=>e.textContent.includes('memory'))"),
                'timeline':cdp.evaluate("document.querySelectorAll('.timeline-events button').length>=3"),
                'no_errors':cdp.evaluate('window.__workflowErrors.length===0'),
                'chat_intact':result['model']=='mock:mock-1',
            }
            cdp.evaluate("document.querySelector('.timeline-events button').click()")
            checks['inspector']=cdp.evaluate("!!document.querySelector('.inspector')")
            for width,height,name in [(1440,1100,'desktop'),(390,1100,'mobile')]:
                cdp.command('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':width<500})
                time.sleep(.25)
                cdp.evaluate("document.querySelector('.react-flow__controls-fitview')?.click()")
                time.sleep(.3)
                checks[name+'_overflow']=cdp.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                image=cdp.command('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
                (OUT/f'jarvis_workflow_{name}.png').write_bytes(base64.b64decode(image['data']))
            requests=[e['params']['request'] for e in cdp.events if e['method']=='Network.requestWillBeSent']
            checks['sse_requested']=any('/api/workflow/events' in r['url'] for r in requests)
            checks['browser_no_posts']=all(r['method']=='GET' for r in requests)
            checks['local_requests_only']=all(r['url'].startswith(origin) or r['url'].startswith('data:') for r in requests)
            report={'checks':checks,'event_count':len(snapshot['events']),'cursor':snapshot['cursor'],
                    'node_count':cdp.evaluate("document.querySelectorAll('.op-node').length"),'errors':cdp.evaluate('window.__workflowErrors'),
                    'screenshots':['artifacts/logs/render/jarvis_workflow_desktop.png','artifacts/logs/render/jarvis_workflow_mobile.png']}
            (OUT/'jarvis_workflow_validation.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report,indent=2))
            if not all(checks.values()):raise SystemExit(1)
            cdp.ws.close()
        finally:
            browser.terminate()
            try:browser.wait(timeout=5)
            except subprocess.TimeoutExpired:browser.kill();browser.wait()
            server.should_exit=True;thread.join(timeout=5);listener.close()


if __name__=='__main__':main()
