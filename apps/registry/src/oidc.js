import {createRemoteJWKSet, jwtVerify} from 'jose';

const ROLE = Object.freeze({
  read: 'policy.reader',
  author: 'policy.author',
  approve: 'policy.approver',
  publish: 'policy.publisher',
  evidenceIngest: 'evidence.ingest',
  evidenceRead: 'evidence.reader',
  evidenceReview: 'evidence.reviewer',
  driveRead: 'drive.reader',
  driveManage: 'drive.manager'
});
export {ROLE};

function requireText(value, label) {
  if(typeof value!=='string'||!value.trim())throw new Error('INVALID_OIDC_'+label);
  return value;
}

export function createOidcAuthenticator({issuer,audience,jwksUri,roleClaim='roles'}){
  const issued=requireText(issuer,'ISSUER');
  const aud=requireText(audience,'AUDIENCE');
  const location = new URL(requireText(jwksUri,'JWKS_URI'));
  if(location.protocol!=='https:' && !(location.protocol==='http:' &&
     ['localhost','127.0.0.1'].includes(location.hostname)))throw new Error('OIDC_JWKS_HTTPS_REQUIRED');
  if(location.username||location.password||location.hash)throw new Error('INVALID_OIDC_JWKS_URI');
  if(!/^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$/.test(roleClaim))throw new Error('INVALID_OIDC_ROLE_CLAIM');
  const jwks=createRemoteJWKSet(location, {timeoutDuration:3000,cooldownDuration:30000});
  return async function authenticate(rawToken){
    if(typeof rawToken!=='string'||!rawToken)return null;
    try{
      const {payload}=await jwtVerify(rawToken,jwks,{issuer:issued,audience:aud,
        algorithms:['RS256','PS256','ES256','EdDSA'],clockTolerance:5,
        maxTokenAge:'1h',requiredClaims:['sub','iat','exp']});
      if(typeof payload.sub!=='string'||!payload.sub.trim())return null;
      const declared=payload[roleClaim];
      if(!Array.isArray(declared)||!declared.every(x=>typeof x==='string'))return null;
      const services=payload.qualityrag_services;
      if(services!==undefined&&(!Array.isArray(services)||!services.every(x=>
        typeof x==='string'&&/^[a-zA-Z0-9._-]+@[a-zA-Z0-9._-]+$/.test(x))))
        return null;
      return {subject:issued+'#'+payload.sub,
        roles:new Set(declared.filter(x=>Object.values(ROLE).includes(x))),
        evidenceServices:new Set(services||[])};
    }catch{return null}
  };
}

export function permissionFor(method,pathname){
  if(pathname==='/v1/drives/google/status'&&method==='GET')return ROLE.driveRead;
  if(pathname==='/v1/drives/google/folders'&&method==='GET')return ROLE.driveRead;
  if(pathname==='/v1/drives/google/files'&&method==='GET')return ROLE.driveRead;
  if(pathname==='/v1/drives/google/start'&&method==='POST')return ROLE.driveManage;
  if(pathname==='/v1/drives/google/folder'&&method==='POST')return ROLE.driveManage;
  if(pathname==='/v1/drives/google/disconnect'&&method==='POST')return ROLE.driveManage;
  const ev='/v1/evidence/evaluations';
  if(method==='POST'&&pathname===ev)return ROLE.evidenceIngest;
  if(method==='GET'&&(pathname===ev||
    (pathname.startsWith(ev+'/')&&[5,6].includes(pathname.split('/').length))))
    return ROLE.evidenceRead;
  if(method==='POST'&&pathname.startsWith(ev+'/')&&
    pathname.split('/').length===6&&pathname.endsWith('/replay'))return ROLE.evidenceRead;
  if(method==='POST'&&pathname.startsWith(ev+'/')&&
    pathname.split('/').length===6&&pathname.endsWith('/reviews'))return ROLE.evidenceReview;
  if(method==='GET'&&(pathname==='/v1/state'||pathname.startsWith('/v1/resolve/')||
     pathname.startsWith('/v1/signed/resolve/')))return ROLE.read;
  if(method==='POST'&&(pathname==='/v1/services'||pathname==='/v1/policies/drafts'||
     pathname==='/v1/signed/promotions'))return ROLE.author;
  if(method==='POST'&&(/^\/v1\/policies\/[^/]+\/[^/]+\/approve$/.test(pathname)||
     /^\/v1\/signed\/promotions\/[^/]+\/[^/]+\/[0-9]+\/approve$/.test(pathname)))return ROLE.approve;
  if(method==='POST'&&(pathname==='/v1/bindings'||
     /^\/v1\/signed\/promotions\/[^/]+\/[^/]+\/[0-9]+\/publish$/.test(pathname)))return ROLE.publish;
  return null;
}
