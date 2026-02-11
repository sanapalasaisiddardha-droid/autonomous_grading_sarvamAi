import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Download, Loader2, Trophy, BarChart3, Eye, ArrowLeft } from 'lucide-react';
import apiClient from '../api/client';

function ReportDashboard() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchReport = useCallback(async () => {
    try {
      const response = await apiClient.get(`/exams/exams/${id}/report/`);
      setReport(response.data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchReport();
  }, [fetchReport]);

  const handleDownloadCSV = () => {
    if (!report) return;
    const { students, total_questions, max_marks_per_question } = report;

    const headers = [
      'Roll Number',
      ...Array.from({ length: total_questions }, (_, i) => `Q${i + 1} (/${max_marks_per_question[i] || 10})`),
      'Total',
      'Max Total',
      'Percentage',
    ];

    const rows = students.map((s) => [
      s.roll_number,
      ...s.question_marks.map((m) => (m !== null ? m : '-')),
      s.total,
      s.max_total,
      `${s.percentage}%`,
    ]);

    const csv = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${report.exam_name.replace(/\s+/g, '_')}_report.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="max-w-4xl mx-auto">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error || 'Failed to load report.'}
        </div>
      </div>
    );
  }

  const { exam_name, subject, class_section_display, total_questions, max_marks_per_question, students } = report;
  const maxTotal = max_marks_per_question.reduce((a, b) => a + b, 0);

  // Compute class stats
  const totals = students.map((s) => s.total).filter((t) => t > 0);
  const classAvg = totals.length > 0 ? (totals.reduce((a, b) => a + b, 0) / totals.length).toFixed(1) : 0;
  const classHigh = totals.length > 0 ? Math.max(...totals) : 0;
  const classLow = totals.length > 0 ? Math.min(...totals) : 0;

  return (
    <div className="max-w-5xl mx-auto">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </button>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">{exam_name}</h1>
          <p className="text-gray-500">
            {subject} {class_section_display && `| ${class_section_display}`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(`/grading/${id}`)}
            className="flex items-center gap-2 bg-white text-blue-600 border border-blue-600 px-4 py-2 rounded-lg hover:bg-blue-50 transition-colors"
          >
            <Eye className="w-4 h-4" />
            Review Answers
          </button>
          <button
            onClick={handleDownloadCSV}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Download className="w-4 h-4" />
            Download CSV
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div className="bg-white rounded-lg shadow p-4 text-center">
          <BarChart3 className="w-6 h-6 text-blue-500 mx-auto mb-2" />
          <p className="text-2xl font-bold">{students.length}</p>
          <p className="text-xs text-gray-500">Students</p>
        </div>
        <div className="bg-white rounded-lg shadow p-4 text-center">
          <Trophy className="w-6 h-6 text-yellow-500 mx-auto mb-2" />
          <p className="text-2xl font-bold">{classHigh}<span className="text-sm text-gray-400">/{maxTotal}</span></p>
          <p className="text-xs text-gray-500">Highest</p>
        </div>
        <div className="bg-white rounded-lg shadow p-4 text-center">
          <p className="text-2xl font-bold mt-2">{classAvg}<span className="text-sm text-gray-400">/{maxTotal}</span></p>
          <p className="text-xs text-gray-500">Average</p>
        </div>
        <div className="bg-white rounded-lg shadow p-4 text-center">
          <p className="text-2xl font-bold mt-2">{classLow}<span className="text-sm text-gray-400">/{maxTotal}</span></p>
          <p className="text-xs text-gray-500">Lowest</p>
        </div>
      </div>

      {/* Results table */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-4 py-3 text-left font-semibold text-gray-700 sticky left-0 bg-gray-50">
                  Roll No.
                </th>
                {Array.from({ length: total_questions }, (_, i) => (
                  <th key={i} className="px-3 py-3 text-center font-semibold text-gray-700">
                    Q{i + 1}
                    <span className="block text-xs font-normal text-gray-400">/{max_marks_per_question[i] || 10}</span>
                  </th>
                ))}
                <th className="px-4 py-3 text-center font-semibold text-gray-700">Total</th>
                <th className="px-4 py-3 text-center font-semibold text-gray-700">%</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {students.map((student) => {
                const pct = student.percentage;
                const rowColor = pct >= 75 ? '' : pct >= 50 ? '' : pct >= 35 ? 'bg-yellow-50' : 'bg-red-50';
                return (
                  <tr key={student.roll_number} className={`hover:bg-gray-50 ${rowColor}`}>
                    <td className="px-4 py-3 font-medium sticky left-0 bg-white">
                      {student.roll_number}
                    </td>
                    {student.question_marks.map((m, i) => {
                      const max = max_marks_per_question[i] || 10;
                      const isLow = m !== null && m < max * 0.35;
                      return (
                        <td
                          key={i}
                          className={`px-3 py-3 text-center ${
                            m === null ? 'text-gray-300' : isLow ? 'text-red-600 font-medium' : ''
                          }`}
                        >
                          {m !== null ? m : '-'}
                        </td>
                      );
                    })}
                    <td className="px-4 py-3 text-center font-semibold">
                      {student.total} <span className="text-gray-400 font-normal">/ {student.max_total}</span>
                    </td>
                    <td className={`px-4 py-3 text-center font-semibold ${
                      pct >= 75 ? 'text-green-600' : pct >= 50 ? 'text-blue-600' : pct >= 35 ? 'text-yellow-600' : 'text-red-600'
                    }`}>
                      {pct}%
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {students.length === 0 && (
        <div className="text-center py-12 text-gray-500">
          No grading data available yet.
        </div>
      )}
    </div>
  );
}

export default ReportDashboard;
