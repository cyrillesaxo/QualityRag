import React,{useEffect,useState} from 'react';
import {ProtectedAdmission} from './ProtectedAdmission';

type Props={token:string;serviceId:string;environment:string};
type Readiness='checking'|'unavailable'|'protected'|'unprotected';

export function ProtectedAdmissionAvailability({token,serviceId,environment}:Props){
 const [readiness,setReadiness]=useState<Readiness>('checking');
 useEffect(()=>{
  let live=true;
  setReadiness('checking');
  if(!token||!serviceId||!environment){
   setReadiness('unavailable');return()=>{live=false};
  }
  const abort=new AbortController();
  const params=new URLSearchParams({serviceId,environment});
  fetch('/v1/evidence/enforcement?'+params.toString(),{
   headers:{Authorization:'Bearer '+token},cache:'no-store',
   redirect:'error',signal:abort.signal
  }).then(async res=>{
   if(!res.ok)throw Error('Not authorized or not configured');
   const data=await res.json();
   if(data.schema!=='qualityrag.drive-protection/v1'||
      data.serviceId!==serviceId||data.environment!==environment)
    throw Error('Incompatible protection contract');
   if(live)setReadiness(data.protected===true?'protected':'unprotected');
  }).catch(()=>{if(live)setReadiness('unavailable')});
  return()=>{live=false;abort.abort()};
 },[token,serviceId,environment]);
 return <section aria-label="Signed evidence readiness" style={{
  padding:12,border:'1px solid #b7d7bf',borderRadius:12,marginTop:16}}>
   <h3>Signed evidence review and control</h3>
   {readiness==='checking'&&<p role="status">Checking service protection and permitted telemetry…</p>}
   {readiness==='unavailable'&&<p role="status">
    Signed review cannot be opened. This service's scoped Registry enforcement status
    is unavailable or your identity lacks the required evidence reader role.
    No evidence submission or source release was attempted.
   </p>}
   {readiness==='unprotected'&&<p role="status">
    Signed protected review is not activated for this service/environment.
    Do not treat source search or existing evaluations as protected admission.
   </p>}
   {readiness==='protected'&&
    <ProtectedAdmission key={serviceId+'@'+environment}
     token={token} serviceId={serviceId} environment={environment} enabled/>}
 </section>;
}
