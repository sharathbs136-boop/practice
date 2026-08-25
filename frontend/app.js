const productsElement = document.querySelector('#products');
const messageElement = document.querySelector('#message');
const adminProductsElement = document.querySelector('#admin-products');
const ordersElement = document.querySelector('#orders');
const cartCountElement = document.querySelector('.cart b');
const cartButton = document.querySelector('.cart');
const cartDrawer = document.querySelector('#cart-drawer');
const cartItemsElement = document.querySelector('#cart-items');
const cartTotalElement = document.querySelector('#cart-total');
const checkoutButton = document.querySelector('#checkout-button');
const cartMessageElement = document.querySelector('#cart-message');
const paymentTokenElement = document.querySelector('#payment-token');
const cartBackdrop = document.querySelector('.cart-backdrop');
const searchForm = document.querySelector('#search-form');
const searchInput = document.querySelector('#search-input');
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
let cart = JSON.parse(localStorage.getItem('microshop-cart') || '[]');
let searchTerm = '';

function showMessage(text, kind = '') {
  messageElement.textContent = text;
  messageElement.className = kind;
}

function saveCart() {
  localStorage.setItem('microshop-cart', JSON.stringify(cart));
  renderCart();
}

function cartQuantity() {
  return cart.reduce((total, item) => total + item.quantity, 0);
}

function renderCart() {
  const count = cartQuantity();
  cartCountElement.textContent = String(count);
  checkoutButton.disabled = !cart.length;
  cartTotalElement.textContent = `$${cart.reduce((total, item) => total + item.price * item.quantity, 0).toFixed(2)}`;
  cartItemsElement.replaceChildren(...(cart.length ? cart.map(item => {
    const row = document.createElement('div');
    row.className = 'cart-item';
    row.innerHTML = `<div><strong>${item.name}</strong><small>$${item.price.toFixed(2)} each</small></div><div class="cart-item-controls"><button type="button" data-action="decrease" aria-label="Decrease ${item.name}">−</button><b>${item.quantity}</b><button type="button" data-action="increase" aria-label="Increase ${item.name}">+</button><button type="button" data-action="remove" aria-label="Remove ${item.name}">×</button></div>`;
    row.querySelectorAll('button').forEach(button => button.addEventListener('click', () => changeCart(item.id, button.dataset.action)));
    return row;
  }) : [Object.assign(document.createElement('p'), {className: 'empty-state', textContent: 'Your cart is empty.'})]));
}

function changeCart(productId, action) {
  const item = cart.find(entry => entry.id === productId);
  if (!item) return;
  if (action === 'remove' || (action === 'decrease' && item.quantity === 1)) cart = cart.filter(entry => entry.id !== productId);
  else if (action === 'decrease') item.quantity -= 1;
  else if (action === 'increase' && item.quantity < (latestStock[productId] || 0)) item.quantity += 1;
  else if (action === 'increase') cartMessageElement.textContent = 'Quantity is limited by live stock.';
  saveCart();
}

function addToCart(product) {
  if (!session) { window.location.href = '/signin.html'; return; }
  const item = cart.find(entry => entry.id === product.id);
  if (item) {
    if (item.quantity >= (latestStock[product.id] || 0)) { showMessage('That quantity is not available', 'error'); return; }
    item.quantity += 1;
  } else cart.push({id: product.id, name: product.name, price: product.price, quantity: 1});
  saveCart();
  showMessage(`${product.name} added to your cart`, 'success');
  openCart();
}

function openCart() {
  cartDrawer.classList.add('open');
  cartDrawer.setAttribute('aria-hidden', 'false');
  cartButton.setAttribute('aria-expanded', 'true');
  cartBackdrop.classList.add('visible');
}

function closeCart() {
  cartDrawer.classList.remove('open');
  cartDrawer.setAttribute('aria-hidden', 'true');
  cartButton.setAttribute('aria-expanded', 'false');
  cartBackdrop.classList.remove('visible');
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
  card.querySelector('button').addEventListener('click', () => addToCart(product));
  return card;
}

