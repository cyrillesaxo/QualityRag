/** Strict one-shot private APX comparator runner.
 *
 * Host-owned text is consumed from bounded stdin; only redacted diagnostics
 * are written to stdout. The secret HMAC key arrives from the trusted host
 * environment, never in a command-line argument or response. Missing native
 * engine FAILS (never silently falls back to a reimplementation).
 */
import {loadNativeSemanticComparator} from './rct_apx_source_spans_native.mjs';

const MAX_INPUT=22000;
async function readBoundedStdin(){
  let text='';
  for await (const chunk of process.stdin) {
    text+=chunk.toString('utf8');
    if (Buffer.byteLength(text,'utf8')>MAX_INPUT)
      throw new Error('Input exceeds limit');
  }
  return text;
}

async function main(){
  const input=JSON.parse(await readBoundedStdin());
  if (!input || Array.isArray(input) || typeof input!=='object'
      || Object.keys(input).sort().join(',')!=='afterText,beforeText'
      || typeof input.beforeText!=='string'
      || typeof input.afterText!=='string'
      || input.beforeText.length>8192 || input.afterText.length>8192
      || !input.beforeText.length || !input.afterText.length)
    throw new Error('Invalid input shape');
  const secret=process.env.RCT_APX_HMAC_KEY_B64;
  delete process.env.RCT_APX_HMAC_KEY_B64;
  if(typeof secret!=='string' || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(secret))
    throw new Error('Missing canonical host key');
  const key=Buffer.from(secret,'base64');
  if(key.length<32 || key.toString('base64')!==secret)
    throw new Error('Invalid host key');
  const comparator=await loadNativeSemanticComparator();
  const result=comparator.inspect({
    beforeText:input.beforeText,afterText:input.afterText,hmacKey:key,
  });
  key.fill(0);
  process.stdout.write(JSON.stringify(result)+'\n');
}

main().catch(()=>{
  // Never print raw input, import exception stacks, credentials, or source
  // snippets into logs. Trusted hosts receive only failure status.
  process.stderr.write('Native APX semantic execution unavailable or invalid.\n');
  process.exitCode=2;
});
