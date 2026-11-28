import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {SCHEMA,questionTargetDigest,questionReviewBytes} from '../src/guided-question-review.js';
// Independent Python serialization oracle: valid Unicode only, no normalization.
const oracle=String.raw`
import sys,json,hashlib
x=json.load(sys.stdin)
def compact(v): return json.dumps(v,ensure_ascii=False,separators=(',',':')).encode('utf-8')
def sha(b): return hashlib.sha256(b).hexdigest()
t=x['target']; s=t['source']; c=t['concept']; e=t['evidence']
units=s['text'].encode('utf-16-le')
def span(a):
 start,end=a['start'],a['end']
 assert units[2*start:2*end].decode('utf-16-le')==a['quote']
 return [start,end,a['quote']]
q=e.get('questionTarget')
args=None if q is None else [[a['role'],*span(a)] for a in q['arguments']]
r=t.get('relation')
rel=None if r is None else [r['id'],r['type'],span(r['from']),span(r['cue']),span(r['to'])]
schema='qualityrag.guided-question-review/v1'
target=sha(compact(['qualityrag.guided-question-target/v2',t['ownerBinding'],t['service'],t['environment'],t['policyDigest'],s['id'],s['revision'],sha(s['text'].encode('utf-8')),c['id'],c['revision'],c['label'],t['goalId'],e['id'],e['obligationId'],e['kind'],e['consequence'],t['operatorId'],span(e),args,rel,e['proposedPremise']]))
p=x['payload']
keys=['schema','ownerBinding','service','environment','policyDigest','targetDigest','nonce','issuedAt','expiresAt','decision','reviewerId']
review=b'QUALITYRAG/'+schema.encode('ascii')+b'\x00'+compact([p[k] for k in keys])
print(json.dumps({'target':target,'review':sha(review)}))
`;
function fixture(text){
 const source={id:'source',revision:'r1',text};
 const concept={id:'c',revision:'r1',label:'Concept é'};
 const evidence={proposedPremise:'The source describes a condition to investigate.',id:'e',obligationId:'o',kind:'boundary',consequence:'Preserve condition',sourceId:source.id,revision:source.revision,conceptId:concept.id,semanticRevision:concept.revision,start:0,end:text.length,quote:text};
 return {ownerBinding:'a'.repeat(64),service:'lexyread',environment:'test',policyDigest:'b'.repeat(64),source,concept,evidence,goalId:'g',operatorId:'boundary'};
}
test('Python and JavaScript agree on Unicode target and signed payload digests',()=>{
 for(const text of ['ASCII','capacité','A😀B','e\u0301','漢字','A\r\nB\t"\\','\u2028\u2029']){
  const target=fixture(text);
  const payload={schema:SCHEMA,ownerBinding:target.ownerBinding,service:target.service,environment:target.environment,policyDigest:target.policyDigest,targetDigest:questionTargetDigest(target),nonce:'fixture-nonce-0001',issuedAt:1800000000000,expiresAt:1800000001000,decision:'ADMIT',reviewerId:'reviewer'};
  const out=JSON.parse(execFileSync('python3',['-c',oracle],{input:JSON.stringify({target,payload}),encoding:'utf8',timeout:5000}));
  assert.equal(out.target,payload.targetDigest);
  assert.equal(out.review,createHash('sha256').update(questionReviewBytes(payload)).digest('hex'));
 }
});
test('UTF-16 spans preserve supplementary characters and reject split pairs',()=>{
 const target=fixture('A😀B');
 target.evidence.questionTarget={operatorId:'boundary',obligationId:'o',arguments:[{role:'condition',start:1,end:3,quote:'😀'}]};
 assert.match(questionTargetDigest(target),/^[a-f0-9]{64}$/);
 target.evidence.questionTarget.arguments[0]={role:'condition',start:1,end:2,quote:'\ud83d'};
 assert.throws(()=>questionTargetDigest(target));
 assert.throws(()=>questionTargetDigest(fixture('bad\ud800')));
 assert.notEqual(questionTargetDigest(fixture('é')),questionTargetDigest(fixture('e\u0301')));
});
