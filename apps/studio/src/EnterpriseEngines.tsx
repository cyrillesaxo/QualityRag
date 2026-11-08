import React from 'react';

type Engine={name:string;description:string;tools:string[]};
const ENGINES:Engine[]=[
 {name:'Data Protection',description:'PCI masking, tokenization and privileged detokenization.',tools:['pci.mask','pci.tokenize','pci.detokenize']},
 {name:'Secrets',description:'Dynamic secrets and credential lifecycle.',tools:['secrets.read','secrets.rotate']},
 {name:'PKI',description:'Certificate issuance, renewal and revocation.',tools:['pki.issue','pki.revoke']},
 {name:'Database',description:'Short-lived database credentials.',tools:['database.credentials']},
 {name:'Transit',description:'Encryption, decryption and key operations.',tools:['transit.encrypt','transit.decrypt']},
 {name:'Trust & Telemetry',description:'Signed evidence attestations and enterprise audit trails.',tools:['trust.attest','audit.verify']}
];
export default function EnterpriseEngines(){
 return <section aria-labelledby="enterprise-engines-heading">
  <h2 id="enterprise-engines-heading">Enterprise Engines</h2>
  <p>Optional private Dodo Enterprise capabilities. Engine execution and licensing are enforced by the server; these disabled controls are only a discovery preview.</p>
  <div className="enterprise-engine-grid">
   {ENGINES.map(engine=><article className="enterprise-engine-card" key={engine.name}>
    <div className="enterprise-engine-heading"><h3>{engine.name}</h3><span className="enterprise-locked">Enterprise · Locked</span></div>
    <p>{engine.description}</p>
    <p className="enterprise-tool-list">{engine.tools.map(tool=><code key={tool}>{tool}</code>)}</p>
    <button type="button" disabled aria-label={engine.name+' requires an enterprise license'}>Configure (Enterprise)</button>
   </article>)}
  </div>
  <p className="status">Enterprise engines are not connected in this Studio build. No sensitive configuration or tokenization data is loaded into the browser.</p>
 </section>;
}
