import React, { useState, useEffect, useRef } from 'react';
import { axiosInstance as axios, API_URL, WS_URL } from '../api/client';
import { Search, AlertTriangle, CheckCircle, FileWarning, ArrowRight, FolderOpen, Loader2 } from 'lucide-react';

function ProgressBar({ progress }) {
    return (
        <div className="mt-6 bg-slate-950 rounded-lg p-4 border border-slate-700">
            <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-slate-300">
                    {progress.status === 'counting' ? 'Counting files...' : 
                     progress.status === 'scanning' ? 'Scanning files...' :
                     progress.status === 'completed' ? 'Scan completed!' : 'Preparing...'}
                </span>
                <span className="text-sm text-slate-400">
                    {progress.files_scanned} / {progress.total_files} files
                </span>
            </div>
            
            <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden">
                <div 
                    className="h-full bg-gradient-to-r from-blue-500 to-blue-400 transition-all duration-300 ease-out"
                    style={{ width: `${progress.progress_percent}%` }}
                />
            </div>
            
            <div className="mt-3 flex justify-between items-center text-xs text-slate-500">
                <span className="truncate max-w-md" title={progress.current_file}>
                    {progress.current_file ? `Scanning: ${progress.current_file.split('/').pop()}` : ''}
                </span>
                <span className="flex items-center gap-2">
                    <span className="text-orange-400">{progress.matches_found} matches found</span>
                    <span>{progress.progress_percent.toFixed(1)}%</span>
                </span>
            </div>
        </div>
    );
}