function renderCatalog() {
  const visibleProducts = activeCategory === 'all'
    ? catalogProducts
    : catalogProducts.filter(product => product.category.toLowerCase() === activeCategory.toLowerCase());
  const searchedProducts = visibleProducts.filter(product => `${product.name} ${product.category} ${product.id}`.toLowerCase().includes(searchTerm));
  productsElement.replaceChildren(...(visibleProducts.length
    ? (searchedProducts.length ? searchedProducts.map(product => productCard(product, latestStock)) : [Object.assign(document.createElement('p'), {className: 'empty-state', textContent: `No products match "${searchTerm}".`})])
    : [Object.assign(document.createElement('p'), {className: 'empty-state', textContent: `No products in ${activeCategory} yet.`})]));
  document.querySelector('#catalog-title').textContent = searchTerm ? `Results for "${searchTerm}"` : activeCategory === 'all' ? 'Popular products' : `${activeCategory} products`;
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

async function checkout() {
  if (!session) { window.location.href = '/signin.html'; return; }
  checkoutButton.disabled = true;
  cartMessageElement.textContent = 'Processing order...';
  const completed = [];
  try {
    for (const item of cart) {
      const response = await fetch('/api/orders', {method: 'POST', headers: {...authHeaders(), 'Content-Type': 'application/json'}, body: JSON.stringify({sku: item.id, quantity: item.quantity, amount: item.price * item.quantity, payment_token: paymentTokenElement.value.trim()})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `${item.name} is unavailable`);
      completed.push({orderId: result.order_id, sku: item.id});
    }
    cart = [];
    saveCart();
    cartMessageElement.textContent = `${completed.length} order${completed.length === 1 ? '' : 's'} confirmed.`;
    showMessage(`Order confirmed: ${completed.map(order => order.orderId).join(', ')}`, 'success');
    await Promise.all([loadProducts(), loadOrders()]);
  } catch (error) {
    cartMessageElement.textContent = error.message;
    cartMessageElement.className = 'error';
    if (completed.length) cart = cart.filter(item => !completed.some(order => order.sku === item.id));
    renderCart();
  } finally {
    checkoutButton.disabled = !cart.length;
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
renderCart();
searchForm.addEventListener('submit', event => {
  event.preventDefault();
  searchTerm = searchInput.value.trim().toLowerCase();
  renderCatalog();
  document.querySelector('#catalog').scrollIntoView({behavior: 'smooth'});
});
searchInput.addEventListener('input', () => {
  searchTerm = searchInput.value.trim().toLowerCase();
  renderCatalog();
});
cartButton.addEventListener('click', () => cartDrawer.classList.contains('open') ? closeCart() : openCart());
document.querySelector('.cart-close').addEventListener('click', closeCart);
cartBackdrop.addEventListener('click', closeCart);
checkoutButton.addEventListener('click', checkout);

const stockEvents = new EventSource('/api/stock/events');
stockEvents.onmessage = event => {
  latestStock = JSON.parse(event.data);
  cart = cart.filter(item => {
    if (latestStock[item.id] === undefined) return false;
    item.quantity = Math.min(item.quantity, latestStock[item.id]);
    return item.quantity > 0;
  });
  saveCart();
  renderCatalog();
};
stockEvents.onerror = () => showMessage('Live stock connection interrupted; reconnecting...', 'error');

const productEvents = new EventSource('/api/products/events');
productEvents.onmessage = event => {
  catalogProducts = JSON.parse(event.data);
  renderCatalog();
};
productEvents.onerror = () => showMessage('Live catalog connection interrupted; reconnecting...', 'error');

const orderEvents = new EventSource('/api/order-events');
orderEvents.onmessage = event => {
  const orders = JSON.parse(event.data);
  ordersElement.replaceChildren(...orders.slice(0, 5).map(order => {
    const row = document.createElement('div');
    row.className = 'order-row';
    row.innerHTML = `<strong>${order.order_id}</strong><span>${order.sku} x ${order.quantity}</span><b>${order.status}</b>`;
    return row;
  }));
};
orderEvents.onerror = () => showMessage('Live order connection interrupted; reconnecting...', 'error');
