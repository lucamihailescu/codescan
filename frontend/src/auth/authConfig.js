/**
 * Microsoft Entra ID (Azure AD) Authentication Configuration
 * 
 * This configuration uses environment variables for security.
 * Create a .env file in the frontend directory with your Entra ID settings.
 */

/**
 * MSAL configuration for Microsoft Entra ID
 */
export const msalConfig = {
  auth: {
    clientId: import.meta.env.VITE_ENTRA_CLIENT_ID || '',
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_ENTRA_TENANT_ID || 'common'}`,
    redirectUri: import.meta.env.VITE_ENTRA_REDIRECT_URI || window.location.origin,
    postLogoutRedirectUri: import.meta.env.VITE_ENTRA_POST_LOGOUT_URI || window.location.origin,
    navigateToLoginRequestUrl: true,
  },
  cache: {
    cacheLocation: 'sessionStorage',
    storeAuthStateInCookie: false,
  },
  system: {
    loggerOptions: {
      loggerCallback: (level, message, containsPii) => {
        if (containsPii) return;
        switch (level) {
          case 0: // Error
            console.error(message);
            break;
          case 1: // Warning
            console.warn(message);
            break;
          case 2: // Info
            console.info(message);
            break;
          case 3: // Verbose
            console.debug(message);
            break;
        }
      },
      logLevel: import.meta.env.DEV ? 3 : 1, // Verbose in dev, Warning in prod
    },
  },
};

/**
 * Scopes for ID token (used during login)
 */
export const loginRequest = {
  scopes: ['openid', 'profile', 'email', 'User.Read'],
};

/**
 * Scopes for Microsoft Graph API (user photo)
 */
export const graphRequest = {
  scopes: ['User.Read'],
};

/**
 * Scopes for API access token
 */
export const apiRequest = {
  scopes: [import.meta.env.VITE_ENTRA_API_SCOPE || 'api://default/.default'],
};

/**
 * Required role for accessing the application
 */
export const REQUIRED_ROLE = 'admin';

/**
 * Support email for access denied inquiries
 */
export const SUPPORT_EMAIL = 'foo@bar.com';

/**
 * Check if user has the required role
 * @param {object} account - MSAL account object
 * @returns {boolean} - Whether user has the required role
 */
export const hasRequiredRole = (account) => {
  if (!account) return false;
  
  // Roles can be in idTokenClaims.roles or account.idTokenClaims.roles
  const claims = account.idTokenClaims || {};
  const roles = claims.roles || [];
  
  return roles.includes(REQUIRED_ROLE);
};

/**
 * Get user roles from account
 * @param {object} account - MSAL account object  
 * @returns {string[]} - Array of user roles
 */
export const getUserRoles = (account) => {
  if (!account) return [];
  const claims = account.idTokenClaims || {};
  return claims.roles || [];
};
