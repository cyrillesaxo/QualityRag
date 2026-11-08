// Conservative lexical sufficiency preflight for exact live-verified source files.
// A signal is a *candidate review task*, not a factual contradiction or proof
// that all exceptions were found. No source text is returned or logged.
const patterns=[
 ['EXCEPTION',/\b(?:except|excepting|excluding|other than)\b/i],
 ['CONDITIONAL',/\b(?:unless|only if|provided that|subject to|conditioned on)\b/i],
 ['OVERRIDE',/\b(?:notwithstanding|however|in spite of|despite)\b/i],
 ['NEGATION',/\b(?:must not|may not|does not apply|do not apply|shall not|no longer)\b/i]
];
const sourceRe=/^google_drive\/[a-f0-9]{32}$/;
const fail=(code)=>{throw Error(code)};
const check=(ok,code)=>{if(!ok)fail(code)};
export function scanReviewedSourceConstraints({sources,witnesses,maxCandidates=32}){
 check(Array.isArray(sources)&&sources.length>0&&sources.length<=8&&
   Array.isArray(witnesses)&&witnesses.length>0&&witnesses.length<=8&&
   Number.isSafeInteger(maxCandidates)&&maxCandidates>=1&&
   maxCandidates<=64,'PROTECTED_SUFFICIENCY_INPUT_INVALID');
 const reviews=new Set();
 for(const w of witnesses){
   check(w&&sourceRe.test(w.sourceId)&&Number.isSafeInteger(w.lineNumber)&&
     w.lineNumber>=1&&w.lineNumber<=6000&&
     ['SUPPORTS','CONTRADICTS','UNKNOWN'].includes(w.status),
     'PROTECTED_SUFFICIENCY_INPUT_INVALID');
   if(w.status==='SUPPORTS')reviews.add(w.sourceId+':'+w.lineNumber);
 }
 let reviewedCount=0,unreviewedCount=0,linesScanned=0;
 const candidates=[],seenSources=new Set();
 for(const source of [...sources].sort((a,b)=>a.sourceId.localeCompare(b.sourceId))){
   check(source&&sourceRe.test(source.sourceId)&&
     !seenSources.has(source.sourceId)&&
     Array.isArray(source.lines)&&source.lines.length>0&&
     source.lines.length<=6000,
     'PROTECTED_SUFFICIENCY_SOURCE_UNAVAILABLE');
   seenSources.add(source.sourceId);
   for(let n=0;n<source.lines.length;n++){
     const line=source.lines[n];
     check(typeof line==='string'&&line.length<=1200,
       'PROTECTED_SUFFICIENCY_SOURCE_UNAVAILABLE');
     linesScanned++;
     const matched=patterns.find(([,re])=>re.test(line));
     if(!matched)continue;
     if(reviews.has(source.sourceId+':'+(n+1))){reviewedCount++;continue}
     unreviewedCount++;
     if(candidates.length<maxCandidates)candidates.push({
       sourceId:source.sourceId,lineNumber:n+1,
       category:matched[0],reviewStatus:'NOT_SIGNED_FOR_THIS_SOURCE_LINE'
     });
   }
 }
 check(witnesses.every(w=>seenSources.has(w.sourceId)),
   'PROTECTED_SUFFICIENCY_SOURCE_UNAVAILABLE');
 return {schema:'qualityrag.constraint-signal-scan/v1',
   status:unreviewedCount?'UNREVIEWED_LEXICAL_SIGNALS':'NO_UNREVIEWED_LEXICAL_SIGNALS',
   candidateCount:unreviewedCount,reviewedSignalCount:reviewedCount,
   candidates,candidatesTruncated:unreviewedCount>candidates.length,
   sourcesScanned:seenSources.size,linesScanned,
   scope:'LIVE_VERIFIED_SIGNED_SOURCE_FILES_ONLY',
   sourceTextIncluded:false,
   heuristic:'BOUNDED_EXPLICIT_LANGUAGE_PATTERNS',
   signalIsProvenException:false,
   wholeFolderScanned:false,documentWideSemanticCompletenessVerified:false,
   otherFilesMayContainUnknownConstraints:true};
}
