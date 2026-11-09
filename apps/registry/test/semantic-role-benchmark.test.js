import test from 'node:test';
import assert from 'node:assert/strict';
import {scanRelationshipConflicts} from '../src/cross-document-relations.js';

// Research challenge corpus, NOT an independently validated benchmark.
// "Expected" means the grammar should raise an investigation candidate,
// not that two claims have a proven logical contradiction.
const id=n=>'google_drive/'+n.toString(16).padStart(32,'0');
const cases=[
 {name:'direct role reversal',a:'The insurer pays the hospital.',b:'The hospital pays the insurer.',expected:true,kind:'INVERSE_PAYER_PAYEE'},
 {name:'receipt reverse role',a:'The insurer must pay the hospital.',b:'The insurer receives payment from the hospital.',expected:true,kind:'INVERSE_PAYER_PAYEE'},
 {name:'required/prohibited polarity',a:'The insurer pays the hospital.',b:'Payment from insurer to hospital is prohibited.',expected:true,kind:'POLARITY_CONFLICT'},
 {name:'negated direct payment',a:'The insurer must pay the hospital.',b:'The insurer must not pay the hospital.',expected:true,kind:'POLARITY_CONFLICT'},
 {name:'receive and pay equivalent',a:'The insurer pays the hospital.',b:'The hospital receives payment from the insurer.',expected:false},
 {name:'required and pay equivalent',a:'The insurer pays the hospital.',b:'Payment from insurer to hospital is required.',expected:false},
 {name:'distinct payees',a:'The insurer pays the hospital.',b:'The insurer pays the vendor.',expected:false},
 {name:'distinct payer',a:'The insurer pays the hospital.',b:'The vendor pays the hospital.',expected:false},
 {name:'unsupported transfer paraphrase negative',a:'The insurer transfers funds to the hospital.',b:'The hospital transfers funds to the insurer.',expected:false,unsupported:true},
 {name:'unsupported condition negative',a:'The insurer pays the hospital.',b:'The insurer pays the hospital unless suspended.',expected:false,unsupported:true},
 {name:'unsupported two-word organizations negative',a:'The health insurer pays the city hospital.',b:'The city hospital pays the health insurer.',expected:false,unsupported:true},
 {name:'unsupported passive voice negative',a:'The insurer pays the hospital.',b:'The hospital is paid by the insurer.',expected:false,unsupported:true}
];
const witness={sourceId:id(1),lineNumber:1,status:'SUPPORTS'};
const results=cases.map(item=>{
 const graph=scanRelationshipConflicts({
   sources:[{sourceId:id(1),lines:[item.a]},{sourceId:id(2),lines:[item.b]}],
   witnesses:[witness]
 });
 return {...item,observed:graph.candidateCount>0,
   observedKind:graph.findings[0]?.category??null,
   hasNoCompletenessClaim:graph.semanticCompletenessVerified===false&&
     graph.crossFileSemanticEntailmentVerified===false&&
     graph.supportedPatternCoverageOnly===true,
   metadataOnly:!JSON.stringify(graph).includes('insurer')&&
     !JSON.stringify(graph).includes('hospital')};
});
const positives=results.filter(x=>x.expected);
const supportedNegatives=results.filter(x=>!x.expected&&!x.unsupported);
const supportedRecall=positives.filter(x=>x.observed).length/positives.length;
const supportedFalseBlockRate=supportedNegatives.filter(x=>x.observed).length/supportedNegatives.length;
const unsupported=results.filter(x=>x.unsupported);
const unsupportedMisses=unsupported.filter(x=>!x.observed).length;

test('bounded payment role benchmark: supported candidate recall',()=>{
 assert.equal(supportedRecall,1,
   'Every supported consequential relationship change should yield a challenge');
 for(const c of positives)assert.equal(c.observedKind,c.kind,c.name);
});
test('bounded payment role benchmark: no false blocks on supported harmless pairs',()=>{
 assert.equal(supportedFalseBlockRate,0);
});
test('bounded payment role benchmark: negative results remain explicitly visible',()=>{
 assert.equal(unsupportedMisses,unsupported.length,
   'Unexpected recognition of unsupported phrase requires benchmark review');
 assert.ok(results.every(x=>x.hasNoCompletenessClaim&&x.metadataOnly));
});
test('benchmark corpus is non-degenerate and has both positives and negatives',()=>{
 assert.equal(cases.length,12);
 assert.equal(positives.length,4);
 assert.equal(supportedNegatives.length,4);
 assert.equal(unsupported.length,4);
});
