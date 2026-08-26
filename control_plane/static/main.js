// API helpers
async function apiPost(url, data) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // If cookie auth needs CSRF, it will be handled. For now, fetch sends cookies automatically.
    },
    body: JSON.stringify(data)
  });
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.error ? error.error.message : 'API error');
  }
  return await res.json();
}

async function apiGet(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.error ? error.error.message : 'API error');
  }
  return await res.json();
}

// Login functionality
const loginForm = document.getElementById('loginForm');
if (loginForm) {
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    try {
      await apiPost('/api/v1/auth/login', { username, password });
      window.location.href = '/planner.html';
    } catch (err) {
      alert('Login failed: ' + err.message);
    }
  });
}

// Planner functionality
const plannerGrid = document.querySelector('.planner-grid');
if (plannerGrid && !window.location.pathname.includes('index.html')) {
  // Fetch planner snapshot
  apiGet('/api/v1/planner/snapshot').then(data => {
    console.log('Planner snapshot loaded:', data);
    // Render logic would go here. The mockup has static items for now.
  }).catch(err => {
    console.error('Failed to load planner', err);
    if (err.message.includes('unauthorized') || err.message.includes('API error')) {
      window.location.href = '/index.html';
    }
  });
}

// Chat functionality
const chatInputBox = document.querySelector('.chat-input-box');
if (chatInputBox) {
  // This is a mockup chat page. Just check authentication.
  apiGet('/api/v1/me').then(data => {
    console.log('User logged in:', data.account.username);
  }).catch(err => {
    console.error('Failed to authenticate', err);
    window.location.href = '/index.html';
  });
}
