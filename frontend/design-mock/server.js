const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const path = require('path');

const app = express();
const PORT = 3000;
const API = 'http://localhost:8000';

// Proxy all API calls to the backend
app.use(['/chat', '/tasks', '/calendar', '/preferences', '/billing', '/api-keys', '/auth', '/health'],
  createProxyMiddleware({ target: API, changeOrigin: true })
);

// Serve the exact static mock files
app.use(express.static(path.join(__dirname)));

// Route / to index.html (already default for express.static)
app.listen(PORT, () => {
  console.log(`scedly frontend → http://localhost:${PORT}`);
  console.log(`API proxy → ${API}`);
});
