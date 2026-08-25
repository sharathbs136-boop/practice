const session = JSON.parse(localStorage.getItem('microshop-session') || 'null');
const message = document.querySelector('#admin-message');
const ordersElement = document.querySelector('#admin-orders');
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
    row.innerHTML += `<input class="stock-input" type="number" min="1" value="${product.status === 'pending' ? 10 : 5}" aria-label="${product.status === 'pending' ? 'Starting stock' : 'Stock to add'}"><button type="button">${product.status === 'pending' ? 'Enable product' : 'Add stock'}</button>`;
    row.querySelector('button').addEventListener('click', () => product.status === 'pending' ? enableProduct(product, row) : restockProduct(product, row));
    return row;
  }));
}

async function loadOrders() {
  const response = await fetch('/api/admin/orders', {headers});
  if (!response.ok) return;
  const orders = await response.json();
  ordersElement.replaceChildren(...(orders.length ? orders.map(order => {
    const row = document.createElement('div');
    row.className = 'admin-row';
    row.innerHTML = `<span><strong>${order.order_id}</strong><small>${order.sku} / ${order.quantity} units</small></span><select aria-label="Status for ${order.order_id}">${['confirmed', 'processing', 'shipped', 'delivered', 'cancelled'].map(status => `<option ${status === order.status ? 'selected' : ''}>${status}</option>`).join('')}</select>`;
    row.querySelector('select').addEventListener('change', event => updateOrderStatus(order.order_id, event.target.value));
    return row;
  }) : [Object.assign(document.createElement('p'), {className: 'empty-state', textContent: 'No orders yet.'})]));
}

async function updateOrderStatus(orderId, status) {
  const response = await fetch(`/api/admin/orders/${orderId}/status`, {method: 'PUT', headers: {...headers, 'Content-Type': 'application/json'}, body: JSON.stringify({status})});
  message.textContent = response.ok ? `${orderId} moved to ${status}.` : 'Could not update order status.';
}

async function restockProduct(product, row) {
  const button = row.querySelector('button');
  const quantity = Number(row.querySelector('.stock-input').value);
  button.disabled = true;
  const response = await fetch('/api/admin/stock/restock', {method: 'POST', headers: {...headers, 'Content-Type': 'application/json'}, body: JSON.stringify({sku: product.id, quantity})});
  if (!response.ok) { message.textContent = 'Could not add stock'; button.disabled = false; return; }
  const result = await response.json();
  message.textContent = `${product.name}: ${result.added} units added. Total stock: ${result.quantity}.`;
  button.disabled = false;
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

await Promise.all([loadProducts(), loadOrders()]);
const orderEvents = new EventSource('/api/order-events');
orderEvents.onmessage = () => loadOrders();
