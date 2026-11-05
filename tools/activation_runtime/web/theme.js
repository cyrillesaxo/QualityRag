'use strict';
// Runs before the page draws so a chosen theme never flashes. "system" follows the OS setting.
(function(){
  try{const t=localStorage.getItem('qr-theme');if(t==='light'||t==='dark')document.documentElement.dataset.theme=t;}catch(_e){/* storage unavailable: follow the system */}
})();
