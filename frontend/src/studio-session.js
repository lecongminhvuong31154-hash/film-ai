/* Simple logout control for password-gated web deployment. */
(async function(){
  try {
    const response=await fetch('/auth/status',{credentials:'same-origin'});
    if(!response.ok) return;
    const state=await response.json();
    if(!state.enabled) return;
    const button=document.createElement('button');
    button.id='studio-logout';button.textContent='Đăng xuất';button.setAttribute('aria-label','Đăng xuất khỏi AI Film Factory');
    button.addEventListener('click',async()=>{
      await fetch('/auth/logout',{method:'POST',credentials:'same-origin'});
      location.replace('/login');
    });
    document.body.appendChild(button);
  }catch(_){}
})();
