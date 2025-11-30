import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Database, Search, ShieldCheck, FolderSync, Activity, Clock, CheckCircle, XCircle, Loader, FolderOpen, X, Copy, Check, ChevronDown } from 'lucide-react';
import { useAuth } from '../auth/useAuth';
import api from '../api/client';

function StatCard({ icon: Icon, label, value, subtitle, color }) {
    return (
        <div className="bg-slate-900 border border-slate-800 p-6 rounded-xl flex items-center space-x-4">
            <div className={`p-3 rounded-lg bg-opacity-20 ${color.bg} ${color.text}`}>
                <Icon size={24} />
            </div>
            <div>
                <p className="text-slate-400 text-sm font-medium">{label}</p>
                <p className="text-2xl font-bold text-white">{value}</p>
                {subtitle && <p className="text-xs text-slate-500 mt-1">{subtitle}</p>}
            </div>
        </div>
    );
}

function IndexOperationModal({ operation, onClose }) {
    const [copied, setCopied] = useState(null);

    if (!operation) return null;

    const copyToClipboard = (text, field) => {
        navigator.clipboard.writeText(text);
        setCopied(field);
        setTimeout(() => setCopied(null), 2000);
    };

    const StatusIcon = operation.status === 'completed' ? CheckCircle 
        : operation.status === 'error' ? XCircle 
        : operation.status === 'running' ? Loader 
        : Clock;
    const statusColor = operation.status === 'completed' ? 'text-emerald-400' 
        : operation.status === 'error' ? 'text-red-400' 
        : operation.status === 'running' ? 'text-blue-400' 
        : 'text-slate-400';
    const statusBg = operation.status === 'completed' ? 'bg-emerald-500/20' 
        : operation.status === 'error' ? 'bg-red-500/20' 
        : operation.status === 'running' ? 'bg-blue-500/20' 
        : 'bg-slate-500/20';

    // Calculate duration
    let duration = '--';
    if (operation.started_at && operation.completed_at) {
        const start = new Date(operation.started_at);
        const end = new Date(operation.completed_at);
        const diffMs = end - start;
        const diffSecs = Math.floor(diffMs / 1000);
        if (diffSecs < 60) {
            duration = `${diffSecs} seconds`;
        } else if (diffSecs < 3600) {
            duration = `${Math.floor(diffSecs / 60)}m ${diffSecs % 60}s`;
        } else {
            duration = `${Math.floor(diffSecs / 3600)}h ${Math.floor((diffSecs % 3600) / 60)}m`;
        }
    } else if (operation.status === 'running') {
        duration = 'In progress...';
    }

    const DetailRow = ({ label, value, mono = false, copyable = false }) => (
        <div className="flex items-start justify-between py-2 border-b border-slate-800 last:border-0">
            <span className="text-slate-400 text-sm">{label}</span>
            <div className="flex items-center gap-2">
                <span className={`text-sm text-slate-200 ${mono ? 'font-mono' : ''} text-right max-w-xs truncate`} title={value}>
                    {value || '--'}
                </span>
                {copyable && value && (
                    <button
                        onClick={() => copyToClipboard(value, label)}
                        className="text-slate-500 hover:text-slate-300 transition"
                        title="Copy to clipboard"
                    >
                        {copied === label ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                    </button>
                )}
            </div>
        </div>
    );

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={onClose}>
            <div 
                className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto"
                onClick={e => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b border-slate-800">
                    <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg ${statusBg}`}>
                            <StatusIcon size={20} className={`${statusColor} ${operation.status === 'running' ? 'animate-spin' : ''}`} />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-white">Index Operation Details</h3>
                            <span className={`text-sm capitalize ${statusColor}`}>{operation.status}</span>
                        </div>
                    </div>
                    <button 
                        onClick={onClose}
                        className="p-2 hover:bg-slate-800 rounded-lg transition"
                    >
                        <X size={20} className="text-slate-400" />
                    </button>
                </div>

                {/* Content */}
                <div className="p-4 space-y-1">
                    <DetailRow label="Index ID" value={operation.index_id} mono copyable />
                    <DetailRow label="Directory Path" value={operation.directory_path} mono copyable />
                    <DetailRow label="Status" value={operation.status} />
                    <DetailRow label="Total Files" value={operation.total_files?.toString()} />
                    <DetailRow label="Files Indexed" value={operation.files_indexed?.toString()} />
                    <DetailRow label="Files Skipped" value={operation.files_skipped?.toString()} />
                    <DetailRow 
                        label="Started At" 
                        value={operation.started_at ? new Date(operation.started_at).toLocaleString() : null} 
                    />
                    <DetailRow 
                        label="Completed At" 
                        value={operation.completed_at ? new Date(operation.completed_at).toLocaleString() : null} 
                    />
                    <DetailRow label="Duration" value={duration} />
                    
                    {operation.error_message && (
                        <div className="mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                            <p className="text-sm text-red-400 font-medium mb-1">Error Message</p>
                            <p className="text-sm text-red-300 font-mono">{operation.error_message}</p>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-4 border-t border-slate-800 flex justify-end">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition"
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}

export default function Dashboard() {
    const { user } = useAuth();
    const [stats, setStats] = useState({
        indexed_files: '--',
        index_operations: '--',
        total_files_indexed: '--',
        scans_performed: '--',
        threats_detected: '--',
        storage_backend: '--'
    });
    const [poolStats, setPoolStats] = useState(null);
    const [indexOperations, setIndexOperations] = useState([]);
    const [loadingOperations, setLoadingOperations] = useState(true);
    const [selectedOperation, setSelectedOperation] = useState(null);
    const [operationsCollapsed, setOperationsCollapsed] = useState(false);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [statsData, poolData, opsData] = await Promise.all([
                    api.get('/stats'),
                    api.get('/pool-stats').catch(() => null),
                    api.get('/index-operations').catch(() => [])
                ]);
                setStats(statsData);
                setPoolStats(poolData);
                setIndexOperations(opsData || []);
            } catch (error) {
                console.error('Failed to fetch dashboard data:', error);
            } finally {
                setLoadingOperations(false);
            }
        };
        fetchData();
    }, []);

    // Get first name from full name
    const firstName = user?.name?.split(' ')[0] || 'Back';

    return (
        <div className="space-y-8">
            <div>
                <h2 className="text-3xl font-bold text-white mb-2">Welcome Back, {firstName}</h2>
                <p className="text-slate-400">Monitor and protect your sensitive data assets.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <StatCard
                    icon={Database}
                    label="Indexed Files"
                    value={stats.indexed_files}
                    color={{ bg: 'bg-blue-500', text: 'text-blue-400' }}
                />
                <StatCard
                    icon={FolderSync}
                    label="Index Operations"
                    value={stats.index_operations}
                    subtitle={stats.total_files_indexed !== '--' ? `${stats.total_files_indexed} files processed` : null}
                    color={{ bg: 'bg-cyan-500', text: 'text-cyan-400' }}
                />
                <StatCard
                    icon={Search}
                    label="Scans Performed"
                    value={stats.scans_performed}
                    color={{ bg: 'bg-purple-500', text: 'text-purple-400' }}
                />
                <StatCard
                    icon={ShieldCheck}
                    label="Threats Detected"
                    value={stats.threats_detected}
                    color={{ bg: 'bg-emerald-500', text: 'text-emerald-400' }}
                />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-xl font-bold text-white mb-4">Quick Actions</h3>
                    <div className="space-y-3">
                        <Link to="/config" className="block w-full p-4 bg-slate-800 hover:bg-slate-700 rounded-lg transition text-center font-medium text-blue-400">
                            Manage Index
                        </Link>
                        <Link to="/scan" className="block w-full p-4 bg-blue-600 hover:bg-blue-700 rounded-lg transition text-center font-medium text-white">
                            Start New Scan
                        </Link>
                    </div>
                </div>

                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <h3 className="text-xl font-bold text-white mb-4">System Status</h3>
                    <div className="flex items-center space-x-2 text-emerald-400">
                        <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
                        <span>System Operational</span>
                    </div>
                    <p className="mt-2 text-slate-400 text-sm">
                        Engine ready. Database connected.
                    </p>
                    <div className="mt-4 pt-4 border-t border-slate-800 space-y-3">
                        <div className="flex items-center justify-between">
                            <span className="text-slate-400 text-sm">Storage Backend</span>
                            <span className={`text-sm font-medium px-2 py-1 rounded ${
                                stats.storage_backend === 'redis' 
                                    ? 'bg-red-500/20 text-red-400' 
                                    : stats.storage_backend === 'sqlite'
                                    ? 'bg-blue-500/20 text-blue-400'
                                    : 'bg-slate-700 text-slate-400'
                            }`}>
                                {stats.storage_backend === '--' ? '--' : stats.storage_backend.toUpperCase()}
                            </span>
                        </div>
                        {poolStats?.sqlite && (
                            <div className="flex items-center justify-between">
                                <span className="text-slate-400 text-sm flex items-center gap-1">
                                    <Activity size={12} />
                                    Pool Connections
                                </span>
                                <span className="text-sm font-mono text-slate-300">
                                    {poolStats.sqlite.checked_out}/{poolStats.sqlite.pool_size}
                                </span>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Index Operations Summary */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <button 
                    className="flex items-center justify-between w-full text-left"
                    onClick={() => setOperationsCollapsed(!operationsCollapsed)}
                >
                    <h3 className="text-xl font-bold text-white flex items-center gap-2">
                        <FolderSync size={20} className="text-cyan-400" />
                        Recent Index Operations
                    </h3>
                    <div className="flex items-center gap-3">
                        <span className="text-sm text-slate-400">
                            {indexOperations.length} operation{indexOperations.length !== 1 ? 's' : ''}
                        </span>
                        <ChevronDown 
                            size={20} 
                            className={`text-slate-400 transition-transform duration-200 ${operationsCollapsed ? '-rotate-90' : ''}`} 
                        />
                    </div>
                </button>
                
                <div className={`transition-all duration-200 overflow-hidden ${operationsCollapsed ? 'max-h-0 opacity-0 mt-0' : 'max-h-[2000px] opacity-100 mt-4'}`}>
                
                {loadingOperations ? (
                    <div className="flex items-center justify-center py-8">
                        <Loader className="animate-spin text-slate-400" size={24} />
                    </div>
                ) : indexOperations.length === 0 ? (
                    <div className="text-center py-8">
                        <FolderOpen size={48} className="mx-auto text-slate-600 mb-3" />
                        <p className="text-slate-400">No indexing operations yet</p>
                        <p className="text-sm text-slate-500 mt-1">
                            Go to <Link to="/config" className="text-blue-400 hover:underline">Configuration</Link> to start indexing
                        </p>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead>
                                <tr className="border-b border-slate-800">
                                    <th className="text-left py-3 px-4 text-slate-400 text-sm font-medium">Status</th>
                                    <th className="text-left py-3 px-4 text-slate-400 text-sm font-medium">Directory</th>
                                    <th className="text-right py-3 px-4 text-slate-400 text-sm font-medium">Files</th>
                                    <th className="text-right py-3 px-4 text-slate-400 text-sm font-medium">Indexed</th>
                                    <th className="text-right py-3 px-4 text-slate-400 text-sm font-medium">Skipped</th>
                                    <th className="text-left py-3 px-4 text-slate-400 text-sm font-medium">Started</th>
                                    <th className="text-left py-3 px-4 text-slate-400 text-sm font-medium">Duration</th>
                                </tr>
                            </thead>
                            <tbody>
                                {indexOperations.slice(0, 10).map((op) => {
                                    const StatusIcon = op.status === 'completed' ? CheckCircle 
                                        : op.status === 'error' ? XCircle 
                                        : op.status === 'running' ? Loader 
                                        : Clock;
                                    const statusColor = op.status === 'completed' ? 'text-emerald-400' 
                                        : op.status === 'error' ? 'text-red-400' 
                                        : op.status === 'running' ? 'text-blue-400' 
                                        : 'text-slate-400';
                                    
                                    // Calculate duration
                                    let duration = '--';
                                    if (op.started_at && op.completed_at) {
                                        const start = new Date(op.started_at);
                                        const end = new Date(op.completed_at);
                                        const diffMs = end - start;
                                        const diffSecs = Math.floor(diffMs / 1000);
                                        if (diffSecs < 60) {
                                            duration = `${diffSecs}s`;
                                        } else if (diffSecs < 3600) {
                                            duration = `${Math.floor(diffSecs / 60)}m ${diffSecs % 60}s`;
                                        } else {
                                            duration = `${Math.floor(diffSecs / 3600)}h ${Math.floor((diffSecs % 3600) / 60)}m`;
                                        }
                                    } else if (op.status === 'running') {
                                        duration = 'In progress...';
                                    }
                                    
                                    // Format start time
                                    const startTime = op.started_at 
                                        ? new Date(op.started_at).toLocaleString()
                                        : '--';
                                    
                                    // Truncate path for display
                                    const displayPath = op.directory_path?.length > 40 
                                        ? '...' + op.directory_path.slice(-37)
                                        : op.directory_path || '--';
                                    
                                    return (
                                        <tr 
                                            key={op.index_id} 
                                            className="border-b border-slate-800/50 hover:bg-slate-800/30 cursor-pointer transition"
                                            onClick={() => setSelectedOperation(op)}
                                        >
                                            <td className="py-3 px-4">
                                                <div className="flex items-center gap-2">
                                                    <StatusIcon 
                                                        size={16} 
                                                        className={`${statusColor} ${op.status === 'running' ? 'animate-spin' : ''}`} 
                                                    />
                                                    <span className={`text-sm capitalize ${statusColor}`}>
                                                        {op.status}
                                                    </span>
                                                </div>
                                            </td>
                                            <td className="py-3 px-4">
                                                <span className="text-sm text-slate-300 font-mono" title={op.directory_path}>
                                                    {displayPath}
                                                </span>
                                            </td>
                                            <td className="py-3 px-4 text-right">
                                                <span className="text-sm text-slate-300">{op.total_files ?? '--'}</span>
                                            </td>
                                            <td className="py-3 px-4 text-right">
                                                <span className="text-sm text-emerald-400">{op.files_indexed ?? '--'}</span>
                                            </td>
                                            <td className="py-3 px-4 text-right">
                                                <span className="text-sm text-slate-400">{op.files_skipped ?? '--'}</span>
                                            </td>
                                            <td className="py-3 px-4">
                                                <span className="text-sm text-slate-400">{startTime}</span>
                                            </td>
                                            <td className="py-3 px-4">
                                                <span className="text-sm text-slate-300">{duration}</span>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                        {indexOperations.length > 10 && (
                            <div className="text-center py-3 text-sm text-slate-400">
                                Showing 10 of {indexOperations.length} operations
                            </div>
                        )}
                    </div>
                )}
                </div>
            </div>

            {/* Modal for operation details */}
            {selectedOperation && (
                <IndexOperationModal 
                    operation={selectedOperation} 
                    onClose={() => setSelectedOperation(null)} 
                />
            )}
        </div>
    );
}
