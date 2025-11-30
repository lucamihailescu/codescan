import React, { useState, useEffect, useRef } from 'react';
import { axiosInstance as axios, API_URL, WS_URL } from '../api/client';
import { FolderPlus, FileText, RefreshCw, CheckCircle, Loader2, FolderOpen, Settings, Shield, AlertTriangle, ChevronDown, Database, Cpu, Server, Zap, HardDrive, Trash2, X, FileX, Plus } from 'lucide-react';

function ProgressBar({ progress }) {
    return (
        <div className="mt-6 bg-slate-950 rounded-lg p-4 border border-slate-700">
            <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-slate-300">
                    {progress.status === 'counting' ? 'Counting files...' : 
                     progress.status === 'processing' ? 'Indexing files...' :
                     progress.status === 'completed' ? 'Indexing completed!' : 'Preparing...'}
                </span>
                <span className="text-sm text-slate-400">
                    {progress.files_processed} / {progress.total_files} files
                </span>
            </div>
            
            <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
                <div 
                    className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 transition-all duration-300 ease-out"
                    style={{ width: `${progress.progress_percent}%` }}
                />
            </div>
            
            <div className="mt-3 flex justify-between items-center text-xs text-slate-500">
                <span className="truncate max-w-md" title={progress.current_file}>
                    {progress.current_file ? `Indexing: ${progress.current_file.split('/').pop()}` : ''}
                </span>
                <span className="flex items-center gap-2">
                    <span className="text-emerald-400">{progress.files_indexed} files indexed</span>
                    <span>{progress.progress_percent.toFixed(1)}%</span>
                </span>
            </div>
        </div>
    );
}

