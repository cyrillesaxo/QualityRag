const profileInput = document.getElementById('profile');
const status = document.getElementById('status');
const keys = ['firstName','lastName','email','phone'];
chrome.storage.local.get('profile', ({ profile }) => { profileInput.value = JSON.stringify(profile || {firstName:'',lastName:'',email:'',phone:''}, null, 2); });
function parse() {
  const input = JSON.parse(profileInput.value);
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw Error('Expected a JSON object.');
  const profile = {};
  for (const k of keys) {
    if (input[k] !== undefined && typeof input[k] !== 'string') throw Error(k + ' must be text.');
    profile[k] = (input[k] || '').trim().slice(0, 250);
  }
  return profile;
}
document.getElementById('save').addEventListener('click', async () => {
  try { await chrome.storage.local.set({profile:parse()}); status.textContent='Saved on this browser.'; }
  catch(e) { status.textContent='Cannot save: '+e.message; }
});
document.getElementById('fill').addEventListener('click', async () => {
  try {
    const profile = parse();
    const [tab] = await chrome.tabs.query({active:true,currentWindow:true});
    if (!tab?.id || !/^https?:/.test(tab.url || '')) throw Error('Open an HTTPS job application tab.');
    const result = await chrome.scripting.executeScript({target:{tabId:tab.id},files:['inject.js']});
    const response = await chrome.tabs.sendMessage(tab.id,{type:'DODO_FILL_CONTACT',profile});
    status.textContent = response?.count ? 'Filled '+response.count+' contact field(s). Review every value before submitting.' : 'No eligible contact fields found. Nothing was changed.';
  } catch(e) { status.textContent='Cannot fill: '+e.message; }
});
