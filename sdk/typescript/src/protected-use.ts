/** Opt-in response release guards for apps consuming customer-signed evidence.
 *  releaseAnswer() sends only a digest. deliverViaGateway() sends plaintext
 *  to a customer-operated registry that buffers it until admission succeeds.
 *  Neither route checks answer semantics nor controls non-integrated apps.
 */
export type UseCheckReceipt={
 schema:'qualityrag.protected-decision-use/v1';
 permission:'PERMIT_SIGNED_ASSERTION_USE';
 decisionId:string;requestId:string;answerSha256:string;
 policySha256:string;checkedAt:string;at:string;
 receiptId:string;chainHash:string;
 deliveryMode?:'DIGEST_ONLY_CLIENT_RELEASE'|'SERVER_BUFFERED_RELEASE'|
   'SOURCE_GROUNDED_EXTRACT';
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
export type SourceGroundedExtract={
 schema:'qualityrag.source-grounded-extract/v1';
 answer:string;
 sections:Array<{
   requirementId:string;sourceId:string;lineNumber:number;
   reviewedStatus:'HUMAN_SIGNED_SUPPORTS';exactSourceLine:string;
   adjacentContext:Array<{lineNumber:number;text:string;semantics:'UNREVIEWED_ADJACENT_CONTEXT'}>
 }>;
 coverage:{requiredPolicyObligations:number;humanSignedSupports:number;
   allSignedAnchorsIncluded:true;adjacentContextWindowLines:1;
   fullDocumentExaminedForExceptions:false};
 assertions:{exactLinesRevalidated:true;humanReviewedAnchorSemantics:true;
   modelGeneratedParaphrase:false;freeFormAnswerEntailmentVerified:false;
   documentWideCompletenessVerified:false;independentPublisherVerified:false};
 receipt:UseCheckReceipt;delivery:'SERVER_GENERATED_EXTRACT_ONLY';
 answerSemanticsVerified:false;globalEnforcement:false;externallyAnchored:false;
};
export type CrossDocumentRelationReport={
 schema:'qualityrag.cross-document-relation-candidates/v1';
 status:'POTENTIAL_CROSS_SOURCE_CONFLICTS'|'NO_SUPPORTED_RELATION_CONFLICTS_FOUND';
 candidateCount:number;findingsTruncated:boolean;bothSignedConflicts:number;
 sourcesScanned:number;linesScanned:number;relationEdgesParsed:number;
 findings:Array<{
   category:'INVERSE_PAYER_PAYEE'|'POLARITY_CONFLICT';
   left:{sourceId:string;lineNumber:number;signedSupportingWitness:boolean};
   right:{sourceId:string;lineNumber:number;signedSupportingWitness:boolean};
   reviewState:'NEEDS_EXPLICIT_CROSS_SOURCE_ADJUDICATION';
 }>;
 scope:'LIVE_VERIFIED_INCLUDED_SELECTED_FOLDER_TEXT_FILES';
 sourceTextIncluded:false;actorNamesIncluded:false;
 crossFileSemanticEntailmentVerified:false;
 authoritativenessVerified:false;semanticCompletenessVerified:false;
 supportedPatternCoverageOnly:true;
 decisionId:string;checkedAt:string;releasePermittedByThisPreview:false;
 nextAction:string;
};
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
 /** Stronger server-side output ownership: registry receives and temporarily
  *  buffers the draft. Use only on a customer-operated trusted endpoint;
  *  the registry must never log answer text. Fail closed on any mismatch.
  */
 async deliverViaGateway(decisionId:string,requestId:string,answer:string):Promise<{
   answer:string;receipt:UseCheckReceipt;delivery:'BUFFERED_SINGLE_RESPONSE'
 }>{
   if(typeof decisionId!=='string'||!UUID.test(decisionId)||
      typeof requestId!=='string'||!ID.test(requestId)||
      typeof answer!=='string'||!answer.trim()||
      new TextEncoder().encode(answer).length>16384||answer.includes('\0'))
     throw Error('Invalid protected gateway delivery request');
   const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(answer));
   const answerSha256=Array.from(new Uint8Array(digest))
     .map(x=>x.toString(16).padStart(2,'0')).join('');
   const response=await fetch(this.base+'/v1/evidence/protected-decisions/'+
      decisionId+'/deliver',{
     method:'POST',cache:'no-store',redirect:'error',
     headers:{Authorization:'Bearer '+this.bearer,'Content-Type':'application/json'},
     body:JSON.stringify({requestId,answer}),
     signal:AbortSignal.timeout(10000)
   });
   let result:any;
   try{
     const text=await response.text();
     if(text.length>35000)throw Error('Oversized gateway response');
     result=JSON.parse(text);
   }catch{throw Error('Protected gateway denied delivery: invalid response')}
   if(!response.ok)throw Error('Protected gateway denied delivery');
   const receipt=result?.receipt as Partial<UseCheckReceipt>|undefined;
   if(result?.schema!=='qualityrag.protected-answer-delivery/v1'||
      result.answer!==answer||result.delivery!=='BUFFERED_SINGLE_RESPONSE'||
      result.answerSemanticsVerified!==false||
      result.globalEnforcement!==false||
      result.externallyAnchored!==false||
      receipt?.schema!=='qualityrag.protected-decision-use/v1'||
      receipt.permission!=='PERMIT_SIGNED_ASSERTION_USE'||
      receipt.decisionId!==decisionId||receipt.requestId!==requestId||
      receipt.answerSha256!==answerSha256||
      receipt.deliveryMode!=='SERVER_BUFFERED_RELEASE'||
      !HEX.test(receipt.policySha256||'')||
      !UUID.test(receipt.receiptId||'')||
      !HEX.test(receipt.chainHash||'')||
      receipt.answerSemanticsVerified!==false||
      receipt.globalEnforcement!==false||
      receipt.externallyAnchored!==false||
      receipt.scope!=='THIS_REGISTRY_CHECK_ONLY')
     throw Error('Protected gateway denied delivery: mismatched permit');
   return {answer:result.answer,receipt:receipt as UseCheckReceipt,
     delivery:'BUFFERED_SINGLE_RESPONSE'};
 }
 /** The registry constructs a verbatim extract from all signed witness anchors.
  * No caller-supplied prose is allowed. Not document-wide semantic entailment.
  */
 /** Experimental WitnessGraph preview over currently included selected files.
  *  No answer authorization is granted by a clean result.
  */
 async checkCrossDocumentRelations(decisionId:string,requestId:string):
   Promise<CrossDocumentRelationReport>{
   if(typeof decisionId!=='string'||!UUID.test(decisionId)||
      typeof requestId!=='string'||!ID.test(requestId))
     throw Error('Invalid cross-document relation request');
   const response=await fetch(this.base+'/v1/evidence/protected-decisions/'+
     decisionId+'/relation-check',{
       method:'POST',cache:'no-store',redirect:'error',
       headers:{Authorization:'Bearer '+this.bearer,'Content-Type':'application/json'},
       body:JSON.stringify({requestId}),signal:AbortSignal.timeout(30000)
     });
   let report:CrossDocumentRelationReport;
   try{
     const raw=await response.text();
     if(raw.length>64000)throw Error('Oversized relation report');
     report=JSON.parse(raw) as CrossDocumentRelationReport;
   }catch{throw Error('Cross-document relation check denied: invalid response')}
   if(!response.ok)throw Error('Cross-document relation check denied');
   const expectedSource=/^google_drive\/[a-f0-9]{32}$/;
   const validAnchor=(x:{sourceId:string;lineNumber:number;
     signedSupportingWitness:boolean}|undefined)=>
       !!x&&expectedSource.test(x.sourceId)&&Number.isSafeInteger(x.lineNumber)&&
       x.lineNumber>=1&&x.lineNumber<=6000&&
       typeof x.signedSupportingWitness==='boolean';
   if(report?.schema!=='qualityrag.cross-document-relation-candidates/v1'||
      !['POTENTIAL_CROSS_SOURCE_CONFLICTS',
        'NO_SUPPORTED_RELATION_CONFLICTS_FOUND'].includes(report.status)||
      report.decisionId!==decisionId||
      !Number.isFinite(Date.parse(report.checkedAt))||
      !Number.isSafeInteger(report.candidateCount)||report.candidateCount<0||
      !Number.isSafeInteger(report.sourcesScanned)||report.sourcesScanned<1||
      !Number.isSafeInteger(report.bothSignedConflicts)||
      report.bothSignedConflicts<0||
      !Array.isArray(report.findings)||report.findings.length>64||
      report.findings.length>report.candidateCount||
      report.findings.some(f=>
        !['INVERSE_PAYER_PAYEE','POLARITY_CONFLICT'].includes(f.category)||
        !validAnchor(f.left)||!validAnchor(f.right)||
        f.reviewState!=='NEEDS_EXPLICIT_CROSS_SOURCE_ADJUDICATION')||
      report.findingsTruncated!==(report.findings.length<report.candidateCount)||
      report.status!==(report.candidateCount?
        'POTENTIAL_CROSS_SOURCE_CONFLICTS':
        'NO_SUPPORTED_RELATION_CONFLICTS_FOUND')||
      report.scope!=='LIVE_VERIFIED_INCLUDED_SELECTED_FOLDER_TEXT_FILES'||
      report.sourceTextIncluded!==false||report.actorNamesIncluded!==false||
      report.crossFileSemanticEntailmentVerified!==false||
      report.authoritativenessVerified!==false||
      report.semanticCompletenessVerified!==false||
      report.supportedPatternCoverageOnly!==true||
      report.releasePermittedByThisPreview!==false)
     throw Error('Cross-document relation check denied: unsupported assurance');
   return report;
 }
 async extractFromReviewedSources(decisionId:string,requestId:string):
   Promise<SourceGroundedExtract>{
   if(typeof decisionId!=='string'||!UUID.test(decisionId)||
      typeof requestId!=='string'||!ID.test(requestId))
     throw Error('Invalid grounded extraction request');
   const response=await fetch(this.base+'/v1/evidence/protected-decisions/'+
     decisionId+'/grounded-deliver',{
       method:'POST',cache:'no-store',redirect:'error',
       headers:{Authorization:'Bearer '+this.bearer,'Content-Type':'application/json'},
       body:JSON.stringify({requestId}),signal:AbortSignal.timeout(30000)
     });
   let result:SourceGroundedExtract;
   try{
     const raw=await response.text();
     if(raw.length>100000)throw Error('Response too large');
     result=JSON.parse(raw) as SourceGroundedExtract;
   }catch{throw Error('Grounded extraction denied: invalid registry response')}
   if(!response.ok)throw Error('Grounded extraction denied');
   if(result?.schema!=='qualityrag.source-grounded-extract/v1'||
      result.delivery!=='SERVER_GENERATED_EXTRACT_ONLY'||
      typeof result.answer!=='string'||!result.answer||
      new TextEncoder().encode(result.answer).length>16384||
      !Array.isArray(result.sections)||result.sections.length<1||
      !Number.isSafeInteger(result.coverage?.requiredPolicyObligations)||
      result.coverage.requiredPolicyObligations<1||
      result.coverage.allSignedAnchorsIncluded!==true||
      result.coverage.fullDocumentExaminedForExceptions!==false||
      result.coverage.humanSignedSupports!==result.sections.length||
      result.assertions?.exactLinesRevalidated!==true||
      result.assertions?.humanReviewedAnchorSemantics!==true||
      result.assertions?.modelGeneratedParaphrase!==false||
      result.assertions?.freeFormAnswerEntailmentVerified!==false||
      result.assertions?.documentWideCompletenessVerified!==false||
      result.assertions?.independentPublisherVerified!==false||
      result.answerSemanticsVerified!==false||
      result.globalEnforcement!==false||
      result.externallyAnchored!==false)
     throw Error('Grounded extraction denied: unsupported coverage claims');
   const digest=await crypto.subtle.digest('SHA-256',
     new TextEncoder().encode(result.answer));
   const actualSha=Array.from(new Uint8Array(digest))
      .map(x=>x.toString(16).padStart(2,'0')).join('');
   const receipt=result.receipt;
   if(receipt?.schema!=='qualityrag.protected-decision-use/v1'||
      receipt.permission!=='PERMIT_SIGNED_ASSERTION_USE'||
      receipt.decisionId!==decisionId||receipt.requestId!==requestId||
      receipt.answerSha256!==actualSha||
      receipt.deliveryMode!=='SOURCE_GROUNDED_EXTRACT'||
      !HEX.test(receipt.policySha256||'')||
      !HEX.test(receipt.chainHash||'')||
      !UUID.test(receipt.receiptId||'')||
      receipt.globalEnforcement!==false||
      receipt.answerSemanticsVerified!==false||
      receipt.externallyAnchored!==false||
      receipt.scope!=='THIS_REGISTRY_CHECK_ONLY')
     throw Error('Grounded extraction denied: invalid permit');
   return result;
 }
}
