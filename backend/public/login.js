const form=document.querySelector('#login-form');
form.addEventListener('submit',async(event)=>{
  event.preventDefault();
  const button=form.querySelector('button'),message=document.querySelector('#message');
  message.textContent='';button.disabled=true;button.textContent='Đang kiểm tra...';
  try{
    const resp=await fetch('/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({password:form.password.value})});
    const data=await resp.json();
    if(!resp.ok) throw new Error(data.detail||'Không thể đăng nhập');
    location.replace('/');
  }catch(error){message.textContent=error.message;button.disabled=false;button.textContent='Vào Studio →';}
});
