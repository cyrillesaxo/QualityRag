// Explicit per-service fail-closed ingress barrier for Drive-governed pilots.
// This is a registry protection setting, not universal enforcement in external apps.
const IDENTIFIER=/^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
export function parseProtectedDriveServices(raw=''){
 if(typeof raw!=='string'||raw.length>2048)
   throw Error('INVALID_PROTECTED_DRIVE_SERVICES');
 if(!raw.trim())return new Set();
 const values=raw.split(',').map(s=>s.trim());
 if(values.length>50||values.some(v=>{
   const pieces=v.split('@');
   return pieces.length!==2||!pieces.every(p=>IDENTIFIER.test(p));
 }))throw Error('INVALID_PROTECTED_DRIVE_SERVICES');
 if(new Set(values).size!==values.length)throw Error('DUPLICATE_PROTECTED_DRIVE_SERVICE');
 return new Set(values);
}
