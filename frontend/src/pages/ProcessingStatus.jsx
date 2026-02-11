import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Loader2, CheckCircle2, XCircle, AlertTriangle, Play, ArrowLeft } from 'lucide-react';
import apiClient from '../api/client';

const STATUS_CONFIG = {
  uploaded:     { icon: Loader2,        color: 'text-gray-400',  bg: 'bg-gray-100',  label: 'Uploaded' },
  processing:   { icon: Loader2,        color: 'text-blue-500',  bg: 'bg-blue-100',  label: 'Processing', spin: true },
  segmented:    { icon: CheckCircle2,   color: 'text-green-500', bg: 'bg-green-100',  label: 'Segmented' },
  needs_review: { icon: AlertTriangle,  color: 'text-orange-500',bg: 'bg-orange-100', label: 'Needs Review' },
  failed:       { icon: XCircle,        color: 'text-red-500',   bg: 'bg-red-100',    label: 'Failed' },
};

function ProcessingStatus() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [starting, setStarting] = useState(false);
  const intervalRef = useRef(null);

  const fetchStatus = useCallback(async () => {
    try {
      const response = await apiClient.get(`/exams/exams/${id}/processing-status/`);
      setData(response.data);
      setError(null);

      // Stop polling if exam has moved past processing
      const examStatus = response.data.exam_status;
      if (examStatus === 'grading' || examStatus === 'completed') {
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  // Start polling on mount
  useEffect(() => {
    fetchStatus();
    intervalRef.current = setInterval(fetchStatus, 3000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchStatus]);

  const handleStartProcessing = async () => {
    setStarting(true);
    setError(null);
    try {
      await apiClient.post(`/exams/exams/${id}/process/`);
      // Immediately re-fetch status
      await fetchStatus();
    } catch (err) {
      setError(err.message);
    } finally {
      setStarting(false);
    }
  };

  const handleContinue = () => {
    if (!data) return;
    if (data.exam_status === 'review') {
      navigate(`/review/${id}`);
    } else if (data.exam_status === 'grading') {
      navigate(`/grading/${id}`);
    } else if (data.exam_status === 'completed') {
      navigate(`/report/${id}`);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error || 'Failed to load processing status.'}
        </div>
      </div>
    );
  }

  const { exam_status, total_sheets, status_counts, sheets } = data;
  const doneCount = (status_counts.segmented || 0) + (status_counts.needs_review || 0) + (status_counts.failed || 0);
  const progressPct = total_sheets > 0 ? Math.round((doneCount / total_sheets) * 100) : 0;
  const isProcessing = exam_status === 'processing';
  const canStart = exam_status === 'created' && total_sheets > 0;
  const isDone = exam_status === 'review' || exam_status === 'grading' || exam_status === 'completed';

  return (
    <div className="max-w-2xl mx-auto">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </button>
      <h1 className="text-2xl font-bold mb-6">Processing Status</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      {/* Exam status card */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <span className="text-sm text-gray-500">Exam Status</span>
            <p className="text-lg font-semibold capitalize">{exam_status}</p>
          </div>
          <div className="text-right">
            <span className="text-sm text-gray-500">Total Sheets</span>
            <p className="text-lg font-semibold">{total_sheets}</p>
          </div>
        </div>

        {/* Progress bar */}
        {(isProcessing || isDone) && (
          <div className="mb-4">
            <div className="flex justify-between text-sm text-gray-500 mb-1">
              <span>{doneCount} of {total_sheets} processed</span>
              <span>{progressPct}%</span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-3">
              <div
                className={`h-3 rounded-full transition-all duration-500 ${isDone ? 'bg-green-500' : 'bg-blue-500'}`}
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        )}

        {/* Status breakdown */}
        {Object.keys(status_counts).length > 0 && (
          <div className="flex flex-wrap gap-3 mb-4">
            {Object.entries(status_counts).map(([st, count]) => {
              const cfg = STATUS_CONFIG[st] || STATUS_CONFIG.uploaded;
              return (
                <span key={st} className={`text-xs px-2 py-1 rounded-full font-medium ${cfg.bg} ${cfg.color}`}>
                  {cfg.label}: {count}
                </span>
              );
            })}
          </div>
        )}

        {/* Actions */}
        {canStart && (
          <button
            onClick={handleStartProcessing}
            disabled={starting}
            className="w-full flex items-center justify-center gap-2 bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {starting ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Play className="w-5 h-5" />
            )}
            {starting ? 'Starting...' : 'Start Processing'}
          </button>
        )}

        {isProcessing && (
          <div className="flex items-center gap-2 text-blue-600 justify-center py-2">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span className="font-medium">Processing in progress... polling every 3s</span>
          </div>
        )}

        {isDone && (
          <button
            onClick={handleContinue}
            className="w-full bg-green-600 text-white py-3 rounded-lg font-medium hover:bg-green-700"
          >
            Continue to {exam_status === 'review' ? 'Segment Review' : exam_status === 'grading' ? 'Grading' : 'Report'}
          </button>
        )}
      </div>

      {/* Per-sheet status */}
      {sheets && sheets.length > 0 && (
        <div className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-100">
            <h2 className="font-semibold">Answer Sheets</h2>
          </div>
          <ul className="divide-y divide-gray-100">
            {sheets.map((sheet) => {
              const cfg = STATUS_CONFIG[sheet.status] || STATUS_CONFIG.uploaded;
              const Icon = cfg.icon;
              return (
                <li key={sheet.anonymous_id} className="px-6 py-3 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <Icon className={`w-5 h-5 ${cfg.color} ${cfg.spin ? 'animate-spin' : ''}`} />
                    <span className="text-sm font-mono text-gray-700">{sheet.short_id}</span>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-gray-500">
                    <span>{sheet.page_count} page{sheet.page_count !== 1 ? 's' : ''}</span>
                    <span>{sheet.segment_count} segment{sheet.segment_count !== 1 ? 's' : ''}</span>
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${cfg.bg} ${cfg.color}`}>
                      {cfg.label}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

export default ProcessingStatus;
