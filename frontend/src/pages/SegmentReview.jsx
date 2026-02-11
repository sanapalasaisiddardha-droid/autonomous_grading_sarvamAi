import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  CheckCircle2, XCircle, AlertTriangle, Loader2, ChevronDown, ChevronUp, ArrowRight, ArrowLeft,
} from 'lucide-react';
import apiClient from '../api/client';

const STATUS_ICON = {
  uploaded: { icon: Loader2, color: 'text-gray-400', label: 'Uploaded' },
  processing: { icon: Loader2, color: 'text-blue-500', label: 'Processing' },
  segmented: { icon: CheckCircle2, color: 'text-green-500', label: 'Segmented' },
  needs_review: { icon: AlertTriangle, color: 'text-orange-500', label: 'Needs Review' },
  failed: { icon: XCircle, color: 'text-red-500', label: 'Failed' },
};

function SegmentReview() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [examStatus, setExamStatus] = useState(null);
  const [segments, setSegments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState(null);
  const [expandedSheet, setExpandedSheet] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [statusRes, segRes] = await Promise.all([
        apiClient.get(`/exams/exams/${id}/processing-status/`),
        apiClient.get('/exams/segments/', { params: { exam: id } }),
      ]);
      setExamStatus(statusRes.data);
      setSegments(segRes.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleApproveAndGrade = async () => {
    setApproving(true);
    setError(null);
    try {
      await apiClient.post(`/exams/exams/${id}/approve-review/`);
      navigate(`/grading/${id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setApproving(false);
    }
  };

  const toggleSheet = (anonymousId) => {
    setExpandedSheet(expandedSheet === anonymousId ? null : anonymousId);
  };

  // Group segments by sheet anonymous_id
  const segmentsBySheet = {};
  segments.forEach((seg) => {
    const key = seg.answer_sheet;
    if (!segmentsBySheet[key]) segmentsBySheet[key] = [];
    segmentsBySheet[key].push(seg);
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  if (!examStatus) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error || 'Failed to load review data.'}
        </div>
      </div>
    );
  }

  const { sheets, status_counts, total_sheets, exam_status } = examStatus;
  const segmentedCount = (status_counts.segmented || 0) + (status_counts.needs_review || 0);
  const failedCount = status_counts.failed || 0;

  return (
    <div className="max-w-3xl mx-auto">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </button>
      <h1 className="text-2xl font-bold mb-2">Segment Review</h1>
      <p className="text-gray-500 mb-6">
        Review detected question boundaries before grading.
      </p>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      {/* Summary card */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="grid grid-cols-3 gap-4 text-center mb-4">
          <div>
            <p className="text-2xl font-bold">{total_sheets}</p>
            <p className="text-sm text-gray-500">Total Sheets</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-green-600">{segmentedCount}</p>
            <p className="text-sm text-gray-500">Ready to Grade</p>
          </div>
          <div>
            <p className="text-2xl font-bold text-red-600">{failedCount}</p>
            <p className="text-sm text-gray-500">Failed</p>
          </div>
        </div>

        {/* Status chips */}
        <div className="flex flex-wrap gap-2 mb-4">
          {Object.entries(status_counts).map(([st, count]) => {
            const cfg = STATUS_ICON[st] || STATUS_ICON.uploaded;
            return (
              <span
                key={st}
                className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full font-medium ${cfg.color} bg-opacity-10`}
                style={{ backgroundColor: 'currentcolor', backgroundClip: 'padding-box', opacity: 0.15 }}
              >
                <span className={cfg.color} style={{ opacity: 1 }}>{cfg.label}: {count}</span>
              </span>
            );
          })}
        </div>

        {exam_status === 'review' && segmentedCount > 0 && (
          <button
            onClick={handleApproveAndGrade}
            disabled={approving}
            className="w-full bg-green-600 text-white py-3 rounded-lg font-medium hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {approving ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <ArrowRight className="w-5 h-5" />
            )}
            {approving ? 'Approving...' : `Approve & Start Grading (${segmentedCount} sheet${segmentedCount !== 1 ? 's' : ''})`}
          </button>
        )}

        {exam_status === 'grading' && (
          <button
            onClick={() => navigate(`/grading/${id}`)}
            className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 flex items-center justify-center gap-2"
          >
            <ArrowRight className="w-5 h-5" />
            Continue to Grading
          </button>
        )}
      </div>

      {/* Per-sheet details */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold">Answer Sheets</h2>
        </div>
        <ul className="divide-y divide-gray-100">
          {sheets.map((sheet) => {
            const cfg = STATUS_ICON[sheet.status] || STATUS_ICON.uploaded;
            const Icon = cfg.icon;
            const isExpanded = expandedSheet === sheet.anonymous_id;
            const sheetSegments = segmentsBySheet[sheet.anonymous_id] || [];

            return (
              <li key={sheet.anonymous_id}>
                <button
                  onClick={() => toggleSheet(sheet.anonymous_id)}
                  className="w-full px-6 py-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <Icon className={`w-5 h-5 ${cfg.color}`} />
                    <span className="font-mono text-sm">{sheet.short_id}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cfg.color}`}>
                      {cfg.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-gray-500">
                    <span>{sheet.page_count} page{sheet.page_count !== 1 ? 's' : ''}</span>
                    <span>{sheet.segment_count} segment{sheet.segment_count !== 1 ? 's' : ''}</span>
                    {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                  </div>
                </button>

                {isExpanded && (
                  <div className="px-6 pb-4">
                    {sheet.segment_count === 0 ? (
                      <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 text-sm text-orange-700">
                        No segments detected for this sheet.
                        {sheet.status === 'failed' && ' Processing failed — question markers were not found.'}
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                        {sheetSegments
                          .sort((a, b) => a.question_number - b.question_number)
                          .map((seg) => (
                            <div
                              key={seg.id}
                              className={`border rounded-lg overflow-hidden ${
                                seg.needs_review ? 'border-orange-300' : 'border-gray-200'
                              }`}
                            >
                              <div className="aspect-[3/4] bg-gray-100 flex items-center justify-center">
                                <img
                                  src={seg.image.startsWith('http') ? seg.image : seg.image.startsWith('/') ? seg.image : `/media/${seg.image}`}
                                  alt={`Q${seg.question_number}`}
                                  className="w-full h-full object-contain"
                                />
                              </div>
                              <div className="px-2 py-1.5 text-xs flex items-center justify-between">
                                <span className="font-medium">Q{seg.question_number}</span>
                                <span className="text-gray-400">
                                  {seg.needs_review ? (
                                    <span className="text-orange-500">Review</span>
                                  ) : (
                                    <span className="text-green-500">OK</span>
                                  )}
                                </span>
                              </div>
                            </div>
                          ))}
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

export default SegmentReview;
