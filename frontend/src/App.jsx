import React from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import { Shield, Settings, Search, Home, LogOut, User } from 'lucide-react';
import { useAuth } from './auth/useAuth';
import Configuration from './pages/Configuration';
import Scan from './pages/Scan';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import AccessDenied from './pages/AccessDenied';

function NavItem({ to, icon: Icon, label }) {
  const location = useLocation();
  const isActive = location.pathname === to;

  return (
    <Link
      to={to}
      className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${isActive
          ? 'bg-blue-600 text-white'
          : 'text-gray-300 hover:bg-slate-800 hover:text-white'
        }`}
    >
      <Icon size={20} />
      <span className="font-medium">{label}</span>
    </Link>
  );
}

function UserMenu() {
  const { user, logout } = useAuth();

  if (!user) return null;

  return (
    <div className="p-4 border-t border-slate-800">
      <div className="flex items-center gap-3 mb-3">
        {user.photo ? (
          <img 
            src={user.photo} 
            alt={user.name} 
            className="w-8 h-8 rounded-full object-cover"
          />
        ) : (
          <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center">
            <User size={16} className="text-white" />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">{user.name}</p>
          <p className="text-xs text-slate-400 truncate">{user.email}</p>
        </div>
      </div>
      <button
        onClick={logout}
        className="w-full flex items-center justify-center gap-2 text-slate-400 hover:text-white hover:bg-slate-800 py-2 px-3 rounded-lg transition-colors text-sm"
      >
        <LogOut size={16} />
        Sign out
      </button>
    </div>
  );
}

function Layout({ children }) {
  return (
    <div className="flex h-screen bg-slate-950 text-slate-100 font-sans">
      {/* Sidebar */}
      <div className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col">
        <div className="p-6 flex items-center space-x-3 border-b border-slate-800">
          <Shield className="text-blue-500" size={28} />
          <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
            Code Guardian
          </h1>
        </div>

        <nav className="flex-1 p-4 space-y-2">
          <NavItem to="/" icon={Home} label="Dashboard" />
          <NavItem to="/config" icon={Settings} label="Configuration" />
          <NavItem to="/scan" icon={Search} label="Scan & Detect" />
        </nav>

        <UserMenu />

        <div className="p-4 border-t border-slate-800 text-xs text-slate-500 text-center">
          v1.0.0 Alpha
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto">
        <div className="p-8 max-w-7xl mx-auto">
          {children}
        </div>
      </div>
    </div>
  );
}

function LoadingScreen() {
  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center">
      <div className="text-center">
        <Shield className="w-16 h-16 text-blue-500 mx-auto mb-4 animate-pulse" />
        <p className="text-slate-400">Loading...</p>
      </div>
    </div>
  );
}

function AuthenticatedApp() {
  const { isAuthenticated, isLoading, hasAccess } = useAuth();

  // Show loading screen while checking auth status
  if (isLoading) {
    return <LoadingScreen />;
  }

  // Show login page if not authenticated
  if (!isAuthenticated) {
    return <Login />;
  }

  // Show access denied if authenticated but missing required role
  if (!hasAccess) {
    return <AccessDenied />;
  }

  // User is authenticated and has access
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/config" element={<Configuration />} />
          <Route path="/scan" element={<Scan />} />
        </Routes>
      </Layout>
    </Router>
  );
}

function App() {
  return <AuthenticatedApp />;
}

export default App;
