/** Opt-in response release guard for apps consuming customer-signed evidence.
 *  The model's raw output stays local; the registry only receives its SHA-256.
 *  This is not an answer-semantic checker or universal model enforcement.
 */
export type UseCheckReceipt={
 schema:'qualityrag.protected-decision-use/v1';
 permission:'PERMIT_SIGNED_ASSERTION_USE';
 decisionId:string;requestId:string;answerSha256:string;
 policySha256:string;checkedAt:string;at:string;
 receiptId:string;chainHash:string;
 globalEnforcement:false;answerSemanticsVerified:false;
 independentPublisherVerified:false;externallyAnchored:false;
 scope:'THIS_REGISTRY_CHECK_ONLY'
};
const UUID=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const ID=/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
const HEX=/^[a-f0-9]{64}$/;

function endpoint(value:string):string {
 if(typeof value!=='string'||value.includes('\\')||
   /[\u0000-\u0020\u007f]/.test(value)||
   !/^[a-z][a-z0-9+.-]*:\/\/[^/?#]/i.test(value))
   throw Error('Protected use requires trusted HTTPS or loopback registry URL');
 const url=new URL(value);
 if(!['https:','http:'].includes(url.protocol)||!url.hostname||
   url.username||url.password||url.search||url.hash||
   (url.protocol==='http:'&&url.hostname!=='127.0.0.1')||
   url.port==='0')
   throw Error('Protected use requires trusted HTTPS or loopback registry URL');
 return url.toString().replace(/\/$/,'');
}
export class ProtectedUseClient {
 private base:string;
 private bearer:string;
 constructor(registryUrl:string,ownerToken:string){
   this.base=endpoint(registryUrl);
   if(typeof ownerToken!=='string'||ownerToken.length<4||ownerToken.length>10000||
      /[\u0000-\u001f\u007f]/.test(ownerToken))
     throw Error('A signed scoped owner token is required');
   this.bearer=ownerToken;
 }
 /** The only path this helper exposes. Never return answer content on refusal. */
 async releaseAnswer(decisionId:string,requestId:string,answer:string):Promise<{
   answer:string;receipt:UseCheckReceipt
 }>{
   if(typeof decisionId!=='string'||!UUID.test(decisionId)||
      typeof requestId!=='string'||!ID.test(requestId)||
      typeof answer!=='string'||!answer.trim()||
      new TextEncoder().encode(answer).length>128000)
     throw Error('Invalid protected answer request');
   const bytes=new TextEncoder().encode(answer);
   const digest=await crypto.subtle.digest('SHA-256',bytes);
   const answerSha256=Array.from(new Uint8Array(digest))
     .map(x=>x.toString(16).padStart(2,'0')).join('');
   const response=await fetch(this.base+'/v1/evidence/protected-decisions/'+
      decisionId+'/use-check',{
     method:'POST',cache:'no-store',redirect:'error',
     headers:{Authorization:'Bearer '+this.bearer,'Content-Type':'application/json'},
     body:JSON.stringify({requestId,answerSha256}),
     signal:AbortSignal.timeout(10000)
   });
   let receipt:Partial<UseCheckReceipt>|null=null;
   try{receipt=await response.json() as Partial<UseCheckReceipt>}
   catch{throw Error('Protected evidence use refused: invalid registry response')}
   if(!response.ok)throw Error('Protected evidence use refused');
   if(!receipt||receipt.schema!=='qualityrag.protected-decision-use/v1'||
     receipt.permission!=='PERMIT_SIGNED_ASSERTION_USE'||
     receipt.decisionId!==decisionId||receipt.requestId!==requestId||
     receipt.answerSha256!==answerSha256||!HEX.test(receipt.policySha256||'')||
     !UUID.test(receipt.receiptId||'')||!HEX.test(receipt.chainHash||'')||
     receipt.globalEnforcement!==false||receipt.answerSemanticsVerified!==false||
     receipt.independentPublisherVerified!==false||
     receipt.externallyAnchored!==false||
     receipt.scope!=='THIS_REGISTRY_CHECK_ONLY')
     throw Error('Protected evidence use refused: malformed or mismatched permit');
   return {answer,receipt:receipt as UseCheckReceipt};
 }
}
