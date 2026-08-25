const session = JSON.parse(localStorage.getItem('microshop-session') || 'null');
const message = document.querySelector('#admin-message');
const headers = session ? {Authorization: `Bearer ${session.token}`} : {};

if (!session || session.role !== 'admin') {
  window.location.href = '/signin.html';
}

async function loadProducts() {
  const response = await fetch('/api/admin/products', {headers});
  if (response.status === 401) { window.location.href = '/signin.html'; return; }
  const products = await response.json();
  document.querySelector('#admin-products').replaceChildren(...products.map(product => {
    const row = document.createElement('div');
    row.className = 'admin-row';
    row.innerHTML = `<span><strong>${product.name}</strong><small>${product.id} / ${product.category} / ${product.status}</small></span>`;
    if (product.status === 'pending') {
      row.innerHTML += '<input class="stock-input" type="number" min="1" value="10" aria-label="Starting stock"><button type="button">Enable product</button>';
      row.querySelector('button').addEventListener('click', () => enableProduct(product, row));
    }
    return row;
  }));
}

async function enableProduct(product, row) {
  const button = row.querySelector('button');
  const quantity = Number(row.querySelector('.stock-input').value);
  button.disabled = true;
  const productResponse = await fetch(`/api/admin/products/${product.id}/enable`, {method: 'PUT', headers});
  const stockResponse = await fetch('/api/admin/stock', {method: 'POST', headers: {...headers, 'Content-Type': 'application/json'}, body: JSON.stringify({sku: product.id, quantity})});
  if (!productResponse.ok || !stockResponse.ok) { message.textContent = 'Could not enable product'; button.disabled = false; return; }
  message.textContent = `${product.name} is live in ${product.category} with ${quantity} units.`;
  await loadProducts();
}

document.querySelector('#product-form').addEventListener('submit', async event => {
  event.preventDefault();
  const response = await fetch('/api/products', {method: 'POST', headers: {...headers, 'Content-Type': 'application/json'}, body: JSON.stringify(Object.fromEntries(new FormData(event.target)))});
  if (!response.ok) { message.textContent = 'Product submission failed'; return; }
  event.target.reset();
  message.textContent = 'Product submitted for review.';
  await loadProducts();
});

await loadProducts();
