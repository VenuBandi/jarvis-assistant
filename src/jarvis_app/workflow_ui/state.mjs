export const initialState = () => ({events: [], cursor: 0, first_id: 0, instance_id: null, gap: false});
export function mergeEvents(state, incoming) {
  const map = new Map(state.events.map(e => [e.id,e]));
  for (const event of incoming || []) if (Number.isInteger(event.id) && event.id > 0 && typeof event.run_id === 'string' && typeof event.node_id === 'string') map.set(event.id,event);
  let events = [...map.values()].sort((a,b) => a.id-b.id).slice(-500);
  // Bound distinct runs, rather than treating a run's many events as separate runs.
  const recentRuns=[]; for(const e of [...events].reverse()) if(!recentRuns.includes(e.run_id)) {recentRuns.push(e.run_id);if(recentRuns.length===100)break;}
  events=events.filter(e => recentRuns.includes(e.run_id));
  return {...state, events, cursor: Math.max(state.cursor,...events.map(e => e.id))};
}
export function applySnapshot(state,snapshot,reset=false) {
  const changed=!!state.instance_id && state.instance_id!==snapshot.instance_id;
  const gap=changed || (state.cursor>0 && Number(snapshot.first_id)>state.cursor+1);
  const base=changed || reset ? initialState() : state;
  return {...mergeEvents(base,snapshot.events),cursor:reset||changed?Number(snapshot.cursor)||0:Math.max(Number(snapshot.cursor)||0,state.cursor),first_id:Number(snapshot.first_id)||0,instance_id:snapshot.instance_id||null,gap:state.gap||gap};
}
export function graphFor(events,runId,positions={}) {
  const byId=new Map();for(const e of events.filter(e=>e.run_id===runId)){const old=byId.get(e.node_id);byId.set(e.node_id,{...e,status:isAssignmentRecord(e)?observedStatus(e):e.status&&e.status!=='unknown'?e.status:old?.status||'unknown',parent_id:e.parent_id||old?.parent_id,data:{...old?.data,...e.data}});}
  const list=[...byId.values()];const depth=(e,seen=new Set())=>{if(!e.parent_id||!byId.has(e.parent_id)||seen.has(e.node_id))return 0;seen.add(e.node_id);return 1+depth(byId.get(e.parent_id),seen);};
  const rowHeight=list.some(isAssignmentRecord)?255:185;
  const lanes=new Map(); const nodes=list.map(e=>{const level=Math.min(8,depth(e));const row=lanes.get(level)||0;lanes.set(level,row+1);return{id:e.node_id,type:'operation',position:positions[e.node_id]||{x:level*320,y:row*rowHeight},data:{event:e}};});
  const edges=list.filter(e=>e.parent_id&&byId.has(e.parent_id)).map(e=>({id:e.parent_id+'→'+e.node_id,source:e.parent_id,target:e.node_id,type:'smoothstep',animated:e.status==='running'&&!isAssignmentRecord(e),style:{stroke:e.status==='error'?'#ef7d84':'#617088',strokeWidth:1.5}}));return{nodes,edges};
}
export function createSSEParser(onMessage) {
  let buffer='';
  const parse=frame=>{let event='message',id='',data=[];for(const line of frame.split(/\r?\n/)){if(line.startsWith(':'))continue;const colon=line.indexOf(':');const field=colon<0?line:line.slice(0,colon);const value=colon<0?'':line.slice(colon+1).replace(/^ /,'');if(field==='event')event=value;else if(field==='id')id=value;else if(field==='data')data.push(value);}if(data.length)onMessage({event,id,data:data.join('\n')});};
  return {push(chunk){buffer+=chunk;let m;while((m=/\r?\n\r?\n/.exec(buffer))){parse(buffer.slice(0,m.index));buffer=buffer.slice(m.index+m[0].length);}if(buffer.length>1048576)throw new Error('Stream frame too large');},end(){buffer='';}};
}

export function prunePositions(positions,events){const retained=new Set(events.map(e=>e.node_id));return Object.fromEntries(Object.entries(positions).filter(([id])=>retained.has(id)));}

export function reconcileNodes(previous,incoming){const existing=new Map(previous.map(n=>[n.id,n]));return incoming.map(n=>({...existing.get(n.id),...n}));}

export function isAssignmentRecord(event){return event?.data?.source==='flightops'||event?.data?.visibility==='assignment_record'||event?.kind?.startsWith('assignment.');}
export function sourceOf(event){return isAssignmentRecord(event)?'flightops':event?.data?.source==='omniroute'?'omniroute':'jarvis';}
export function filterEvents(events,source='all'){return source==='all'?events:events.filter(e=>sourceOf(e)===source);}
export function observedStatus(event){return isAssignmentRecord(event)&&event.status==='running'?'unknown':event.status||'unknown';}
export function buildRuns(events){const runs=new Map();for(const e of events){const old=runs.get(e.run_id),root=!e.parent_id||e.kind?.startsWith('run.'),title=e.data?.label||e.data?.task_id||e.kind||'Untitled observation';runs.set(e.run_id,{id:e.run_id,at:e.at,status:root?observedStatus(e):old?.status||observedStatus(e),label:root?title:old?.label||title,source:root?sourceOf(e):old?.source||sourceOf(e),recorded:root?isAssignmentRecord(e):old?.recorded||isAssignmentRecord(e)});}return[...runs.values()].reverse();}
