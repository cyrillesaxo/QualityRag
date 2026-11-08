import {acceptBalafonsEvidence} from './balafons-evidence.js';

// Opt-in receiver, mounted only behind an authenticated service gateway.
// resolveOwner MUST verify a trusted service credential and return the Balafons
// owner from an independently authenticated authorization context.
export function createBalafonsIngestHandler({secret,resolveOwner,replayStore,enqueue}){
 if(typeof resolveOwner!=='function'||typeof enqueue!=='function'||!replayStore?.claim||typeof secret!=='string'||secret.length<32)
  throw new Error('BALAFONS_RECEIVER_NOT_CONFIGURED');
 return async function(req,res){
  const respond=(status,data)=>{res.writeHead(status,{'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff'});res.end(JSON.stringify(data))};
  if(req.method!=='POST')return respond(405,{error:'METHOD_NOT_ALLOWED'});
  let owner;
  try{owner=await resolveOwner(req)}catch{return respond(401,{error:'UNAUTHORIZED'})}
  if(typeof owner!=='string'||!owner)return respond(401,{error:'UNAUTHORIZED'});
  const chunks=[];let size=0;
  try{
   for await(const chunk of req){size+=chunk.length;if(size>500000)return respond(413,{error:'BODY_TOO_LARGE'});chunks.push(chunk)}
   const payload=Buffer.concat(chunks).toString('utf8');
   const event=await acceptBalafonsEvidence({payload,signature:req.headers['x-qualityrag-signature'],secret,expectedOwnerId:owner,replayStore});
   // Queue must be durable, tenant-partitioned and idempotent by event_id.
   await enqueue(event);
   return respond(202,{accepted:true,event_id:event.event_id});
  }catch(error){
   if(error.message==='EVIDENCE_REPLAY')return respond(409,{error:'EVIDENCE_REPLAY'});
   if(error.message==='EVIDENCE_OWNER_MISMATCH')return respond(403,{error:'EVIDENCE_OWNER_MISMATCH'});
   if(error.message==='EVIDENCE_EVENT_EXPIRED')return respond(400,{error:'EVIDENCE_EVENT_EXPIRED'});
   if(error.message==='INVALID_EVIDENCE_SIGNATURE')return respond(401,{error:'INVALID_EVIDENCE_SIGNATURE'});
   if(error.message==='BODY_TOO_LARGE')return respond(413,{error:'BODY_TOO_LARGE'});
   // Never echo raw upstream errors or source contents.
   return respond(400,{error:'EVIDENCE_REJECTED'});
  }
 };
}
