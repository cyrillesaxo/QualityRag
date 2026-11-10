import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {EvidenceLedger} from '../src/evidence-ledger.js';

const sha=x=>createHash('sha256').update(x).digest('hex');
test('US-066 exact requestId reconciliation reads append-only owner-scoped use event',()=>{
 const directory=mkdtempSync(join(tmpdir(),'qr-use-audit-'));
 try{
   const ledger=new EvidenceLedger(join(directory,'events.jsonl'));
   const id=randomUUID(),actor='issuer#owner',requestId='delivery-'+randomUUID();
   const policySha256=sha('policy');
   const decision=ledger.append({
     id,type:'protected-decision',serviceId:'claims',environment:'staging',
     actorHash:sha(actor),policySha256,result:{verdict:'ADMIT'}
   });
   const missing=ledger.protectedUseStatusForOwner(id,actor,requestId);
   assert.equal(missing.state,'NOT_RECORDED_AT_CHECK_TIME');
   assert.equal(missing.retryAuthorized,false);
   assert.equal(missing.releasePermitted,false);
   const receipt=ledger.recordProtectedUse({
     decision,actor,requestId,answerSha256:sha('private answer'),
     checkedAt:new Date().toISOString(),mode:'SOURCE_GROUNDED_EXTRACT'
   });
   const found=ledger.protectedUseStatusForOwner(id,actor,requestId);
   assert.equal(found.state,'RECORDED');
   assert.equal(found.useReceiptId,receipt.receiptId);
   assert.equal(found.answerSha256,receipt.answerSha256);
   assert.equal(found.deliveryMode,'SOURCE_GROUNDED_EXTRACT');
   assert.equal(found.retryAuthorized,false);
   assert.equal(found.currentSourceRevalidated,false);
   assert.equal(found.releasePermitted,false);
   assert.equal(JSON.stringify(found).includes('private answer'),false);
   assert.equal(ledger.protectedUseStatusForOwner(id,actor,'delivery-'+randomUUID()).state,
     'NOT_RECORDED_AT_CHECK_TIME');
   assert.throws(()=>ledger.protectedUseStatusForOwner(id,'issuer#other',requestId),
     /PROTECTED_DECISION_OWNER_FORBIDDEN/);
 }finally{rmSync(directory,{recursive:true,force:true})}
});
