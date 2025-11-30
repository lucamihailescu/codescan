import React, { createContext, useContext, useEffect, useState } from 'react';
import { useMsal, useIsAuthenticated, useAccount } from '@azure/msal-react';
import { InteractionStatus } from '@azure/msal-browser';
import { loginRequest, graphRequest, hasRequiredRole, getUserRoles, REQUIRED_ROLE, SUPPORT_EMAIL } from './authConfig';
import { initializeApiClient, clearApiClient } from '../api/client';

/**
 * Auth Context for sharing authentication state across the app
 */
export const AuthContext = createContext({
  isAuthenticated: false,
  isLoading: true,
  hasAccess: false,
  user: null,
  roles: [],
  login: () => {},
  logout: () => {},
  error: null,
});

/**
 * Fetch user photo from Microsoft Graph API
 */
async function fetchUserPhoto(instance, account) {
  try {
    // Get access token for Graph API
    const response = await instance.acquireTokenSilent({
      ...graphRequest,
      account: account,
    });

    // Fetch user photo from Graph API
    const photoResponse = await fetch('https://graph.microsoft.com/v1.0/me/photo/$value', {
      headers: {
        Authorization: `Bearer ${response.accessToken}`,
      },
    });

    if (photoResponse.ok) {
      const blob = await photoResponse.blob();
      return URL.createObjectURL(blob);
    }
    return null;
  } catch (error) {
    // User might not have a photo or token acquisition failed
    console.debug('Could not fetch user photo:', error.message);
    return null;
  }
}

/**
 * Auth Provider Component
 * Wraps the application and provides authentication state and methods
 */
export const AuthProvider = ({ children }) => {
  const { instance, accounts, inProgress } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const account = useAccount(accounts[0] || {});
  
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [userPhoto, setUserPhoto] = useState(null);

  // Check if user has the required admin role
  const hasAccess = isAuthenticated && hasRequiredRole(account);
  const roles = getUserRoles(account);

  // User info
  const user = account ? {
    name: account.name || account.username,
    email: account.username,
    roles: roles,
    photo: userPhoto,
  } : null;

  useEffect(() => {
    // Update loading state based on MSAL interaction status
    if (inProgress === InteractionStatus.None) {
      setIsLoading(false);
    }
  }, [inProgress]);

  // Fetch user photo when authenticated
  useEffect(() => {
    if (isAuthenticated && account && inProgress === InteractionStatus.None) {
      // Initialize API client for authenticated requests
      initializeApiClient(instance, account);
      
      fetchUserPhoto(instance, account).then(photoUrl => {
        setUserPhoto(photoUrl);
      });
    } else {
      clearApiClient();
    }
  }, [isAuthenticated, account, instance, inProgress]);

  // Cleanup photo URL on unmount
  useEffect(() => {
    return () => {
      if (userPhoto) {
        URL.revokeObjectURL(userPhoto);
      }
    };
  }, [userPhoto]);

  /**
   * Initiate login flow
   */
  const login = async () => {
    setError(null);
    try {
      await instance.loginRedirect(loginRequest);
    } catch (err) {
      console.error('Login failed:', err);
      setError(err.message || 'Login failed');
    }
  };

  /**
   * Initiate logout flow
   */
  const logout = async () => {
    try {
      clearApiClient();
      await instance.logoutRedirect({
        postLogoutRedirectUri: window.location.origin,
      });
    } catch (err) {
      console.error('Logout failed:', err);
    }
  };

  const contextValue = {
    isAuthenticated,
    isLoading: isLoading || inProgress !== InteractionStatus.None,
    hasAccess,
    user,
    roles,
    login,
    logout,
    error,
    requiredRole: REQUIRED_ROLE,
    supportEmail: SUPPORT_EMAIL,
  };

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthProvider;
