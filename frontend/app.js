const productsElement = document.querySelector('#products');
const messageElement = document.querySelector('#message');
const adminProductsElement = document.querySelector('#admin-products');
const ordersElement = document.querySelector('#orders');
const cartCountElement = document.querySelector('.cart b');
const sessionLink = document.querySelector('#session-link');
const adminMessage = document.querySelector('#admin-message');
const loginMessage = document.querySelector('#login-message');
let session = JSON.parse(localStorage.getItem('microshop-session') || 'null');

function authHeaders() {
  return session ? {Authorization: `Bearer ${session.token}`} : {};
}

function updateSessionUi() {
  if (sessionLink) sessionLink.textContent = session ? `${session.username} / Sign out` : 'Sign in';
  if (adminMessage) adminMessage.textContent = session?.role === 'admin' ? 'Admin mode: submit products and enable stock.' : 'Sign in as an admin to add products and enable stock.';
}
let catalogProducts = [];
let latestStock = {};
let activeCategory = 'all';

function showMessage(text, kind = '') {
  messageElement.textContent = text;
  messageElement.className = kind;
}

function productCard(product, stock) {
  const card = document.createElement('article');
  card.className = 'product-card';
  const available = stock[product.id] || 0;
  card.innerHTML = `
    <div class="product-image ${product.category.toLowerCase().replaceAll(' ', '-')}" role="img" aria-label="${product.name}"><span>${available > 0 ? 'IN STOCK' : 'OUT OF STOCK'}</span></div>
    <div class="product-top"><span class="category">${product.category}</span><span class="product-id">SKU ${product.id}</span></div>
    <h3>${product.name}</h3>
    <div class="product-bottom"><strong>$${product.price.toFixed(2)}</strong><span>${available} available</span><button type="button" ${available < 1 ? 'disabled' : ''}>Add to order</button></div>`;
  card.querySelector('button').addEventListener('click', () => placeOrder(product.id, card.querySelector('button')));
  return card;
}

function renderCatalog() {
  const visibleProducts = activeCategory === 'all'
    ? catalogProducts
    : catalogProducts.filter(product => product.category.toLowerCase() === activeCategory.toLowerCase());
  productsElement.replaceChildren(...(visibleProducts.length
    ? visibleProducts.map(product => productCard(product, latestStock))
    : [Object.assign(document.createElement('p'), {className: 'empty-state', textContent: `No products in ${activeCategory} yet.`})]));
  document.querySelector('#catalog-title').textContent = activeCategory === 'all' ? 'Popular products' : `${activeCategory} products`;
}

async function loadProducts() {
  try {
    const [productsResponse, stockResponse] = await Promise.all([fetch('/api/products'), fetch('/api/stock')]);
    if (!productsResponse.ok || !stockResponse.ok) throw new Error('Catalog unavailable');
    const products = await productsResponse.json();
    const stock = await stockResponse.json();
    catalogProducts = products;
    latestStock = stock;
    renderCatalog();
  } catch {
    productsElement.innerHTML = '<p class="error">Could not load the catalog. Check the products service.</p>';
  }
}

async function loadOrders() {
  const response = await fetch('/api/order-history');
  if (!response.ok) return;
  const orders = await response.json();
  ordersElement.replaceChildren(...orders.slice(0, 5).map(order => {
    const row = document.createElement('div');
    row.className = 'order-row';
    row.innerHTML = `<strong>${order.order_id}</strong><span>${order.sku} x ${order.quantity}</span><b>${order.status}</b>`;
    return row;
  }));
}

async function loadAdminProducts() {
  if (!adminProductsElement) return;
  const response = await fetch('/api/admin/products', {headers: authHeaders()});
  const products = await response.json();
  adminProductsElement.replaceChildren(...products.map(product => {
    const row = document.createElement('div');
    row.className = 'admin-row';
    row.innerHTML = `<span><strong>${product.name}</strong><small>${product.id} / ${product.status}</small></span>`;
    if (product.status === 'pending') {
      row.innerHTML += '<input class="stock-input" type="number" min="1" value="10" aria-label="Starting stock"><button type="button">Enable</button>';
      row.querySelector('button').addEventListener('click', () => enableProduct(product, row));
    }
    return row;
  }));
}

