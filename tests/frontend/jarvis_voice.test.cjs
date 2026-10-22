const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('src/jarvis_app/frontend/voice.js', 'utf8');
function setup(options = {}) {
  const context = vm.createContext({}); vm.runInContext(source, context);
  const element = () => ({textContent: '', disabled: false, attrs: {}, handlers: {},
    setAttribute(k,v) { this.attrs[k]=v; }, addEventListener(k,v) { this.handlers[k]=v; }, click() { if (!this.disabled) this.handlers.click(); }});
  const mic=element(), mute=element(), stop=element(), status=element(), input={value:'',maxLength:4000};
  const sent=[], spoken=[], instances=[]; let cancellations=0, busy=false;
  class Recognition {
    constructor() { instances.push(this); }
    start() { if(options.startError) throw options.startError; this.onstart(); }
    abort() { this.onend(); }
    result(text, final=true) { const result=[{transcript:text}]; result.isFinal=final; this.onresult({results:[result]}); }
  }
  const env = {navigator:{language:'en-US'}, isSecureContext:true, addEventListener(){},
    SpeechSynthesisUtterance:class {constructor(text){this.text=text;}},
    speechSynthesis:{cancel(){cancellations++;},getVoices(){return [{localService:true,lang:'en-US'}];},speak(u){spoken.push(u);}}};
  if (!options.unsupported) env[options.prefixed ? 'webkitSpeechRecognition' : 'SpeechRecognition']=Recognition;
  if(options.noSynthesis) delete env.speechSynthesis;
  const voice=context.createJarvisVoice({env,mic,mute,stop,status,input,submit:t=>sent.push(t),isBusy:()=>busy});
  return {voice,mic,mute,stop,status,input,sent,spoken,instances,setBusy:v=>busy=v,cancelled:()=>cancellations};
}
test('microphone starts only on click; interim text is displayed; final sent exactly once on end',()=>{
  const s=setup(); assert.equal(s.instances.length,0); s.mic.click();
  const r=s.instances[0]; assert.equal(r.continuous,false); assert.equal(s.mic.attrs['aria-pressed'],'true');
  r.result('hel',false); assert.equal(s.input.value,'hel'); assert.deepEqual(s.sent,[]);
  r.result('hello Jarvis'); assert.equal(s.input.value,'hello Jarvis'); r.onend(); r.onend();
  assert.deepEqual(s.sent,['hello Jarvis']); assert.equal(s.mic.attrs['aria-pressed'],'false');
});
test('webkit fallback works',()=>{const s=setup({prefixed:true}); s.mic.click(); assert.equal(s.instances.length,1);});
test('permission denial remains visible and does not submit',()=>{
  const s=setup(); s.mic.click(); const r=s.instances[0]; r.onerror({error:'not-allowed'}); r.onend();
  assert.match(s.status.textContent,/permission denied/); assert.deepEqual(s.sent,[]);
});
test('unsupported recognition and speech report errors without breaking text input',()=>{
  const s=setup({unsupported:true}); assert.equal(s.mic.disabled,true); assert.match(s.status.textContent,/unsupported/);
  const t=setup({noSynthesis:true}); assert.equal(t.mute.disabled,true); t.voice.speak('hello');
  assert.match(t.status.textContent,/unsupported/);
});
test('no-speech, capture and network failures are actionable',()=>{
  for(const error of ['no-speech','audio-capture','network','service-not-allowed']) {
    const s=setup(); s.mic.click(); s.instances[0].onerror({error}); s.instances[0].onend();
    assert.ok(s.status.textContent.length>30); assert.deepEqual(s.sent,[]);
  }
});
test('busy agent blocks recognition and preserves transcripts if busy on completion',()=>{
  const s=setup(); s.setBusy(true); s.mic.click(); assert.equal(s.instances.length,0);
  s.setBusy(false); s.mic.click(); s.instances[0].result('hello'); s.setBusy(true); s.instances[0].onend();
  assert.deepEqual(s.sent,[]); assert.equal(s.input.value,'hello');
});
test('cancel microphone and oversize transcript never submit',()=>{
  const s=setup(); s.mic.click(); s.instances[0].result('hello'); s.mic.click(); assert.deepEqual(s.sent,[]);
  s.mic.click(); s.instances[1].result('x'.repeat(4001)); s.instances[1].onend();
  assert.match(s.status.textContent,/too long/); assert.deepEqual(s.sent,[]);
});
test('speaks response with local voice, supports mute/unmute, stop and completion',()=>{
  const s=setup(); s.voice.speak('hello'); assert.equal(s.spoken[0].text,'hello');
  assert.equal(s.spoken[0].voice.localService,true); assert.equal(s.stop.disabled,false);
  s.stop.click(); assert.equal(s.stop.disabled,true); assert.ok(s.cancelled()>0);
  s.mute.click(); s.voice.speak('silent'); assert.equal(s.spoken.length,1); assert.equal(s.mute.textContent,'Unmute');
  s.mute.click(); s.voice.speak('again'); assert.equal(s.spoken.length,2);
  s.spoken[1].onend(); assert.equal(s.stop.disabled,true);
});
test('starting recognition cancels playback and does not speak while listening',()=>{
  const s=setup(); s.voice.speak('hi'); const count=s.cancelled(); s.mic.click();
  assert.ok(s.cancelled()>count); s.voice.speak('feedback'); assert.equal(s.spoken.length,1);
});
test('start exceptions and synthesis failures are shown',()=>{
  const s=setup({startError:new Error('device failure')}); s.mic.click(); assert.match(s.status.textContent,/device failure/);
  const t=setup(); t.voice.speak('hello'); t.spoken[0].onerror({error:'not-allowed'});
  assert.match(t.status.textContent,/Could not speak/); assert.equal(t.stop.disabled,true);
});
test('late events from an aborted session cannot submit or stop a new session',()=>{
  const s=setup(); s.mic.click(); const old=s.instances[0]; s.mic.click(); s.mic.click();
  old.onerror({error:'aborted'}); old.onend(); old.result('stale');
  assert.equal(s.mic.attrs['aria-pressed'],'true');
  s.instances[1].result('current'); s.instances[1].onend(); assert.deepEqual(s.sent,['current']);
});
test('chat integration keeps token, backend route, confirmations and reply speech',async()=>{
  const nodes={}; const calls=[], spoken=[];
  function node(key) { return nodes[key] ||= {content:'test-token',value:'',disabled:false,dataset:{},
    classList:{add(){},remove(){}},addEventListener(){},replaceChildren(){},append(){},setAttribute(){}}; }
  const context=vm.createContext({
    document:{querySelector:node,createElement:()=>node('created')},window:{},
    createJarvisVoice:()=>({stopSpeaking(){},speak:t=>spoken.push(t)}),
    fetch:async(path,opts)=>{calls.push({path,opts}); return {ok:true,json:async()=>path==='/api/chat'||path==='/api/confirm'?{reply:'selected model reply'}:[]};},
    setInterval(){},setTimeout(){},clearTimeout(){},
  });
  vm.runInContext(fs.readFileSync('src/jarvis_app/frontend/app.js','utf8'),context);
  await vm.runInContext('send("recognized words")',context);
  const call=calls.find(c=>c.path==='/api/chat');
  assert.equal(call.opts.headers['X-Jarvis-Token'],'test-token');
  assert.deepEqual(JSON.parse(call.opts.body),{text:'recognized words',conv:'default'});
  assert.deepEqual(spoken,['selected model reply']);
  await vm.runInContext('confirmAct("pending-id", true)',context);
  const confirmation=calls.find(c=>c.path==='/api/confirm');
  assert.deepEqual(JSON.parse(confirmation.opts.body),{id:'pending-id',approve:true});
  assert.equal(spoken.length,2);
  await vm.runInContext('refresh()',context); assert.equal(spoken.length,2);
});
