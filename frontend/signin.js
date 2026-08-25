const message = document.querySelector('#account-message');

async function submitAccount(path, form) {
  const credentials = Object.fromEntries(new FormData(form));
  const response = await fetch(`/api/${path}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(credentials)
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  if (path === 'register') {
    message.textContent = 'Account created. You can sign in now.';
    form.reset();
    return;
  }
  localStorage.setItem('microshop-session', JSON.stringify(result));
  window.location.href = result.role === 'admin' ? '/admin.html' : '/';
}

document.querySelector('#login-form').addEventListener('submit', async event => {
  event.preventDefault();
  try { await submitAccount('login', event.target); } catch (error) { message.textContent = error.message; }
});

document.querySelector('#register-form').addEventListener('submit', async event => {
  event.preventDefault();
  try { await submitAccount('register', event.target); } catch (error) { message.textContent = error.message; }
});