export default function Scan() {
    const [path, setPath] = useState('');
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState(null);
    const [error, setError] = useState(null);
    const [progress, setProgress] = useState(null);
    const wsRef = useRef(null);

    // Cleanup WebSocket on unmount
    useEffect(() => {
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
                setError('Note: Browser security limits access to full paths. Please verify or enter the complete path manually.');
            } catch (err) {
                if (err.name !== 'AbortError') {
                    setError('Failed to open folder picker');
                }
            }
        } else {
            setError('Folder browsing is not supported in this browser. Please enter the path manually.');
        }
    };

    const handleScan = async (e) => {
        e.preventDefault();
        if (!path) return;

        setLoading(true);
        setError(null);
        setResults(null);
        setProgress(null);

        try {
            // Start the scan (returns immediately with scan_id)
            const scanRes = await axios.post(`${API_URL}/scan`, { path });
            const scanId = scanRes.data.scan_id;

            // Connect to WebSocket for real-time progress
            const ws = new WebSocket(`${WS_URL}/ws/scan/${scanId}`);
            wsRef.current = ws;

            ws.onopen = () => {
                console.log('WebSocket connected for scan:', scanId);
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                setProgress(data);

                // When scan is completed, fetch results
                if (data.status === 'completed') {
                    fetchResults(scanId);
                } else if (data.status === 'error') {
                    setError(data.error_message || 'Scan failed');
                    setLoading(false);
                }
            };

            ws.onerror = (err) => {
                console.error('WebSocket error:', err);
                // Fallback to polling if WebSocket fails
                pollForResults(scanId);
            };

            ws.onclose = () => {
                console.log('WebSocket closed');
            };

        } catch (err) {
            setError(err.response?.data?.detail || 'Scan failed');
            setLoading(false);
        }
    };

    const fetchResults = async (scanId) => {
        try {
            const resultsRes = await axios.get(`${API_URL}/results/${scanId}`);
            setResults(resultsRes.data);
        } catch (err) {
            setError('Failed to fetch results');
        } finally {
            setLoading(false);
            if (wsRef.current) {
                wsRef.current.close();
            }
        }
    };

    const pollForResults = async (scanId) => {
        // Fallback polling if WebSocket fails
        const poll = async () => {
            try {
                const progressRes = await axios.get(`${API_URL}/scan/${scanId}/progress`);
                setProgress(progressRes.data);

                if (progressRes.data.status === 'completed') {
                    fetchResults(scanId);
                } else if (progressRes.data.status === 'error') {
                    setError(progressRes.data.error_message || 'Scan failed');
                    setLoading(false);
                } else {
                    setTimeout(poll, 500);
                }
            } catch (err) {
                setError('Failed to get scan progress');
                setLoading(false);
            }
        };
        poll();
    };

    return (
        <div className="space-y-8">
            <div>
                <h2 className="text-3xl font-bold text-white mb-2">Scan & Detect</h2>
                <p className="text-slate-400">Scan directories for matches against your indexed data.</p>
            </div>

            {/* Scan Form */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                <h3 className="text-xl font-bold text-white mb-4 flex items-center">
                    <Search className="mr-2 text-blue-400" /> Start New Scan
                </h3>
                <form onSubmit={handleScan} className="flex gap-4">
                    <input
                        type="text"
                        value={path}
                        onChange={(e) => setPath(e.target.value)}
                        placeholder="/path/to/target/folder"
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
                        {loading ? 'Scanning...' : 'Scan Now'}
                    </button>
                </form>

                {/* Progress Bar */}
                {loading && progress && <ProgressBar progress={progress} />}

                {error && (
                    <div className="mt-4 p-3 rounded-lg bg-red-900/30 text-red-400">
                        {error}
                    </div>
                )}
            </div>

            {/* Results */}
            {results && (
                <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                    <div className="p-6 border-b border-slate-800 flex justify-between items-center">
                        <h3 className="text-xl font-bold text-white flex items-center">
                            <FileWarning className="mr-2 text-orange-400" /> Scan Results
                        </h3>
                        <span className="bg-slate-800 text-slate-300 px-3 py-1 rounded-full text-sm font-medium">
                            {results.length} Matches Found
                        </span>
                    </div>

                    <div className="overflow-x-auto">
                        <table className="w-full text-left text-sm text-slate-400">
                            <thead className="bg-slate-950 text-slate-200 uppercase font-medium">
                                <tr>
                                    <th className="px-6 py-4">Match Type</th>
                                    <th className="px-6 py-4">Found File</th>
                                    <th className="px-6 py-4">Matched Against</th>
                                    <th className="px-6 py-4">Score</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800">
                                {results.length === 0 ? (
                                    <tr>
                                        <td colSpan="4" className="px-6 py-8 text-center text-slate-500">
                                            <div className="flex flex-col items-center justify-center">
                                                <CheckCircle size={48} className="text-emerald-500 mb-2" />
                                                <p className="text-lg font-medium text-white">Clean Scan</p>
                                                <p>No matches found in the target directory.</p>
                                            </div>
                                        </td>
                                    </tr>
                                ) : (
                                    results.map((result) => (
                                        <tr key={result.id} className="hover:bg-slate-800/50 transition">
                                            <td className="px-6 py-4">
                                                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                                    result.match_type === 'exact'
                                                        ? 'bg-red-900/50 text-red-400 border border-red-800'
                                                        : result.match_type === 'high_confidence'
                                                        ? 'bg-orange-900/50 text-orange-400 border border-orange-800'
                                                        : 'bg-yellow-900/50 text-yellow-400 border border-yellow-800'
                                                    }`}>
                                                    {result.match_type === 'exact' ? 'EXACT MATCH' : 
                                                     result.match_type === 'high_confidence' ? 'HIGH CONFIDENCE' : 
                                                     'SIMILARITY'}
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 font-medium text-white truncate max-w-xs" title={result.file_path}>
                                                {result.file_path}
                                            </td>
                                            <td className="px-6 py-4 flex items-center space-x-2 truncate max-w-xs">
                                                <ArrowRight size={14} className="text-slate-600" />
                                                <span title={result.matched_file_id}>ID: {result.matched_file_id}</span>
                                            </td>
                                            <td className="px-6 py-4 font-mono">
                                                <div className="flex items-center space-x-2">
                                                    <div className="w-16 h-2 bg-slate-800 rounded-full overflow-hidden">
                                                        <div
                                                            className={`h-full ${
                                                                result.score > 0.95 ? 'bg-red-500' : 
                                                                result.score > 0.85 ? 'bg-orange-500' : 
                                                                'bg-yellow-500'
                                                            }`}
                                                            style={{ width: `${result.score * 100}%` }}
                                                        ></div>
                                                    </div>
                                                    <span>{(result.score * 100).toFixed(1)}%</span>
                                                </div>
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}
