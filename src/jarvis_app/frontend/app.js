"use strict";
/* Jarvis dashboard: shows only real server state (/api/state, /api/conversation, /api/audit). */
const TOKEN = document.querySelector('meta[name="jarvis-token"]').content;
const $ = s => document.querySelector(s);
const el = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) { if (k.startsWith("on")) e.addEventListener(k.slice(2), v); else if (v !== null && v !== undefined) e.setAttribute(k, v); }
  for (const k of kids.flat()) if (k !== null && k !== undefined) e.append(k.nodeType ? k : String(k)); return e; };
const CONV = "default";
let busy = false;

async function api(path, opts = {}) {
  const r = await fetch(path, {...opts, headers: {"Content-Type": "application/json", "X-Jarvis-Token": TOKEN, ...(opts.headers || {})}});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || ("HTTP " + r.status));
  return j;
}
function toast(t) { const e = $("#toast"); e.textContent = t; e.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => e.classList.remove("show"), 3500); }
function setState(st) { $("#orb").dataset.st = st; $("#stateChip").textContent = st; }

function renderMessages(msgs) {
  const box = $("#msgs"); const atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
  box.replaceChildren();
  if (!msgs.length) box.append(el("p", {class: "empty"}, "Say hello, ask the time, or ask about the FlightOps project."));
  for (const m of msgs) {
    if (m.role === "assistant" && !m.content && m.meta.tool_calls) {
      box.append(el("div", {class: "m tool"}, el("small", {}, "tool call"), m.meta.tool_calls.map(t => `${t.name}(${JSON.stringify(t.args)})`).join("\n"))); continue; }
    const who = m.role === "user" ? "You" : m.role === "tool" ? `tool result · ${m.meta.name || ""}` : `Jarvis${m.meta.model ? " · " + m.meta.model : ""}`;
    box.append(el("div", {class: "m " + m.role}, el("small", {}, who + " · " + new Date(m.at).toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"})), m.content));
  }
  if (atEnd) box.scrollTop = box.scrollHeight;
}

function renderState(s) {
  if (!busy) setState(s.agent_state);
  const sel = $("#modelSel"); sel.replaceChildren(...s.models.map(m => el("option", {value: m.key, selected: m.active ? "" : null}, m.label)));
  $("#models").replaceChildren(...s.models.map(m => el("div", {class: "item"},
    el("div", {class: "l"}, el("b", {}, m.label + (m.active ? " ✓" : "")), el("div", {class: "muted"}, `${m.provider}: ${m.model} · key: ${m.credential}`),
      m.last_check ? el("div", {class: m.last_check.ok ? "ok" : "bad"}, (m.last_check.ok ? "reachable " : "failed: ") + m.last_check.detail) : el("div", {class: "muted"}, "not checked yet")),
    el("button", {class: "btn ghost small", type: "button", onclick: () => check(m.key)}, "Check"))));
  $("#perms").replaceChildren(...Object.entries(s.permissions).map(([p, on]) => el("label", {class: "item"},
    el("span", {class: "l"}, p), el("input", {type: "checkbox", checked: on ? "" : null, onchange: e => setPerm(p, e.target.checked)}))));
  $("#tools").replaceChildren(...s.tools.map(t => el("div", {class: "item"}, el("span", {class: "l"}, el("b", {}, t.name), el("div", {class: "muted"}, t.description)),
    el("span", {class: t.confirm ? "warn" : "muted"}, t.confirm ? "asks first" : "read"))));
  $("#integrations").replaceChildren(...s.integrations.map(i => el("div", {class: "item"}, el("span", {class: "l"}, i.name), el("span", {class: "muted"}, i.status))));
  $("#memory").replaceChildren(el("div", {class: "muted"}, s.memory_enabled ? `${s.memory_count} item(s) stored` : "memory switched off"));
  renderPending(s.pending);
}

function renderPending(list) {
  const box = $("#pending"); box.replaceChildren();
  for (const p of list) box.append(el("div", {}, el("b", {}, "Confirm: "), `${p.tool} ${JSON.stringify(p.args)}`,
    el("div", {class: "row"}, el("button", {class: "btn small", type: "button", onclick: () => confirmAct(p.id, true)}, "Approve"),
      el("button", {class: "btn ghost small", type: "button", onclick: () => confirmAct(p.id, false)}, "Decline"))));
}

async function loadAudit() {
  const a = await api("/api/audit?limit=12");
  $("#audit").replaceChildren(...(a.length ? a.map(x => el("div", {class: "item"}, el("span", {class: "l"}, el("b", {}, x.tool), el("div", {class: "muted"}, x.args_summary || "")),
    el("span", {class: x.status === "ok" ? "ok" : x.status === "awaiting_confirmation" ? "warn" : "bad"}, x.status))) : [el("div", {class: "muted"}, "No tool calls yet.")]));
}

async function refresh() {
  try { const [s, msgs] = await Promise.all([api("/api/state"), api("/api/conversation?conv=" + CONV)]); renderState(s); renderMessages(msgs); loadAudit(); }
  catch (e) { setState("offline"); }
}

async function send(text) {
  if (busy || !text.trim()) return; voice.stopSpeaking(); busy = true; setState("thinking"); $("#sendBtn").disabled = true;
  try { const r = await api("/api/chat", {method: "POST", body: JSON.stringify({text, conv: CONV})}); $("#input").value = ""; if (r.error) toast(r.error); voice.speak(r.reply); }
  catch (e) { toast("Not sent: " + e.message); }
  finally { busy = false; $("#sendBtn").disabled = false; await refresh(); }
}
async function confirmAct(id, approve) {
  if (busy) return;
  voice.stopSpeaking(); busy = true; setState("executing");
  try { const r = await api("/api/confirm", {method: "POST", body: JSON.stringify({id, approve})}); if (r.error) toast(r.error); voice.speak(r.reply); }
  catch (e) { toast(e.message); } finally { busy = false; await refresh(); }
}
async function check(key) { toast("Checking " + key + "…"); try { const r = await api("/api/model/validate", {method: "POST", body: JSON.stringify({name: key})}); toast(r.ok ? "Reachable" : "Failed: " + r.detail); } catch (e) { toast(e.message); } refresh(); }
async function setPerm(p, on) { try { await api("/api/permissions", {method: "POST", body: JSON.stringify({permission: p, enabled: on})}); } catch (e) { toast(e.message); } refresh(); }

const voice = createJarvisVoice({env: window, mic: $("#micBtn"), mute: $("#muteBtn"), stop: $("#stopSpeakingBtn"),
  status: $("#voiceStatus"), input: $("#input"), submit: send, isBusy: () => busy});
$("#form").addEventListener("submit", e => { e.preventDefault(); send($("#input").value); });
$("#modelSel").addEventListener("change", async e => { setState("thinking"); try { const r = await api("/api/model", {method: "POST", body: JSON.stringify({name: e.target.value})}); toast(r.message); } catch (err) { toast(err.message); } refresh(); });
$("#stopBtn").addEventListener("click", async () => { try { await api("/api/stop", {method: "POST"}); toast("Stop requested"); } catch (e) { toast(e.message); } });
refresh(); setInterval(() => { if (!busy) refresh(); }, 4000);
