import { useContext } from 'react';
import { AuthContext } from './AuthProvider';

/**
 * Custom hook to use auth context
 */
export const useAuth = () => useContext(AuthContext);

export default useAuth;
