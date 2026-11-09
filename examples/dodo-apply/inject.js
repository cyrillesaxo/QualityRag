(() => {
  if (window.__dodoApplyContactListenerInstalled) return;
  window.__dodoApplyContactListenerInstalled = true;
  const patterns = {
    firstName: /^(first[ _-]?name|given[ _-]?name|fname)$/i,
    lastName: /^(last[ _-]?name|family[ _-]?name|surname|lname)$/i,
    email: /^(e[ _-]?mail(?:[ _-]?address)?|emailaddress)$/i,
    phone: /^(phone(?:[ _-]?(?:number|mobile))?|mobile(?:[ _-]?number)?|telephone)$/i
  };
  const normalize = s => String(s||'').trim().replace(/[*:]/g,'').replace(/\\s+/g,' ');
  function labels(input) {
    const explicit = input.labels ? [...input.labels].map(x=>x.innerText) : [];
    return [input.name,input.id,input.getAttribute('aria-label'),...explicit].map(normalize).filter(Boolean);
  }
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message?.type !== 'DODO_FILL_CONTACT') return;
    let count=0;
    const used=new Set();
    for (const input of document.querySelectorAll('input')) {
      if (input.disabled || input.readOnly || input.type === 'hidden' || input.type === 'password' || input.type === 'file' || input.value.trim()) continue;
      if (!['text','email','tel',''].includes(input.type)) continue;
      const matched = Object.entries(patterns).filter(([key, pattern]) => !used.has(key) && message.profile?.[key] && labels(input).some(label=>pattern.test(label)));
      if (matched.length !== 1) continue;
      const [key] = matched[0];
      const descriptor=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value');
      descriptor.set.call(input,message.profile[key]);
      input.dispatchEvent(new Event('input',{bubbles:true}));
      input.dispatchEvent(new Event('change',{bubbles:true}));
      used.add(key);count++;
    }
    respond({count});
  });
})();
