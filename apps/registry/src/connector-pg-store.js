// PostgreSQL persistence for OAuth PKCE state and encrypted provider credentials.
// Database role permissions must restrict access to the registry service only.
export class PgConnectorStore{
 constructor(pool){if(!pool||typeof pool.query!=='function')throw new Error('POSTGRES_POOL_REQUIRED');this.pool=pool}
 async savePending(pending,provider='google'){
  const {state_hash,tenant_id,principal_id,code_verifier,expires_at}=pending;
  if(!['google','microsoft','dropbox','box'].includes(provider))throw new Error('INVALID_PROVIDER');
  if(!state_hash||!tenant_id||!principal_id||!code_verifier||!Number.isFinite(expires_at))throw new Error('INVALID_OAUTH_PENDING');
  await this.pool.query('INSERT INTO qr_connector_oauth_states(state_hash,tenant_id,principal_id,provider,code_verifier,expires_at) VALUES ($1,$2,$3,$4,$5,$6)',
   [state_hash,tenant_id,principal_id,provider,code_verifier,new Date(expires_at)]);
 }
 // Atomic consume: a replay or concurrent callback cannot obtain the verifier twice.
 async consumePending({stateHash,tenantId,principalId,provider='google'}){
  const r=await this.pool.query(`UPDATE qr_connector_oauth_states SET consumed_at=now()
   WHERE state_hash=$1 AND tenant_id=$2 AND principal_id=$3 AND provider=$4
    AND consumed_at IS NULL AND expires_at>now()
   RETURNING state_hash,tenant_id,principal_id,provider,code_verifier,expires_at`,
   [stateHash,tenantId,principalId,provider]);
  if(r.rowCount!==1)throw new Error('OAUTH_STATE_EXPIRED_OR_USED');
  return {state_hash:r.rows[0].state_hash,tenant_id:r.rows[0].tenant_id,
   principal_id:r.rows[0].principal_id,code_verifier:r.rows[0].code_verifier,
   expires_at:new Date(r.rows[0].expires_at).getTime(),consumed:true};
 }
 async saveCredential({connectionId,tenantId,principalId,provider,displayName='',encryptedRecord,scopes=[]}){
  if(!connectionId||!tenantId||!principalId||!encryptedRecord||!['google','microsoft','dropbox','box'].includes(provider))throw new Error('INVALID_CONNECTOR_CREDENTIAL');
  await this.pool.query(`INSERT INTO qr_connector_credentials(connection_id,tenant_id,principal_id,provider,display_name,encrypted_record,granted_scopes)
    VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7)
    ON CONFLICT (connection_id) DO UPDATE SET encrypted_record=EXCLUDED.encrypted_record,
    granted_scopes=EXCLUDED.granted_scopes,updated_at=now()
    WHERE qr_connector_credentials.tenant_id=EXCLUDED.tenant_id AND qr_connector_credentials.principal_id=EXCLUDED.principal_id AND qr_connector_credentials.provider=EXCLUDED.provider`,
   [connectionId,tenantId,principalId,provider,displayName,JSON.stringify(encryptedRecord),scopes]);
 }
 async listConnections(tenantId,principalId){
  const r=await this.pool.query(`SELECT connection_id,provider,display_name,granted_scopes,status FROM qr_connector_credentials
    WHERE tenant_id=$1 AND principal_id=$2 AND status<>'revoked' ORDER BY created_at DESC`,[tenantId,principalId]);
  return r.rows.map(x=>({id:x.connection_id,provider:x.provider,display_name:x.display_name,
   scopes:x.granted_scopes,status:x.status}));
 }
 async getEncryptedCredential({connectionId,tenantId,principalId}){
  const r=await this.pool.query(`SELECT provider,encrypted_record FROM qr_connector_credentials
    WHERE connection_id=$1 AND tenant_id=$2 AND principal_id=$3 AND status='connected'`,[connectionId,tenantId,principalId]);
  if(r.rowCount!==1)throw new Error('CONNECTOR_NOT_FOUND');
  return r.rows[0];
 }
 async revoke({connectionId,tenantId,principalId}){
  const r=await this.pool.query(`UPDATE qr_connector_credentials SET status='revoked',updated_at=now()
    WHERE connection_id=$1 AND tenant_id=$2 AND principal_id=$3 AND status<>'revoked' RETURNING connection_id`,[connectionId,tenantId,principalId]);
  if(r.rowCount!==1)throw new Error('CONNECTOR_NOT_FOUND');
 }
}
