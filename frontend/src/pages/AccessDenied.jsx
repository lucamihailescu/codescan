import React from 'react';
import { ShieldX, Mail, LogOut, ArrowLeft } from 'lucide-react';
import { useAuth } from '../auth/useAuth';

/**
 * Access Denied Page
 * Displayed when a user is authenticated but lacks the required 'admin' role
 */
function AccessDenied() {
  const { user, roles, logout, supportEmail, requiredRole } = useAuth();

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-slate-900 rounded-2xl shadow-2xl border border-slate-800 p-8 text-center">
        {/* Icon */}
        <div className="mx-auto w-20 h-20 bg-red-500/10 rounded-full flex items-center justify-center mb-6">
          <ShieldX className="w-10 h-10 text-red-500" />
        </div>

        {/* Title */}
        <h1 className="text-2xl font-bold text-white mb-2">Access Denied</h1>
        
        {/* Message */}
        <p className="text-slate-400 mb-6">
          You don't have permission to access this application. 
          The <span className="text-blue-400 font-mono">'{requiredRole}'</span> role is required.
        </p>

        {/* User Info Box */}
        {user && (
          <div className="bg-slate-800/50 rounded-lg p-4 mb-6 text-left">
            <h3 className="text-sm font-medium text-slate-300 mb-2">Signed in as:</h3>
            <div className="flex items-center gap-3">
              {user.photo ? (
                <img 
                  src={user.photo} 
                  alt={user.name} 
                  className="w-10 h-10 rounded-full object-cover"
                />
              ) : (
                <div className="w-10 h-10 bg-slate-600 rounded-full flex items-center justify-center">
                  <span className="text-white text-sm font-medium">
                    {user.name?.charAt(0)?.toUpperCase() || '?'}
                  </span>
                </div>
              )}
              <div>
                <p className="text-white font-medium">{user.name}</p>
                <p className="text-slate-400 text-sm">{user.email}</p>
              </div>
            </div>
            {roles.length > 0 ? (
              <div className="mt-3 pt-3 border-t border-slate-700">
                <span className="text-xs text-slate-500">Your roles: </span>
                <span className="text-xs text-slate-400">{roles.join(', ')}</span>
              </div>
            ) : (
              <div className="mt-3 pt-3 border-t border-slate-700">
                <span className="text-xs text-slate-500">No roles assigned</span>
              </div>
            )}
          </div>
        )}

        {/* Support Contact */}
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4 mb-6">
          <p className="text-slate-300 text-sm mb-2">
            Need access? Contact your administrator:
          </p>
          <a 
            href={`mailto:${supportEmail}?subject=Code Guardian Access Request&body=Hello,%0A%0AI would like to request access to the Code Guardian application.%0A%0AUser: ${user?.name || 'N/A'}%0AEmail: ${user?.email || 'N/A'}%0A%0AThank you.`}
            className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 font-medium transition-colors"
          >
            <Mail className="w-4 h-4" />
            {supportEmail}
          </a>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-3">
          <button
            onClick={logout}
            className="w-full flex items-center justify-center gap-2 bg-slate-700 hover:bg-slate-600 text-white font-medium py-3 px-4 rounded-lg transition-colors"
          >
            <LogOut className="w-4 h-4" />
            Sign out and try a different account
          </button>
          
          <button
            onClick={() => window.location.reload()}
            className="w-full flex items-center justify-center gap-2 text-slate-400 hover:text-white font-medium py-2 px-4 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Retry
          </button>
        </div>

        {/* Footer */}
        <p className="mt-8 text-xs text-slate-600">
          MLP Code Guardian v1.0.0 • Role-based access control enabled
        </p>
      </div>
    </div>
  );
}

export default AccessDenied;