export default function Configuration() {
    const [path, setPath] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState(null);
    const [indexedFiles, setIndexedFiles] = useState([]);
    const [progress, setProgress] = useState(null);
    const [similarityConfig, setSimilarityConfig] = useState(null);
    const [storageConfig, setStorageConfig] = useState(null);
    const [threadingConfig, setThreadingConfig] = useState(null);
    const [ignoredFilesConfig, setIgnoredFilesConfig] = useState(null);
    const [configLoading, setConfigLoading] = useState(false);
    const [filesExpanded, setFilesExpanded] = useState(false);
    const [showDeleteModal, setShowDeleteModal] = useState(false);
    const [deleting, setDeleting] = useState(false);
    const wsRef = useRef(null);

    const fetchIndexedFiles = async () => {
        try {
            const res = await axios.get(`${API_URL}/indexed-files`);
            setIndexedFiles(res.data);
        } catch (err) {
            console.error("Failed to fetch files", err);
        }
    };

    const handleDeleteAllFiles = async () => {
        setDeleting(true);
        try {
            const res = await axios.delete(`${API_URL}/indexed-files`);
            setMessage({ type: 'success', text: res.data.message });
            setIndexedFiles([]);
            setShowDeleteModal(false);
        } catch (err) {
            setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to delete indexed files' });
        } finally {
            setDeleting(false);
        }
    };

    const fetchSimilarityConfig = async () => {
        try {
            const res = await axios.get(`${API_URL}/config/similarity`);
            setSimilarityConfig(res.data);
        } catch (err) {
            console.error("Failed to fetch similarity config", err);
        }
    };

    const fetchStorageConfig = async () => {
        try {
            const res = await axios.get(`${API_URL}/config/storage`);
            setStorageConfig(res.data);
        } catch (err) {
            console.error("Failed to fetch storage config", err);
        }
    };

    const fetchThreadingConfig = async () => {
        try {
            const res = await axios.get(`${API_URL}/config/threading`);
            setThreadingConfig(res.data);
        } catch (err) {
            console.error("Failed to fetch threading config", err);
        }
    };

    const fetchIgnoredFilesConfig = async () => {
        try {
            const res = await axios.get(`${API_URL}/config/ignored-files`);
            setIgnoredFilesConfig(res.data);
        } catch (err) {
            console.error("Failed to fetch ignored files config", err);
        }
    };

    useEffect(() => {
        fetchIndexedFiles();
        fetchSimilarityConfig();
        fetchStorageConfig();
        fetchThreadingConfig();
        fetchIgnoredFilesConfig();
        return () => {
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, []);

    const handleBrowse = async () => {
        if ('showDirectoryPicker' in window) {
            try {
                const dirHandle = await window.showDirectoryPicker();
                setPath(dirHandle.name);
                setMessage({ type: 'info', text: 'Note: Browser security limits access to full paths. Please verify or enter the complete path manually.' });
            } catch (err) {
                if (err.name !== 'AbortError') {
                    setMessage({ type: 'error', text: 'Failed to open folder picker' });
                }
            }
        } else {
            setMessage({ type: 'error', text: 'Folder browsing is not supported in this browser. Please enter the path manually.' });
        }
    };

    const handleIndex = async (e) => {
        e.preventDefault();
        if (!path) return;

        setLoading(true);
        setMessage(null);
        setProgress(null);

        try {
            // Start the indexing (returns immediately with index_id)
            const indexRes = await axios.post(`${API_URL}/index`, { path });
            const indexId = indexRes.data.index_id;

            // Connect to WebSocket for real-time progress
            const ws = new WebSocket(`${WS_URL}/ws/index/${indexId}`);
            wsRef.current = ws;

            ws.onopen = () => {
                console.log('WebSocket connected for indexing:', indexId);
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                setProgress(data);

                // When indexing is completed, refresh the file list
                if (data.status === 'completed') {
                    setMessage({ type: 'success', text: `Indexing completed! ${data.files_indexed} files indexed.` });
                    setLoading(false);
                    setPath('');
                    fetchIndexedFiles();
                    if (wsRef.current) {
                        wsRef.current.close();
                    }
                } else if (data.status === 'error') {
                    setMessage({ type: 'error', text: data.error_message || 'Indexing failed' });
                    setLoading(false);
                }
            };

            ws.onerror = (err) => {
                console.error('WebSocket error:', err);
                // Fallback to polling if WebSocket fails
                pollForProgress(indexId);
            };

            ws.onclose = () => {
                console.log('WebSocket closed');
            };

        } catch (err) {
            setMessage({ type: 'error', text: err.response?.data?.detail || 'Indexing failed' });
            setLoading(false);
        }
    };

    const pollForProgress = async (indexId) => {
        const poll = async () => {
            try {
                const progressRes = await axios.get(`${API_URL}/index/${indexId}/progress`);
                setProgress(progressRes.data);

                if (progressRes.data.status === 'completed') {
                    setMessage({ type: 'success', text: `Indexing completed! ${progressRes.data.files_indexed} files indexed.` });
                    setLoading(false);
                    setPath('');
                    fetchIndexedFiles();
                } else if (progressRes.data.status === 'error') {
                    setMessage({ type: 'error', text: progressRes.data.error_message || 'Indexing failed' });
                    setLoading(false);
                } else {
                    setTimeout(poll, 500);
                }
            } catch (err) {
                setMessage({ type: 'error', text: 'Failed to get indexing progress' });
                setLoading(false);
            }
        };
        poll();
    };

    return (
        <div className="space-y-8">
            <div>
                <h2 className="text-3xl font-bold text-white mb-2">Configuration</h2>
                <p className="text-slate-400">Manage your data index. Add folders to be monitored.</p>
            </div>

            {/* Index Form */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <h3 className="text-xl font-bold text-white mb-4 flex items-center">
                    <FolderPlus className="mr-2 text-blue-400" /> Add Folder to Index
                </h3>
                <form onSubmit={handleIndex} className="flex gap-4">
                    <input
                        type="text"
                        value={path}
                        onChange={(e) => setPath(e.target.value)}
                        placeholder="/path/to/your/data"
                        className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-blue-500 transition"
                        disabled={loading}
                    />
                    <button
                        type="button"
                        onClick={handleBrowse}
                        disabled={loading}
                        className="bg-slate-700 hover:bg-slate-600 text-white font-medium px-4 py-3 rounded-lg transition flex items-center disabled:opacity-50"
                        title="Browse for folder"
                    >
                        <FolderOpen size={20} />
                    </button>
                    <button
                        type="submit"
                        disabled={loading}
                        className="bg-blue-600 hover:bg-blue-700 text-white font-medium px-6 py-3 rounded-lg transition flex items-center disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {loading ? <Loader2 className="animate-spin mr-2" size={20} /> : null}
                        {loading ? 'Indexing...' : 'Index Folder'}
                    </button>
                </form>

                {/* Progress Bar */}
                {loading && progress && <ProgressBar progress={progress} />}

                {message && (
                    <div className={`mt-4 p-3 rounded-lg ${
                        message.type === 'success' ? 'bg-emerald-900/30 text-emerald-400' : 
                        message.type === 'info' ? 'bg-blue-900/30 text-blue-400' :
                        'bg-red-900/30 text-red-400'
                    }`}>
                        {message.text}
                    </div>
                )}
            </div>

            {/* Similarity Configuration */}
            <SimilaritySettings 
                config={similarityConfig}
                loading={configLoading}
                onUpdate={async (updates) => {
                    setConfigLoading(true);
                    try {
                        const res = await axios.put(`${API_URL}/config/similarity`, updates);
                        setSimilarityConfig({ ...similarityConfig, config: res.data.config });
                        setMessage({ type: 'success', text: 'Similarity settings updated' });
                    } catch (err) {
                        setMessage({ type: 'error', text: 'Failed to update settings' });
                    } finally {
                        setConfigLoading(false);
                    }
                }}
                onApplyPreset={async (level) => {
                    setConfigLoading(true);
                    try {
                        const res = await axios.post(`${API_URL}/config/similarity/preset/${level}`);
                        setSimilarityConfig({ ...similarityConfig, config: res.data.config });
                        setMessage({ type: 'success', text: `Applied ${level} sensitivity preset` });
                    } catch (err) {
                        setMessage({ type: 'error', text: 'Failed to apply preset' });
                    } finally {
                        setConfigLoading(false);
                    }
                }}
                onReset={async () => {
                    setConfigLoading(true);
                    try {
                        const res = await axios.post(`${API_URL}/config/similarity/reset`);
                        setSimilarityConfig({ ...similarityConfig, config: res.data.config });
                        setMessage({ type: 'success', text: 'Settings reset to defaults' });
                    } catch (err) {
                        setMessage({ type: 'error', text: 'Failed to reset settings' });
                    } finally {
                        setConfigLoading(false);
                    }
                }}
            />

            {/* Storage Backend Configuration */}
            <StorageSettings
                config={storageConfig}
                loading={configLoading}
                onUpdate={async (updates) => {
                    setConfigLoading(true);
                    try {
                        const res = await axios.put(`${API_URL}/config/storage`, updates);
                        setStorageConfig({ ...storageConfig, config: res.data.config, health: res.data.health });
                        setMessage({ type: 'success', text: res.data.message });
                    } catch (err) {
                        setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to update storage settings' });
                    } finally {
                        setConfigLoading(false);
                    }
                }}
                onTestRedis={async (redisConfig) => {
                    setConfigLoading(true);
                    try {
                        const res = await axios.post(`${API_URL}/config/storage/test-redis`, null, {
                            params: redisConfig
                        });
                        if (res.data.success) {
                            setMessage({ type: 'success', text: 'Redis connection successful!' });
                        } else {
                            setMessage({ type: 'error', text: res.data.message });
                        }
                        return res.data;
                    } catch (err) {
                        setMessage({ type: 'error', text: 'Failed to test Redis connection' });
                        return { success: false };
                    } finally {
                        setConfigLoading(false);
                    }
                }}
                onRefreshHealth={async () => {
                    try {
                        const res = await axios.get(`${API_URL}/config/storage/health`);
                        setStorageConfig({ ...storageConfig, health: res.data });
                    } catch (err) {
                        console.error("Failed to refresh health", err);
                    }
                }}
            />

            {/* Threading Configuration */}
            <ThreadingSettings
                config={threadingConfig}
                loading={configLoading}
                onUpdate={async (updates) => {
                    setConfigLoading(true);
                    try {
                        const res = await axios.put(`${API_URL}/config/threading`, updates);
                        setThreadingConfig({ ...threadingConfig, ...res.data.config });
                        setMessage({ type: 'success', text: res.data.message });
                    } catch (err) {
                        setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to update threading settings' });
                    } finally {
                        setConfigLoading(false);
                    }
                }}
            />

            {/* Ignored Files Configuration */}
            <IgnoredFilesSettings
                config={ignoredFilesConfig}
                loading={configLoading}
                onUpdate={async (patterns) => {
                    setConfigLoading(true);
                    try {
                        const res = await axios.put(`${API_URL}/config/ignored-files`, { patterns });
                        setIgnoredFilesConfig({ ...ignoredFilesConfig, config: res.data.config });
                        setMessage({ type: 'success', text: res.data.message });
                    } catch (err) {
                        setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to update ignored files' });
                    } finally {
                        setConfigLoading(false);
                    }
                }}
                onAddPattern={async (pattern) => {
                    setConfigLoading(true);
                    try {
                        const res = await axios.post(`${API_URL}/config/ignored-files/add`, null, {
                            params: { pattern }
                        });
                        setIgnoredFilesConfig({ ...ignoredFilesConfig, config: res.data.config });
                        setMessage({ type: 'success', text: res.data.message });
                    } catch (err) {
                        setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to add pattern' });
                    } finally {
                        setConfigLoading(false);
                    }
                }}
                onRemovePattern={async (pattern) => {
                    setConfigLoading(true);
                    try {
                        const res = await axios.delete(`${API_URL}/config/ignored-files/remove`, {
                            params: { pattern }
                        });
                        setIgnoredFilesConfig({ ...ignoredFilesConfig, config: res.data.config });
                        setMessage({ type: 'success', text: res.data.message });
                    } catch (err) {
                        setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to remove pattern' });
                    } finally {
                        setConfigLoading(false);
                    }
                }}
                onReset={async () => {
                    setConfigLoading(true);
                    try {
                        const res = await axios.post(`${API_URL}/config/ignored-files/reset`);
                        setIgnoredFilesConfig({ ...ignoredFilesConfig, config: res.data.config });
                        setMessage({ type: 'success', text: res.data.message });
                    } catch (err) {
                        setMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to reset' });
                    } finally {
                        setConfigLoading(false);
                    }
                }}
            />

            {/* Indexed Files List */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                <div 
                    className="p-6 flex justify-between items-center cursor-pointer hover:bg-slate-800/30 transition"
                    onClick={() => setFilesExpanded(!filesExpanded)}
                >
                    <h3 className="text-xl font-bold text-white flex items-center">
                        <DatabaseIcon className="mr-2 text-purple-400" /> Indexed Files ({indexedFiles.length})
                    </h3>
                    <div className="flex items-center gap-3">
                        {indexedFiles.length > 0 && (
                            <button 
                                onClick={(e) => { e.stopPropagation(); setShowDeleteModal(true); }} 
                                className="text-red-400 hover:text-red-300 transition p-1"
                                title="Delete all indexed files"
                            >
                                <Trash2 size={18} />
                            </button>
                        )}
                        <button 
                            onClick={(e) => { e.stopPropagation(); fetchIndexedFiles(); }} 
                            className="text-slate-400 hover:text-white transition p-1"
                            title="Refresh list"
                        >
                            <RefreshCw size={18} />
                        </button>
                        <ChevronDown 
                            size={20} 
                            className={`text-slate-400 transition-transform duration-200 ${filesExpanded ? 'rotate-180' : ''}`} 
                        />
                    </div>
                </div>

                {filesExpanded && (
                    <div className="overflow-x-auto border-t border-slate-800">
                        <table className="w-full text-left text-sm text-slate-400">
                            <thead className="bg-slate-950 text-slate-200 uppercase font-medium">
                                <tr>
                                    <th className="px-6 py-4">Filename</th>
                                    <th className="px-6 py-4">Path</th>
                                    <th className="px-6 py-4">Hash (SHA256)</th>
                                    <th className="px-6 py-4">Indexed At</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800">
                                {indexedFiles.length === 0 ? (
                                    <tr>
                                        <td colSpan="4" className="px-6 py-8 text-center text-slate-500">
                                            No files indexed yet.
                                        </td>
                                    </tr>
                                ) : (
                                    indexedFiles.map((file) => (
                                        <tr key={file.id} className="hover:bg-slate-800/50 transition">
                                            <td className="px-6 py-4 font-medium text-white flex items-center">
                                                <FileText size={16} className="mr-2 text-slate-500" />
                                                {file.filename}
                                            </td>
                                            <td className="px-6 py-4 truncate max-w-xs" title={file.path}>{file.path}</td>
                                            <td className="px-6 py-4 font-mono text-xs text-slate-500 truncate max-w-[100px]" title={file.file_hash}>
                                                {file.file_hash}
                                            </td>
                                            <td className="px-6 py-4">
                                                {new Date(file.indexed_at).toLocaleString()}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {/* Delete Confirmation Modal */}
            {showDeleteModal && (
                <DeleteConfirmationModal
                    fileCount={indexedFiles.length}
                    deleting={deleting}
                    onConfirm={handleDeleteAllFiles}
                    onCancel={() => setShowDeleteModal(false)}
                />
            )}
        </div>
    );
}

function DatabaseIcon(props) {
    return (
        <svg
            {...props}
            xmlns="http://www.w3.org/2000/svg"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
        >
            <ellipse cx="12" cy="5" rx="9" ry="3" />
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
        </svg>
    );
}


function DeleteConfirmationModal({ fileCount, deleting, onConfirm, onCancel }) {
    return (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
            <div className="bg-slate-900 border border-slate-700 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-xl font-bold text-white flex items-center">
                        <AlertTriangle className="mr-2 text-red-400" size={24} />
                        Confirm Deletion
                    </h3>
                    <button
                        onClick={onCancel}
                        disabled={deleting}
                        className="text-slate-400 hover:text-white transition p-1 disabled:opacity-50"
                    >
                        <X size={20} />
                    </button>
                </div>
                
                <div className="mb-6">
                    <p className="text-slate-300 mb-3">
                        Are you sure you want to delete <span className="font-bold text-white">{fileCount}</span> indexed file{fileCount !== 1 ? 's' : ''}?
                    </p>
                    <div className="bg-red-900/20 border border-red-800/50 rounded-lg p-3">
                        <p className="text-red-400 text-sm">
                            <strong>Warning:</strong> This action cannot be undone. All indexed files will be permanently removed from the current storage backend.
                        </p>
                    </div>
                </div>
                
                <div className="flex gap-3 justify-end">
                    <button
                        onClick={onCancel}
                        disabled={deleting}
                        className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition disabled:opacity-50"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={onConfirm}
                        disabled={deleting}
                        className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition flex items-center gap-2 disabled:opacity-50"
                    >
                        {deleting ? (
                            <>
                                <Loader2 className="animate-spin" size={16} />
                                Deleting...
                            </>
                        ) : (
                            <>
                                <Trash2 size={16} />
                                Delete All Files
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
}


function SimilaritySettings({ config, loading, onUpdate, onApplyPreset, onReset }) {
    const [threshold, setThreshold] = useState(65);
    const [showAdvanced, setShowAdvanced] = useState(false);

    useEffect(() => {
        if (config?.config?.similarity_threshold) {
            setThreshold(Math.round(config.config.similarity_threshold * 100));
        }
    }, [config]);

    if (!config) {
        return (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <div className="flex items-center justify-center py-4">
                    <Loader2 className="animate-spin text-slate-400" size={24} />
                    <span className="ml-2 text-slate-400">Loading settings...</span>
                </div>
            </div>
        );
    }

    const currentLevel = config.config.sensitivity_level;
    const descriptions = config.description;

    const getSensitivityColor = (level) => {
        switch (level) {
            case 'low': return 'text-emerald-400 bg-emerald-900/30 border-emerald-800';
            case 'medium': return 'text-blue-400 bg-blue-900/30 border-blue-800';
            case 'high': return 'text-orange-400 bg-orange-900/30 border-orange-800';
            default: return 'text-purple-400 bg-purple-900/30 border-purple-800';
        }
    };

    const getSensitivityIcon = (level) => {
        switch (level) {
            case 'low': return <Shield size={18} />;
            case 'medium': return <Settings size={18} />;
            case 'high': return <AlertTriangle size={18} />;
            default: return <Settings size={18} />;
        }
    };

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
            <div className="flex justify-between items-center mb-6">
                <h3 className="text-xl font-bold text-white flex items-center">
                    <Settings className="mr-2 text-purple-400" /> Similarity Matching Settings
                </h3>
                <button 
                    onClick={onReset}
                    disabled={loading}
                    className="text-sm text-slate-400 hover:text-white transition disabled:opacity-50"
                >
                    Reset to defaults
                </button>
            </div>

            {/* Sensitivity Level Presets */}
            <div className="mb-6">
                <label className="block text-sm font-medium text-slate-300 mb-3">
                    Sensitivity Level
                </label>
                <div className="grid grid-cols-3 gap-3">
                    {['low', 'medium', 'high'].map((level) => (
                        <button
                            key={level}
                            onClick={() => onApplyPreset(level)}
                            disabled={loading}
                            className={`p-4 rounded-lg border transition-all ${
                                currentLevel === level 
                                    ? getSensitivityColor(level) + ' ring-2 ring-offset-2 ring-offset-slate-900'
                                    : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
                            } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                        >
                            <div className="flex items-center justify-center mb-2">
                                {getSensitivityIcon(level)}
                            </div>
                            <div className="font-medium capitalize">{level}</div>
                            <div className="text-xs mt-1 opacity-75">
                                {level === 'low' && '80% threshold'}
                                {level === 'medium' && '65% threshold'}
                                {level === 'high' && '50% threshold'}
                            </div>
                        </button>
                    ))}
                </div>
                <p className="mt-2 text-xs text-slate-500">
                    {descriptions[currentLevel] || 'Custom configuration'}
                </p>
            </div>

            {/* Custom Threshold Slider */}
            <div className="mb-6">
                <div className="flex justify-between items-center mb-2">
                    <label className="text-sm font-medium text-slate-300">
                        Similarity Threshold
                    </label>
                    <span className="text-sm font-mono text-white bg-slate-800 px-2 py-1 rounded">
                        {threshold}%
                    </span>
                </div>
                <input
                    type="range"
                    min="30"
                    max="95"
                    value={threshold}
                    onChange={(e) => setThreshold(parseInt(e.target.value))}
                    onMouseUp={() => onUpdate({ similarity_threshold: threshold / 100 })}
                    onTouchEnd={() => onUpdate({ similarity_threshold: threshold / 100 })}
                    className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
                    disabled={loading}
                />
                <div className="flex justify-between text-xs text-slate-500 mt-1">
                    <span>More matches (may have false positives)</span>
                    <span>Fewer matches (more precise)</span>
                </div>
            </div>

            {/* Advanced Settings Toggle */}
            <button
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="text-sm text-blue-400 hover:text-blue-300 transition mb-4"
            >
                {showAdvanced ? '▼ Hide' : '▶ Show'} advanced settings
            </button>

            {showAdvanced && (
                <div className="space-y-4 pt-4 border-t border-slate-700">
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-slate-400 mb-1">
                                High Confidence Threshold
                            </label>
                            <div className="text-sm text-white bg-slate-800 px-3 py-2 rounded">
                                {Math.round(config.config.high_confidence_threshold * 100)}%
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-400 mb-1">
                                Exact Match Threshold
                            </label>
                            <div className="text-sm text-white bg-slate-800 px-3 py-2 rounded">
                                {Math.round(config.config.exact_match_threshold * 100)}%
                            </div>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-slate-400 mb-1">
                                N-gram Range
                            </label>
                            <div className="text-sm text-white bg-slate-800 px-3 py-2 rounded">
                                {config.config.ngram_range_min} - {config.config.ngram_range_max}
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-slate-400 mb-1">
                                Min Content Length
                            </label>
                            <div className="text-sm text-white bg-slate-800 px-3 py-2 rounded">
                                {config.config.min_content_length} chars
                            </div>
                        </div>
                    </div>

                    <div className="flex items-center gap-3">
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={config.config.require_multiple_matches}
                                onChange={(e) => onUpdate({ require_multiple_matches: e.target.checked })}
                                disabled={loading}
                                className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-blue-500 focus:ring-blue-500"
                            />
                            <span className="text-sm text-slate-300">
                                Require multi-level validation (reduces false positives)
                            </span>
                        </label>
                    </div>
                </div>
            )}
        </div>
    );
}


function StorageSettings({ config, loading, onUpdate, onTestRedis, onRefreshHealth }) {
    const [showRedisConfig, setShowRedisConfig] = useState(false);
    const [redisHost, setRedisHost] = useState('localhost');
    const [redisPort, setRedisPort] = useState(6379);
    const [redisPassword, setRedisPassword] = useState('');
    const [redisDb, setRedisDb] = useState(0);
    const [testingRedis, setTestingRedis] = useState(false);

    useEffect(() => {
        if (config?.config?.redis_config) {
            setRedisHost(config.config.redis_config.host || 'localhost');
            setRedisPort(config.config.redis_config.port || 6379);
            setRedisDb(config.config.redis_config.db || 0);
        }
    }, [config]);

    if (!config) {
        return (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <div className="flex items-center justify-center py-4">
                    <Loader2 className="animate-spin text-slate-400" size={24} />
                    <span className="ml-2 text-slate-400">Loading storage settings...</span>
                </div>
            </div>
        );
    }

    const currentBackend = config.config?.backend || 'sqlite';
    const health = config.health || {};

    const handleTestRedis = async () => {
        setTestingRedis(true);
        await onTestRedis({
            host: redisHost,
            port: redisPort,
            password: redisPassword || undefined,
            db: redisDb
        });
        setTestingRedis(false);
    };

    const handleSwitchBackend = (backend) => {
        if (backend === 'redis') {
            onUpdate({
                backend: 'redis',
                redis_host: redisHost,
                redis_port: redisPort,
                redis_password: redisPassword || undefined,
                redis_db: redisDb
            });
        } else {
            onUpdate({ backend: 'sqlite' });
        }
    };

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
            <div className="flex justify-between items-center mb-6">
                <h3 className="text-xl font-bold text-white flex items-center">
                    <Database className="mr-2 text-blue-400" /> Storage Backend
                </h3>
                <div className="flex items-center gap-2">
                    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${
                        health.healthy 
                            ? 'bg-emerald-900/30 text-emerald-400' 
                            : 'bg-red-900/30 text-red-400'
                    }`}>
                        <span className={`w-2 h-2 rounded-full ${health.healthy ? 'bg-emerald-400' : 'bg-red-400'}`} />
                        {health.healthy ? 'Connected' : 'Disconnected'}
                    </span>
                    <button
                        onClick={onRefreshHealth}
                        className="text-slate-400 hover:text-white transition p-1"
                        title="Refresh status"
                    >
                        <RefreshCw size={16} />
                    </button>
                </div>
            </div>

            {/* Backend Selection */}
            <div className="mb-6">
                <label className="block text-sm font-medium text-slate-300 mb-3">
                    Storage Backend
                </label>
                <div className="grid grid-cols-2 gap-3">
                    <button
                        onClick={() => handleSwitchBackend('sqlite')}
                        disabled={loading}
                        className={`p-4 rounded-lg border transition-all ${
                            currentBackend === 'sqlite'
                                ? 'bg-blue-900/30 border-blue-800 text-blue-400 ring-2 ring-offset-2 ring-offset-slate-900 ring-blue-500'
                                : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
                        } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        <div className="flex items-center justify-center mb-2">
                            <HardDrive size={24} />
                        </div>
                        <div className="font-medium">SQLite</div>
                        <div className="text-xs mt-1 opacity-75">
                            Simple, no setup required
                        </div>
                    </button>

                    <button
                        onClick={() => setShowRedisConfig(true)}
                        disabled={loading}
                        className={`p-4 rounded-lg border transition-all ${
                            currentBackend === 'redis'
                                ? 'bg-red-900/30 border-red-800 text-red-400 ring-2 ring-offset-2 ring-offset-slate-900 ring-red-500'
                                : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
                        } ${loading ? 'opacity-50 cursor-not-allowed' : ''}`}
                    >
                        <div className="flex items-center justify-center mb-2">
                            <Server size={24} />
                        </div>
                        <div className="font-medium">Redis</div>
                        <div className="text-xs mt-1 opacity-75">
                            High performance, requires Redis Stack
                        </div>
                    </button>
                </div>
                <p className="mt-2 text-xs text-slate-500">
                    {config.description?.[currentBackend] || ''}
                </p>
            </div>

            {/* Redis Configuration */}
            {(showRedisConfig || currentBackend === 'redis') && (
                <div className="space-y-4 pt-4 border-t border-slate-700">
                    <h4 className="text-sm font-medium text-slate-300">Redis Configuration</h4>
                    
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs text-slate-400 mb-1">Host</label>
                            <input
                                type="text"
                                value={redisHost}
                                onChange={(e) => setRedisHost(e.target.value)}
                                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                                placeholder="localhost"
                            />
                        </div>
                        <div>
                            <label className="block text-xs text-slate-400 mb-1">Port</label>
                            <input
                                type="number"
                                value={redisPort}
                                onChange={(e) => setRedisPort(parseInt(e.target.value) || 6379)}
                                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                                placeholder="6379"
                            />
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-xs text-slate-400 mb-1">Password (optional)</label>
                            <input
                                type="password"
                                value={redisPassword}
                                onChange={(e) => setRedisPassword(e.target.value)}
                                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                                placeholder="••••••••"
                            />
                        </div>
                        <div>
                            <label className="block text-xs text-slate-400 mb-1">Database</label>
                            <input
                                type="number"
                                value={redisDb}
                                onChange={(e) => setRedisDb(parseInt(e.target.value) || 0)}
                                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500"
                                min="0"
                                max="15"
                            />
                        </div>
                    </div>

                    <div className="flex gap-3">
                        <button
                            onClick={handleTestRedis}
                            disabled={loading || testingRedis}
                            className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded transition disabled:opacity-50"
                        >
                            {testingRedis ? <Loader2 className="animate-spin" size={16} /> : <Zap size={16} />}
                            Test Connection
                        </button>
                        {currentBackend !== 'redis' && (
                            <button
                                onClick={() => handleSwitchBackend('redis')}
                                disabled={loading}
                                className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded transition disabled:opacity-50"
                            >
                                Switch to Redis
                            </button>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}


function ThreadingSettings({ config, loading, onUpdate }) {
    const [enabled, setEnabled] = useState(false);
    const [maxWorkers, setMaxWorkers] = useState(4);
    const [batchSize, setBatchSize] = useState(50);

    useEffect(() => {
        if (config) {
            setEnabled(config.enabled || false);
            setMaxWorkers(config.max_workers || 4);
            setBatchSize(config.batch_size || 50);
        }
    }, [config]);

    if (!config) {
        return (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <div className="flex items-center justify-center py-4">
                    <Loader2 className="animate-spin text-slate-400" size={24} />
                    <span className="ml-2 text-slate-400">Loading threading settings...</span>
                </div>
            </div>
        );
    }

    const handleSave = () => {
        onUpdate({
            enabled,
            max_workers: maxWorkers,
            batch_size: batchSize
        });
    };

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
            <div className="flex justify-between items-center mb-6">
                <h3 className="text-xl font-bold text-white flex items-center">
                    <Cpu className="mr-2 text-orange-400" /> Parallel Processing
                </h3>
                <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium ${
                    enabled 
                        ? 'bg-emerald-900/30 text-emerald-400' 
                        : 'bg-slate-700 text-slate-400'
                }`}>
                    {enabled ? 'Enabled' : 'Disabled'}
                </span>
            </div>

            {/* Enable Toggle */}
            <div className="mb-6">
                <label className="flex items-center gap-3 cursor-pointer">
                    <div className="relative">
                        <input
                            type="checkbox"
                            checked={enabled}
                            onChange={(e) => setEnabled(e.target.checked)}
                            className="sr-only"
                        />
                        <div className={`w-11 h-6 rounded-full transition ${enabled ? 'bg-orange-500' : 'bg-slate-700'}`}>
                            <div className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full transition-transform ${enabled ? 'translate-x-5' : ''}`} />
                        </div>
                    </div>
                    <div>
                        <span className="text-sm font-medium text-slate-300">
                            Enable parallel processing
                        </span>
                        <p className="text-xs text-slate-500">
                            Use multiple threads for indexing and scanning
                        </p>
                    </div>
                </label>
            </div>

            {/* Worker Configuration */}
            {enabled && (
                <div className="space-y-4 pt-4 border-t border-slate-700">
                    <div>
                        <div className="flex justify-between items-center mb-2">
                            <label className="text-sm font-medium text-slate-300">
                                Worker Threads
                            </label>
                            <span className="text-sm font-mono text-white bg-slate-800 px-2 py-1 rounded">
                                {maxWorkers}
                            </span>
                        </div>
                        <input
                            type="range"
                            min="1"
                            max="16"
                            value={maxWorkers}
                            onChange={(e) => setMaxWorkers(parseInt(e.target.value))}
                            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-orange-500"
                            disabled={loading}
                        />
                        <div className="flex justify-between text-xs text-slate-500 mt-1">
                            <span>1 (sequential)</span>
                            <span>Recommended: {navigator.hardwareConcurrency || 4} (CPU cores)</span>
                            <span>16 (max)</span>
                        </div>
                    </div>

                    <div>
                        <div className="flex justify-between items-center mb-2">
                            <label className="text-sm font-medium text-slate-300">
                                Batch Size
                            </label>
                            <span className="text-sm font-mono text-white bg-slate-800 px-2 py-1 rounded">
                                {batchSize} files
                            </span>
                        </div>
                        <input
                            type="range"
                            min="10"
                            max="200"
                            step="10"
                            value={batchSize}
                            onChange={(e) => setBatchSize(parseInt(e.target.value))}
                            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-orange-500"
                            disabled={loading}
                        />
                        <div className="flex justify-between text-xs text-slate-500 mt-1">
                            <span>10 (frequent updates)</span>
                            <span>200 (better performance)</span>
                        </div>
                    </div>

                    <div className="pt-2">
                        <p className="text-xs text-slate-500 mb-3">
                            {config.recommendations?.io_bound || 'For I/O-bound tasks like file scanning, you can use 2-4x CPU cores.'}
                        </p>
                    </div>
                </div>
            )}

            {/* Save Button */}
            <div className="mt-6 pt-4 border-t border-slate-700">
                <button
                    onClick={handleSave}
                    disabled={loading}
                    className="flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded transition disabled:opacity-50"
                >
                    {loading ? <Loader2 className="animate-spin" size={16} /> : <CheckCircle size={16} />}
                    Save Threading Settings
                </button>
            </div>
        </div>
    );
}


function IgnoredFilesSettings({ config, loading, onUpdate, onAddPattern, onRemovePattern, onReset }) {
    const [newPattern, setNewPattern] = useState('');
    const [showExamples, setShowExamples] = useState(false);

    if (!config) {
        return (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <div className="flex items-center justify-center py-4">
                    <Loader2 className="animate-spin text-slate-400" size={24} />
                    <span className="ml-2 text-slate-400">Loading ignored files settings...</span>
                </div>
            </div>
        );
    }

    const patterns = config.config?.patterns || [];

    const handleAddPattern = () => {
        if (newPattern.trim()) {
            onAddPattern(newPattern.trim());
            setNewPattern('');
        }
    };

    const handleKeyPress = (e) => {
        if (e.key === 'Enter') {
            handleAddPattern();
        }
    };

    const commonPatterns = [
        { pattern: '.DS_Store', desc: 'macOS system files' },
        { pattern: 'Thumbs.db', desc: 'Windows thumbnail cache' },
        { pattern: '*.log', desc: 'Log files' },
        { pattern: '*.tmp', desc: 'Temporary files' },
        { pattern: '*.pyc', desc: 'Python compiled files' },
        { pattern: '__pycache__', desc: 'Python cache directories' },
        { pattern: 'node_modules', desc: 'Node.js dependencies' },
        { pattern: '.git', desc: 'Git repository data' },
        { pattern: '*.bak', desc: 'Backup files' },
        { pattern: '~$*', desc: 'Office temp files' },
    ];

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
            <div className="flex justify-between items-center mb-6">
                <h3 className="text-xl font-bold text-white flex items-center">
                    <FileX className="mr-2 text-red-400" /> Ignored Files
                </h3>
                <span className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium bg-slate-700 text-slate-300">
                    {patterns.length} pattern{patterns.length !== 1 ? 's' : ''}
                </span>
            </div>

            <p className="text-sm text-slate-400 mb-4">
                Files matching these patterns will be skipped during indexing and scanning. 
                Patterns match filename only (not full path) and support wildcards (* and ?).
            </p>

            {/* Add Pattern Input */}
            <div className="flex gap-2 mb-4">
                <input
                    type="text"
                    value={newPattern}
                    onChange={(e) => setNewPattern(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="e.g., *.log, .DS_Store, *.tmp"
                    className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-4 py-2 text-white text-sm focus:outline-none focus:border-red-500 transition"
                    disabled={loading}
                />
                <button
                    onClick={handleAddPattern}
                    disabled={loading || !newPattern.trim()}
                    className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    <Plus size={16} />
                    Add
                </button>
            </div>

            {/* Common Patterns Quick Add */}
            <div className="mb-4">
                <button
                    onClick={() => setShowExamples(!showExamples)}
                    className="text-sm text-blue-400 hover:text-blue-300 transition"
                >
                    {showExamples ? '▼ Hide' : '▶ Show'} common patterns
                </button>
                
                {showExamples && (
                    <div className="mt-3 grid grid-cols-2 gap-2">
                        {commonPatterns.map(({ pattern, desc }) => (
                            <button
                                key={pattern}
                                onClick={() => !patterns.includes(pattern) && onAddPattern(pattern)}
                                disabled={loading || patterns.includes(pattern)}
                                className={`flex items-center justify-between p-2 rounded text-sm transition ${
                                    patterns.includes(pattern)
                                        ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
                                        : 'bg-slate-800 hover:bg-slate-700 text-slate-300'
                                }`}
                            >
                                <span className="font-mono text-xs">{pattern}</span>
                                <span className="text-xs text-slate-500">{desc}</span>
                            </button>
                        ))}
                    </div>
                )}
            </div>

            {/* Current Patterns List */}
            <div className="border border-slate-700 rounded-lg overflow-hidden">
                <div className="bg-slate-800 px-4 py-2 text-sm font-medium text-slate-300">
                    Active Patterns
                </div>
                <div className="divide-y divide-slate-700">
                    {patterns.length === 0 ? (
                        <div className="px-4 py-6 text-center text-slate-500 text-sm">
                            No patterns configured. All files will be processed.
                        </div>
                    ) : (
                        patterns.map((pattern, index) => (
                            <div 
                                key={index} 
                                className="flex items-center justify-between px-4 py-2 hover:bg-slate-800/50 transition"
                            >
                                <span className="font-mono text-sm text-white">{pattern}</span>
                                <button
                                    onClick={() => onRemovePattern(pattern)}
                                    disabled={loading}
                                    className="text-slate-400 hover:text-red-400 transition p-1 disabled:opacity-50"
                                    title="Remove pattern"
                                >
                                    <X size={16} />
                                </button>
                            </div>
                        ))
                    )}
                </div>
            </div>

            {/* Reset Button */}
            {patterns.length > 0 && (
                <div className="mt-4 flex justify-end">
                    <button
                        onClick={onReset}
                        disabled={loading}
                        className="text-sm text-slate-400 hover:text-white transition disabled:opacity-50"
                    >
                        Reset to defaults
                    </button>
                </div>
            )}
        </div>
    );
}
