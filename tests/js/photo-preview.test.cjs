const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs"), vm = require("node:vm");
const source = fs.readFileSync(`${__dirname}/../../static/js/reports/photo-preview.js`, "utf8");
function page(fetch) {
  const handlers = {}, events = {}, revoked = [], used = [];
  const input = {files:[], addEventListener(name, fn) { handlers[name] = fn; }};
  const img = {hidden:true, removeAttribute() { delete this.src; }, addEventListener(name, fn) {events[name]=fn;}};
  const box = {dataset:{previewUrl:"/report/photo-preview/"},setAttribute(k,v) {this[k]=v;}}, status={textContent:""};
  const form = {elements:{photo:input,csrfmiddlewaretoken:{value:"csrf"}}};
  const doc={getElementById:(id)=>({"report-form":form,"report-photo-preview":box,"report-preview-image":img,"report-preview-status":status}[id])};
  const context={module:{exports:{}}, fetch, AbortController, FormData:class {append() {}},
    URL:{createObjectURL(blob){used.push(blob); return `blob:${used.length}`;},revokeObjectURL(url){revoked.push(url);}},
    addEventListener(name,fn){events[name]=fn;}};
  vm.runInNewContext(source,context); const api=context.module.exports;
  api.init(doc); return {api,input,img,box,status,handlers,events,revoked,used};
}
const file=(name="sample.heic")=>({name,size:1024,type:name.endsWith("jpg")?"image/jpeg":"image/heic"});
const response=()=>({ok:true,headers:{get:()=>"image/jpeg"},blob:async()=>({converted:true})});
test("HEIC/HEIF extension and MIME detection",()=>{
  const p=page(); assert.equal(p.api.isHeic({name:"A.HEIF"}),true); assert.equal(p.api.isHeic({name:"",type:"image/heic"}),true);
  assert.equal(p.api.isHeic(file("a.jpg")),false);
});
test("HEIC loading then converted preview preserves original and sends CSRF",async()=>{
  let request; const p=page(async(url,options)=>{request={url,options};return response();});
  const original=file(); p.input.files=[original]; const job=p.handlers.change(); assert.equal(p.box['aria-busy'],"true");
  await job; assert.equal(p.img.hidden,false); assert.equal(p.input.files[0],original); assert.equal(p.used[0].converted,true);
  assert.equal(request.options.headers['X-CSRFToken'],"csrf"); assert.equal(request.options.credentials,"same-origin");
});
test("JPEG uses local URL without server request and clears previous URL",async()=>{
  const p=page(()=>{throw new Error("unexpected fetch");}); p.input.files=[file("a.jpg")]; await p.handlers.change();
  p.input.files=[file("b.jpg")];await p.handlers.change(); assert.deepEqual(p.revoked,["blob:1"]); assert.equal(p.img.src,"blob:2");
});
test("late conversion cannot replace a reselected JPEG",async()=>{
  let resolve; const p=page(()=>new Promise(r=>resolve=r));p.input.files=[file()];const old=p.handlers.change();
  p.input.files=[file("new.jpg")];await p.handlers.change();resolve(response());await old;
  assert.equal(p.used.length,1);assert.equal(p.used[0].name,"new.jpg");
});
test("failure gives explicit notice; selecting again recovers",async()=>{
  let failed=true; const p=page(async()=>{if(failed)throw new Error();return response();});p.input.files=[file()];await p.handlers.change();
  assert.equal(p.img.hidden,true);assert.match(p.status.textContent,/불러오지 못/);assert.equal(p.box['aria-busy'],"false");
  failed=false;await p.handlers.change();assert.equal(p.img.hidden,false);assert.equal(p.status.textContent,"");
});
test("empty selection, oversized file and non-image response remain safe",async()=>{
  const p=page(async()=>({ok:true,headers:{get:()=>"text/html"}}));await p.handlers.change();
  p.input.files=[{...file(),size:11*1024*1024}];await p.handlers.change();assert.match(p.status.textContent,/10MB/);
  p.input.files=[file()];await p.handlers.change();assert.equal(p.img.hidden,true);assert.match(p.status.textContent,/불러오지 못/);
});
test("bfcache keeps URL while leaving permanently revokes it",async()=>{
  const p=page();p.input.files=[file("a.jpg")];await p.handlers.change();p.events.pagehide({persisted:true});assert.equal(p.revoked.length,0);
  p.events.pagehide({persisted:false});assert.deepEqual(p.revoked,["blob:1"]);
});