async function enableProduct(product, row) {
  const button = row.querySelector('button');
  const quantity = Number(row.querySelector('.stock-input').value);
  button.disabled = true;
  try {
    const productResponse = await fetch(`/api/admin/products/${product.id}/enable`, {method: 'PUT', headers: authHeaders()});
    if (!productResponse.ok) throw new Error('Could not enable product');
    const stockResponse = await fetch('/api/admin/stock', {
      method: 'POST', headers: {...authHeaders(), 'Content-Type': 'application/json'},
      body: JSON.stringify({sku: product.id, quantity})
    });
    if (!stockResponse.ok) throw new Error('Could not enable stock');
    showMessage(`${product.name} is live with ${quantity} units`, 'success');
    await Promise.all([loadProducts(), loadAdminProducts()]);
  } catch (error) {
    showMessage(error.message, 'error');
    button.disabled = false;
  }
}

document.querySelector('#product-form')?.addEventListener('submit', async event => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  const response = await fetch('/api/products', {
    method: 'POST', headers: {...authHeaders(), 'Content-Type': 'application/json'}, body: JSON.stringify(data)
  });
  if (!response.ok) {
    showMessage('Product submission failed', 'error');
    return;
  }
  event.target.reset();
  showMessage('Product submitted for admin approval', 'success');
  void loadAdminProducts().catch(() => showMessage('Admin catalog unavailable', 'error'));
});

document.querySelectorAll('[data-category]').forEach(control => {
  control.addEventListener('click', event => {
    event.preventDefault();
    activeCategory = control.dataset.category;
    renderCatalog();
    document.querySelector('#catalog').scrollIntoView({behavior: 'smooth'});
  });
});

async function placeOrder(sku, button) {
  if (!session) {
    window.location.href = '/signin.html';
    return;
  }
  button.disabled = true;
  button.textContent = 'Ordering...';
  try {
    const response = await fetch('/api/orders', {
      method: 'POST',
      headers: {...authHeaders(), 'Content-Type': 'application/json'},
      body: JSON.stringify({sku, quantity: 1})
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Order failed');
    showMessage(`Order successful: ${result.order_id} / Product: ${result.product_id}`, 'success');
    button.textContent = 'Confirmed';
    cartCountElement.textContent = String(Number(cartCountElement.textContent) + 1);
    await Promise.all([loadProducts(), loadOrders()]);
  } catch (error) {
    showMessage(error.message, 'error');
    button.disabled = false;
    button.textContent = 'Order one';
  }
}

await Promise.allSettled([loadProducts(), loadAdminProducts(), loadOrders()]);
setInterval(async () => {
  await Promise.allSettled([loadProducts(), loadAdminProducts(), loadOrders()]);
}, 5000);

document.querySelector('#login-form')?.addEventListener('submit', async event => {
  event.preventDefault();
  const credentials = Object.fromEntries(new FormData(event.target));
  const response = await fetch('/api/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(credentials)});
  const result = await response.json();
  if (!response.ok) { loginMessage.textContent = result.error; return; }
  session = result;
  localStorage.setItem('microshop-session', JSON.stringify(session));
  loginMessage.textContent = `Signed in as ${session.username} (${session.role})`;
  updateSessionUi();
  void loadAdminProducts();
});

sessionLink?.addEventListener('click', event => {
  if (!session) return;
  event.preventDefault();
  session = null;
  localStorage.removeItem('microshop-session');
  loginMessage.textContent = 'Signed out';
  updateSessionUi();
});

updateSessionUi();

const stockEvents = new EventSource('/api/stock/events');
stockEvents.onmessage = event => {
  latestStock = JSON.parse(event.data);
  renderCatalog();
};
stockEvents.onerror = () => showMessage('Live stock connection interrupted; reconnecting...', 'error');
