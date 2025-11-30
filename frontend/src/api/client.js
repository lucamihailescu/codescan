/**
 * API Client with Entra ID Authentication
 * 
 * Provides authenticated API calls using the user's Entra ID bearer token.
 */
import axios from 'axios';

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
export const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

let msalInstance = null;
let accountInfo = null;

/**
 * Initialize the API client with MSAL instance
 * Call this after MSAL is initialized in AuthProvider
 */
export function initializeApiClient(msal, account) {
  msalInstance = msal;
  accountInfo = account;
}

/**
 * Clear the API client authentication
 * Call this on logout
 */
export function clearApiClient() {
  msalInstance = null;
  accountInfo = null;
}

/**
 * Get the current access token, acquiring a new one if needed
 */
async function getAccessToken() {
  if (!msalInstance || !accountInfo) {
    console.debug('[API Client] No MSAL instance or account, skipping token acquisition');
    return null; // No auth configured, anonymous access
  }

  try {
    // Use the API scope for backend access
    // Try api://{clientId}/access_as_user first, fall back to .default
    const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID;
    
    if (!clientId) {
      console.debug('[API Client] No client ID configured');
      return null;
    }

    // Try to get token with custom scope first, then fallback to .default
    const scopeOptions = [
      [`api://${clientId}/access_as_user`],
      [`api://${clientId}/.default`],
      [`${clientId}/.default`],
    ];

    for (const scopes of scopeOptions) {
      try {
        console.debug('[API Client] Trying scopes:', scopes);
        const response = await msalInstance.acquireTokenSilent({
          scopes,
          account: accountInfo,
        });
        console.debug('[API Client] Token acquired successfully');
        return response.accessToken;
      } catch (scopeError) {
        console.debug('[API Client] Scope failed:', scopes, scopeError.message);
        continue;
      }
    }
    
    console.warn('[API Client] All scope attempts failed');
    return null;
  } catch (error) {
    console.error('[API Client] Failed to acquire token:', error);
    return null;
  }
}

/**
 * Configured axios instance with authentication interceptor
 */
export const axiosInstance = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor to include auth token
axiosInstance.interceptors.request.use(
  async (config) => {
    const token = await getAccessToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Add response interceptor for error handling
axiosInstance.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      console.error('Authentication error - token may be expired');
      // Could trigger re-authentication here
    }
    return Promise.reject(error);
  }
);

/**
 * Make an authenticated API request using fetch
 */
export async function apiRequest(endpoint, options = {}) {
  const token = await getAccessToken();
  
  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  // Handle empty responses
  const text = await response.text();
  if (!text) {
    return null;
  }
  
  return JSON.parse(text);
}

/**
 * API helper methods using fetch
 */
export const api = {
  get: (endpoint) => apiRequest(endpoint, { method: 'GET' }),
  
  post: (endpoint, data) => apiRequest(endpoint, {
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
  }),
  
  put: (endpoint, data) => apiRequest(endpoint, {
    method: 'PUT',
    body: JSON.stringify(data),
  }),
  
  delete: (endpoint) => apiRequest(endpoint, { method: 'DELETE' }),
};

export default api;
