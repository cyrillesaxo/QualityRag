import React,{useState} from 'react';

type Engine={name:string;description:string;tools:string[];benefit:string};
const ENGINES:Engine[]=[
 {name:'Data Protection',description:'PCI masking, tokenization and privileged detokenization.',tools:['pci.mask','pci.tokenize','pci.detokenize'],benefit:'Keep payment-card numbers out of AI prompts and retrieval indexes.'},
 {name:'Secrets',description:'Dynamic secrets and credential lifecycle.',tools:['secrets.read','secrets.rotate'],benefit:'Issue credentials only to authorized workloads.'},
 {name:'PKI',description:'Certificate issuance, renewal and revocation.',tools:['pki.issue','pki.revoke'],benefit:'Manage workload certificate lifecycles.'},
 {name:'Database',description:'Short-lived database credentials.',tools:['database.credentials'],benefit:'Reduce exposure from long-lived database passwords.'},
 {name:'Transit',description:'Encryption, decryption and key operations.',tools:['transit.encrypt','transit.decrypt'],benefit:'Keep encryption keys outside the AI application.'},
 {name:'Trust & Telemetry',description:'Signed evidence attestations and enterprise audit trails.',tools:['trust.attest','audit.verify'],benefit:'Inspect signed provenance and policy decisions.'}
];
const DEMO_PAN='4111 1111 1111 1111';
const MASKED_PAN='•••• •••• •••• 1111';
const CONTACT='https://dodollc.net';
export default function EnterpriseEngines(){
 const [expanded,setExpanded]=useState<string|null>('Data Protection');
 const [demo,setDemo]=useState(false);
 function contact(engine:string){
  const url=new URL(CONTACT);
  url.searchParams.set('utm_source','qualityrag_studio');
  url.searchParams.set('utm_medium','enterprise_engine');
  url.searchParams.set('utm_campaign','engine_discovery');
  url.searchParams.set('utm_content',engine.toLowerCase().replace(/[^a-z0-9]+/g,'-'));
  window.open(url.toString(),'_blank','noopener,noreferrer');
 }
 return <section aria-labelledby="enterprise-engines-heading">
  <h2 id="enterprise-engines-heading">Enterprise Engines</h2>
  <p>Explore enterprise capabilities using safe examples. Production configuration requires a license and server-side authorization.</p>
  <div className="enterprise-engine-grid">
   {ENGINES.map(engine=><article className="enterprise-engine-card" key={engine.name}>
    <div className="enterprise-engine-heading"><h3>{engine.name}</h3><span className="enterprise-locked">Enterprise · Locked</span></div>
    <p>{engine.description}</p>
    <p><strong>Why it matters:</strong> {engine.benefit}</p>
    <p className="enterprise-tool-list">{engine.tools.map(tool=><code key={tool}>{tool}</code>)}</p>
    <div className="enterprise-actions">
     <button type="button" onClick={()=>{setExpanded(expanded===engine.name?null:engine.name);setDemo(false)}} aria-expanded={expanded===engine.name}> {expanded===engine.name?'Hide example':'Explore free example'}</button>
     <button type="button" disabled aria-label={engine.name+' production configuration requires an enterprise license'}>Configure · Locked</button>
    </div>
    {expanded===engine.name&&<div className="enterprise-demo">
     {engine.name==='Data Protection'?<>
      <p><strong>PCI masking — synthetic example</strong></p>
      <p>Input: <code>{DEMO_PAN}</code></p>
      <button type="button" onClick={()=>setDemo(true)}>Run sample masking</button>
      {demo&&<div role="status"><p>Masked: <code>{MASKED_PAN}</code></p><p>Only the final four digits remain visible. This is a static demonstration, not a live PCI scan, tokenization service, or compliance certification.</p></div>}
     </>:<p>{engine.benefit} This preview describes the capability; no enterprise backend or customer data is accessed.</p>}
     <button type="button" onClick={()=>contact(engine.name)}>Explore Enterprise with Dodo LLC</button>
    </div>}
   </article>)}
  </div>
  <p className="status">No card data, secrets, or enterprise credentials are collected by these previews. Paid features remain locked until server-side licensing and engine APIs are connected.</p>
 </section>;
}
