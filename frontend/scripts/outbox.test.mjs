import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const code = ts.transpileModule(readFileSync(new URL('../src/api/outbox.ts',import.meta.url),'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText
class Storage {
  data = new Map()
  getItem(key) {return this.data.get(key) ?? null}
  setItem(key,value) {this.data.set(key,String(value))}
}
class ApiError extends Error {constructor(status,msg='API error'){super(msg);this.status=status}}
function harness(send=async () => ({})) {
  const local=new Storage(), session=new Storage(), exports={}
  session.setItem('session',JSON.stringify({role:'owner',shop_id:1}))
  const api={ApiError,SESSION_KEY:'session',confirmCaptureRaw:send}
  new Function('require','exports','localStorage','sessionStorage','window','Event',code)(() => api,exports,local,session,{dispatchEvent(){}},Event)
  return {api:exports,local,session,entries:() => JSON.parse(local.getItem('shelfloop_outbox') ?? '[]')}
}
const entry={capture_id:7,edits:[{index:0,product_id:1,qty:3,unit:'pack',kind:'stock_update'}],idem_key:'retry-key'}
test('identical enqueue is deduplicated and successful replay removes only that owner entry',async () => {
  let calls=0;const h=harness(async () => {calls++})
  h.api.enqueueOutbox(entry);h.api.enqueueOutbox(entry)
  assert.equal(h.entries().length,1)
  assert.equal(await h.api.flushOutbox(),1);assert.equal(calls,1);assert.equal(h.entries().length,0)
})
test('a different owner cannot replay a queued confirmation',async () => {
  let calls=0;const h=harness(async () => {calls++})
  h.api.enqueueOutbox(entry);h.session.setItem('session',JSON.stringify({role:'owner',shop_id:2}))
  assert.equal(await h.api.flushOutbox(),0);assert.equal(calls,0);assert.equal(h.entries().length,1)
})
test('network failures and server errors preserve pending work',async () => {
  for(const error of [new TypeError('network'),new ApiError(503)]) {
    const h=harness(async () => {throw error});h.api.enqueueOutbox(entry)
    assert.equal(await h.api.flushOutbox(),0);assert.equal(h.entries().length,1)
  }
})
test('permanent conflicts retain the body and surface the reason',async () => {
  const h=harness(async () => {throw new ApiError(409,'stock changed')});h.api.enqueueOutbox(entry)
  await h.api.flushOutbox();assert.equal(h.entries()[0].error,'stock changed');assert.deepEqual(h.entries()[0].edits,entry.edits)
})
test('concurrent flushes share one request',async () => {
  let calls=0;const h=harness(async () => {calls++;await new Promise(r=>setTimeout(r,5))})
  h.api.enqueueOutbox(entry);await Promise.all([h.api.flushOutbox(),h.api.flushOutbox()]);assert.equal(calls,1)
})
test('a new draft queued during replay is not overwritten',async () => {
  let h;h=harness(async () => h.api.enqueueOutbox({...entry,idem_key:'new',capture_id:8}))
  h.api.enqueueOutbox(entry);await h.api.flushOutbox();assert.equal(h.entries().length,1);assert.equal(h.entries()[0].capture_id,8)
})
test('storage failure is reported instead of pretending to save',() => {
  const h=harness();h.local.setItem=()=>{throw new Error('quota')}
  assert.throws(()=>h.api.enqueueOutbox(entry),/quota/)
})
