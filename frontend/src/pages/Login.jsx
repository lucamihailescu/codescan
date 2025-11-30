import React from 'react';
import { Shield, LogIn, Loader2 } from 'lucide-react';
import { useAuth } from '../auth/useAuth';

/**
 * Login Page
 * Displayed when user is not authenticated
 */
function Login() {
  const { login, isLoading, error } = useAuth();

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-900 rounded-2xl shadow-2xl border border-slate-800 p-8 text-center">
        {/* Logo */}
        <div className="mx-auto w-20 h-20 bg-blue-500/10 rounded-full flex items-center justify-center mb-6">
          <Shield className="w-10 h-10 text-blue-500" />
        </div>

        {/* Title */}
        <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent mb-2">
          Code Guardian
        </h1>
        
        <p className="text-slate-400 mb-8">
          Code Security & Protection Solution
        </p>

        {/* Error Message */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6 text-left">
            <p className="text-red-400 text-sm">{error}</p>
          </div>
        )}

        {/* Login Button */}
        <button
          onClick={login}
          disabled={isLoading}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 disabled:cursor-not-allowed text-white font-medium py-3 px-4 rounded-lg transition-colors"
        >
          {isLoading ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              Signing in...
            </>
          ) : (
            <>
              <LogIn className="w-5 h-5" />
              Sign in with Microsoft
            </>
          )}
        </button>

        {/* Info */}
        <p className="mt-6 text-xs text-slate-500">
          Sign in with your organizational Microsoft account to access the DLP dashboard.
        </p>

        {/* Footer */}
        <div className="mt-8 pt-6 border-t border-slate-800">
          <p className="text-xs text-slate-600">
            Secured by Microsoft Entra ID
          </p>
        </div>
      </div>
    </div>
  );
}

export default Login;
