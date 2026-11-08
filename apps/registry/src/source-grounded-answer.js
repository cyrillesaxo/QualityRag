// Bounded extractive response assembly, not general-language entailment.
// Only signed SUPPORTS anchors from the current approved PackSpec are quoted.
// Nearby source lines are shown as *unreviewed context*, never silently dropped.
import {createHash} from 'node:crypto';
const sha=text=>createHash('sha256').update(text,'utf8').digest('hex');
const validId=/^[A-Za-z0-9._-]{1,128}$/;
function require_(okay,code){if(!okay)throw Error(code)}
export function buildSourceGroundedAnswer({policy,witnesses,verifiedLines}){
 require_(policy&&Array.isArray(policy.requirements)&&policy.requirements.length>0&&
   policy.requirements.length<=8&&Array.isArray(witnesses)&&
   witnesses.length>0&&witnesses.length<=8&&Array.isArray(verifiedLines)&&
   verifiedLines.length===witnesses.length,'PROTECTED_GROUNDED_COVERAGE_INVALID');
 const ids=policy.requirements.map(x=>x.id);
 require_(ids.every(x=>typeof x==='string'&&validId.test(x))&&
   new Set(ids).size===ids.length,'PROTECTED_GROUNDED_COVERAGE_INVALID');
 require_(witnesses.every(w=>w.status==='SUPPORTS')&&
   ids.every(id=>witnesses.some(w=>w.requirementId===id)),
   'PROTECTED_GROUNDED_REVIEW_INCOMPLETE');
 const expected=new Map(witnesses.map(w=>[
   w.requirementId+':'+w.sourceId+':'+w.lineNumber,w
 ]));
 require_(expected.size===witnesses.length,'PROTECTED_GROUNDED_COVERAGE_INVALID');
 const seen=new Set();
 const snippets=[];
 for(const source of verifiedLines){
   const key=source.requirementId+':'+source.sourceId+':'+source.lineNumber;
   const signed=expected.get(key);
   require_(signed&&!seen.has(key),'PROTECTED_GROUNDED_UNAPPROVED_ANCHOR');
   seen.add(key);
   require_(source.lineSha256===signed.lineSha256&&
     typeof source.text==='string'&&
     sha(source.text)===signed.lineSha256&&
     Array.isArray(source.context)&&source.context.length<=2,
     'PROTECTED_GROUNDED_SOURCE_CHANGED');
   for(const context of source.context){
     require_(Number.isSafeInteger(context.lineNumber)&&
       Math.abs(context.lineNumber-source.lineNumber)===1&&
       typeof context.text==='string'&&context.text.length<=1200,
       'PROTECTED_GROUNDED_CONTEXT_INVALID');
   }
   snippets.push({
     requirementId:signed.requirementId,
     sourceId:signed.sourceId,
     lineNumber:signed.lineNumber,
     reviewedStatus:'HUMAN_SIGNED_SUPPORTS',
     exactSourceLine:source.text,
     adjacentContext:source.context.map(c=>({
       lineNumber:c.lineNumber,text:c.text,
       semantics:'UNREVIEWED_ADJACENT_CONTEXT'
     }))
   });
 }
 require_(seen.size===expected.size,'PROTECTED_GROUNDED_COVERAGE_INVALID');
 const chunks=['Source-grounded extract — not a complete policy interpretation.'];
 const ordered=[];
 for(const id of ids){
   chunks.push('Requirement: '+id);
   const matches=snippets.filter(x=>x.requirementId===id)
     .sort((a,b)=>a.sourceId.localeCompare(b.sourceId)||a.lineNumber-b.lineNumber);
   for(const m of matches){
     chunks.push('  Human-reviewed source line ['+m.sourceId+
       ', line '+m.lineNumber+']: '+m.exactSourceLine);
     for(const c of m.adjacentContext)
       chunks.push('  Adjacent, not-reviewed context [line '+c.lineNumber+']: '+c.text);
     ordered.push(m);
   }
 }
 chunks.push('Coverage warning: unreviewed passages may contain other exceptions, '+
   'conditions or contradictions. This extract does not establish complete meaning.');
 const answer=chunks.join('\n');
 require_(Buffer.byteLength(answer,'utf8')<=16384,'PROTECTED_GROUNDED_OUTPUT_TOO_LARGE');
 return {
   schema:'qualityrag.source-grounded-extract/v1',
   answer,sections:ordered,
   coverage:{requiredPolicyObligations:ids.length,
     humanSignedSupports:ordered.length,
     allSignedAnchorsIncluded:true,
     adjacentContextWindowLines:1,
     fullDocumentExaminedForExceptions:false},
   assertions:{exactLinesRevalidated:true,
     humanReviewedAnchorSemantics:true,
     modelGeneratedParaphrase:false,
     freeFormAnswerEntailmentVerified:false,
     documentWideCompletenessVerified:false,
     independentPublisherVerified:false}
 };
}
