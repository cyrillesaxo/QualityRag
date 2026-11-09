// Conservative WitnessGraph candidate detection for selected live-verified
// files. This is a bounded English surface grammar, NOT automatic entailment.
// No actor names or original source text ever leave this helper.
const SOURCE=/^google_drive\/[0-9a-f]{32}$/;
const REL=/^\s*(?:the\s+)?([a-z][a-z-]{1,31})\s+(must pay|must not pay|pays|does not pay|shall pay|shall not pay)\s+(?:the\s+)?([a-z][a-z-]{1,31})\s*[.!]?\s*$/i;
const ACTION={
 'must pay':true,'pays':true,'shall pay':true,
 'must not pay':false,'does not pay':false,'shall not pay':false
};
function check(condition,code){if(!condition)throw Error(code)}
function extract(line){
 const match=REL.exec(line);
 if(!match)return null;
 const from=match[1].toLowerCase(),to=match[3].toLowerCase();
 if(from===to)return null;
 return {from,to,positive:ACTION[match[2].toLowerCase()]};
}
export function scanRelationshipConflicts({sources,witnesses,maxFindings=32}){
 check(Array.isArray(sources)&&sources.length>0&&sources.length<=40&&
   Array.isArray(witnesses)&&witnesses.length>0&&witnesses.length<=8&&
   Number.isInteger(maxFindings)&&maxFindings>=1&&maxFindings<=64,
   'PROTECTED_RELATION_INPUT_INVALID');
 const reviewed=new Set();
 for(const w of witnesses){
   check(w&&SOURCE.test(w.sourceId)&&Number.isSafeInteger(w.lineNumber)&&
      w.lineNumber>=1&&w.lineNumber<=6000&&
      ['SUPPORTS','CONTRADICTS','UNKNOWN'].includes(w.status),
      'PROTECTED_RELATION_INPUT_INVALID');
   if(w.status==='SUPPORTS')reviewed.add(w.sourceId+':'+w.lineNumber);
 }
 check(sources.every(s=>s&&SOURCE.test(s.sourceId)&&
   Array.isArray(s.lines)&&s.lines.length>0&&s.lines.length<=6000),
   'PROTECTED_RELATION_SOURCE_INVALID');
 const sorted=[...sources].sort((a,b)=>a.sourceId.localeCompare(b.sourceId));
 const seen=new Set(),edges=[];
 let linesScanned=0;
 for(const source of sorted){
   check(!seen.has(source.sourceId),'PROTECTED_RELATION_SOURCE_INVALID');
   seen.add(source.sourceId);
   for(let i=0;i<source.lines.length;i++){
     const line=source.lines[i];
     check(typeof line==='string'&&line.length<=1200,
       'PROTECTED_RELATION_SOURCE_INVALID');
     linesScanned++;
     const parsed=extract(line);
     if(!parsed)continue;
     edges.push({...parsed,sourceId:source.sourceId,lineNumber:i+1,
       signedSupportingWitness:reviewed.has(source.sourceId+':'+(i+1))});
     check(edges.length<=256,'PROTECTED_RELATION_EDGE_LIMIT');
   }
 }
 check(witnesses.every(w=>seen.has(w.sourceId)),
   'PROTECTED_RELATION_SOURCE_INVALID');
 const findings=[];
 let candidateCount=0;
 const bothReviewed={count:0};
 for(let a=0;a<edges.length;a++){
   for(let b=a+1;b<edges.length;b++){
     const x=edges[a],y=edges[b];
     // Cross-file relations only. A contradiction in the same document
     // remains outside this particular cross-document candidate detector.
     if(x.sourceId===y.sourceId)continue;
     const same=x.from===y.from&&x.to===y.to;
     const reversed=x.from===y.to&&x.to===y.from;
     const category=same&&x.positive!==y.positive?
       'POLARITY_CONFLICT':
       reversed&&x.positive&&y.positive?
         'INVERSE_PAYER_PAYEE':null;
     if(!category)continue;
     candidateCount++;
     if(x.signedSupportingWitness&&y.signedSupportingWitness)
       bothReviewed.count++;
     if(findings.length<maxFindings){
       findings.push({
         category,
         left:{sourceId:x.sourceId,lineNumber:x.lineNumber,
           signedSupportingWitness:x.signedSupportingWitness},
         right:{sourceId:y.sourceId,lineNumber:y.lineNumber,
           signedSupportingWitness:y.signedSupportingWitness},
         reviewState:'NEEDS_EXPLICIT_CROSS_SOURCE_ADJUDICATION'
       });
     }
   }
 }
 return {
   schema:'qualityrag.cross-document-relation-candidates/v1',
   status:candidateCount?'POTENTIAL_CROSS_SOURCE_CONFLICTS':
     'NO_SUPPORTED_RELATION_CONFLICTS_FOUND',
   candidateCount,findings,
   findingsTruncated:candidateCount>findings.length,
   bothSignedConflicts:bothReviewed.count,
   sourcesScanned:seen.size,linesScanned,relationEdgesParsed:edges.length,
   scope:'LIVE_VERIFIED_INCLUDED_SELECTED_FOLDER_TEXT_FILES',
   grammar:'BOUNDED_ENGLISH_PAYER_PAYEE_AND_NEGATED_PAYMENT',
   sourceTextIncluded:false,actorNamesIncluded:false,
   crossFileSemanticEntailmentVerified:false,
   authoritativenessVerified:false,
   semanticCompletenessVerified:false,
   supportedPatternCoverageOnly:true,
   nextAction:candidateCount?
     'REVIEW_AUTHORITY_SCOPE_DATE_AND_CORRECT_PAYER_PAYEE':
     'NO_DETECTED_CONFLICT_NOT_A_PROOF_OF_CONSISTENCY'
 };
}
