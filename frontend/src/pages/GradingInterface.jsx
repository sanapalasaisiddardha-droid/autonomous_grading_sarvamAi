import { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Check, Loader2, AlertTriangle, ArrowLeft } from 'lucide-react';
import apiClient from '../api/client';

function GradingInterface() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [gradingStatus, setGradingStatus] = useState(null);
  const [segments, setSegments] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [marks, setMarks] = useState('');
  const [feedback, setFeedback] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [error, setError] = useState(null);
  const [grades, setGrades] = useState({}); // segmentId -> grade data
  const [readOnly, setReadOnly] = useState(false);
  const [viewingQuestion, setViewingQuestion] = useState(null);

  const fetchGradingStatus = useCallback(async () => {
    try {
      const response = await apiClient.get(`/exams/exams/${id}/grading-status/`);
      setGradingStatus(response.data);
      return response.data;
    } catch (err) {
      setError(err.message);
      return null;
    }
  }, [id]);

  const fetchSegmentsForQuestion = useCallback(async (questionNum) => {
    try {
      const response = await apiClient.get('/exams/segments/', {
        params: { exam: id, question: questionNum },
      });
      // Shuffle for anonymity
      const shuffled = [...response.data].sort(() => Math.random() - 0.5);
      setSegments(shuffled);
      setCurrentIndex(0);

      // Fetch existing grades for this question
      const gradesResponse = await apiClient.get('/grading/grades/', {
        params: { exam: id, question: questionNum },
      });
      const gradeMap = {};
      gradesResponse.data.forEach((g) => {
        gradeMap[g.segment] = g;
      });
      setGrades(gradeMap);

      // Set marks/feedback for first segment if already graded
      if (shuffled.length > 0 && gradeMap[shuffled[0].id]) {
        setMarks(String(gradeMap[shuffled[0].id].marks));
        setFeedback(gradeMap[shuffled[0].id].feedback || '');
      } else {
        setMarks('');
        setFeedback('');
      }
    } catch (err) {
      setError(err.message);
    }
  }, [id]);

  // Initial load
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      const status = await fetchGradingStatus();
      if (status) {
        const isCompleted = status.exam_status === 'completed';
        setReadOnly(isCompleted);
        const startQuestion = isCompleted ? 1 : status.current_grading_question;
        setViewingQuestion(startQuestion);
        await fetchSegmentsForQuestion(startQuestion);
      }
      setLoading(false);
    };
    init();
  }, [fetchGradingStatus, fetchSegmentsForQuestion]);

  // When navigating between segments, update marks/feedback fields
  useEffect(() => {
    if (segments.length === 0) return;
    const seg = segments[currentIndex];
    if (seg && grades[seg.id]) {
      setMarks(String(grades[seg.id].marks));
      setFeedback(grades[seg.id].feedback || '');
    } else {
      setMarks('');
      setFeedback('');
    }
  }, [currentIndex, segments, grades]);

  const currentSegment = segments[currentIndex] || null;
  const activeQuestion = readOnly ? (viewingQuestion || 1) : (gradingStatus?.current_grading_question || 1);
  const questionInfo = gradingStatus?.questions?.[activeQuestion - 1];
  const maxMarks = questionInfo?.max_marks || 10;

  const isGraded = (segId) => !!grades[segId];
  const allGradedForQuestion = segments.length > 0 && segments.every((s) => isGraded(s.id));

  const handleSaveGrade = async () => {
    if (!currentSegment || marks === '') return;
    const numMarks = parseFloat(marks);
    if (isNaN(numMarks) || numMarks < 0 || numMarks > maxMarks) {
      setError(`Marks must be between 0 and ${maxMarks}`);
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const existing = grades[currentSegment.id];
      if (existing) {
        // Update
        const response = await apiClient.patch(`/grading/grades/${existing.id}/`, {
          marks: numMarks,
          feedback,
        });
        setGrades((prev) => ({ ...prev, [currentSegment.id]: response.data }));
      } else {
        // Create
        const response = await apiClient.post('/grading/grades/', {
          exam: id,
          segment: currentSegment.id,
          marks: numMarks,
          feedback,
        });
        setGrades((prev) => ({ ...prev, [currentSegment.id]: response.data }));
      }

      // Auto-advance to next ungraded
      if (currentIndex < segments.length - 1) {
        const nextUngraded = segments.findIndex(
          (s, i) => i > currentIndex && !grades[s.id] && s.id !== currentSegment.id
        );
        if (nextUngraded !== -1) {
          setCurrentIndex(nextUngraded);
        } else {
          setCurrentIndex(currentIndex + 1);
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleAdvanceQuestion = async () => {
    setAdvancing(true);
    setError(null);
    try {
      const response = await apiClient.post(`/exams/exams/${id}/advance-question/`);
      if (response.data.exam_status === 'completed') {
        navigate(`/report/${id}`);
        return;
      }
      // Reload everything for next question
      const status = await fetchGradingStatus();
      if (status) {
        await fetchSegmentsForQuestion(status.current_grading_question);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setAdvancing(false);
    }
  };

  const handleKeyDown = (e) => {
    if (readOnly) return;
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSaveGrade();
    }
  };

  const handleQuestionClick = async (questionNum) => {
    if (!readOnly) return;
    setViewingQuestion(questionNum);
    setLoading(true);
    await fetchSegmentsForQuestion(questionNum);
    setLoading(false);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
      </div>
    );
  }

  if (!gradingStatus) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error || 'Failed to load grading data.'}
        </div>
      </div>
    );
  }

  const gradedCount = segments.filter((s) => isGraded(s.id)).length;

  return (
    <div className="max-w-4xl mx-auto">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </button>

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold">
            {readOnly ? 'Review' : 'Grading'}: {gradingStatus.exam_name}
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Question {activeQuestion} of {gradingStatus.total_questions}
          </p>
        </div>
        {!readOnly && (
          <div className="text-right">
            <span className="text-sm text-gray-500">Progress</span>
            <p className="text-lg font-semibold">{gradedCount} / {segments.length} graded</p>
          </div>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4 flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-700 text-sm">
            Dismiss
          </button>
        </div>
      )}

      {/* Question tabs */}
      <div className="flex gap-1 mb-4 overflow-x-auto pb-2">
        {gradingStatus.questions.map((q) => {
          const isCurrent = q.question_number === activeQuestion;
          const isComplete = q.graded === q.total && q.total > 0;
          const isPast = q.question_number < activeQuestion;
          return (
            <button
              key={q.question_number}
              onClick={() => readOnly && handleQuestionClick(q.question_number)}
              disabled={!readOnly}
              className={`flex-shrink-0 px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${
                isCurrent
                  ? 'bg-blue-600 text-white border-blue-600'
                  : isComplete || isPast
                  ? 'bg-green-100 text-green-700 border-green-200'
                  : 'bg-gray-100 text-gray-400 border-gray-200'
              } ${readOnly && !isCurrent ? 'cursor-pointer hover:bg-blue-50 hover:border-blue-300 hover:text-blue-600' : ''} ${!readOnly ? 'cursor-default' : ''}`}
            >
              Q{q.question_number}
              {(isComplete || isPast) && <Check className="w-3 h-3 inline ml-1" />}
              {isCurrent && !isComplete && !readOnly && (
                <span className="ml-1 text-xs opacity-75">({q.graded}/{q.total})</span>
              )}
            </button>
          );
        })}
      </div>

      {segments.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <AlertTriangle className="w-12 h-12 text-orange-400 mx-auto mb-4" />
          <h2 className="text-lg font-medium text-gray-600 mb-2">No segments for Q{activeQuestion}</h2>
          <p className="text-gray-400 mb-4">
            No answer segments were detected for this question. You may need to review the segmentation.
          </p>
          {!readOnly && activeQuestion < gradingStatus.total_questions && (
            <button
              onClick={handleAdvanceQuestion}
              disabled={advancing}
              className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {advancing ? 'Advancing...' : `Skip to Q${activeQuestion + 1}`}
            </button>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Answer image — takes 2/3 */}
          <div className="lg:col-span-2 bg-white rounded-lg shadow">
            <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
              <span className="text-sm font-medium text-gray-700">
                Answer {currentIndex + 1} of {segments.length}
                {currentSegment && (
                  <span className="text-gray-400 ml-2">
                    (Sheet {currentSegment.answer_sheet?.short_id || currentSegment.answer_sheet})
                  </span>
                )}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentIndex(Math.max(0, currentIndex - 1))}
                  disabled={currentIndex === 0}
                  className="p-1 rounded hover:bg-gray-100 disabled:opacity-30"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <button
                  onClick={() => setCurrentIndex(Math.min(segments.length - 1, currentIndex + 1))}
                  disabled={currentIndex === segments.length - 1}
                  className="p-1 rounded hover:bg-gray-100 disabled:opacity-30"
                >
                  <ChevronRight className="w-5 h-5" />
                </button>
              </div>
            </div>
            <div className="p-4 flex items-center justify-center min-h-[400px] bg-gray-50">
              {currentSegment ? (
                <img
                  src={currentSegment.image.startsWith('http') ? currentSegment.image : currentSegment.image.startsWith('/') ? currentSegment.image : `/media/${currentSegment.image}`}
                  alt={`Answer for Q${activeQuestion}`}
                  className="max-w-full max-h-[600px] object-contain rounded"
                />
              ) : (
                <p className="text-gray-400">No segment to display</p>
              )}
            </div>
            {/* Thumbnail strip */}
            {segments.length > 1 && (
              <div className="px-4 py-3 border-t border-gray-100 flex gap-2 overflow-x-auto">
                {segments.map((seg, i) => (
                  <button
                    key={seg.id}
                    onClick={() => setCurrentIndex(i)}
                    className={`flex-shrink-0 w-10 h-10 rounded-lg text-xs font-medium flex items-center justify-center border-2 transition-colors ${
                      i === currentIndex
                        ? 'border-blue-500 bg-blue-50 text-blue-700'
                        : isGraded(seg.id)
                        ? 'border-green-400 bg-green-50 text-green-700'
                        : 'border-gray-200 bg-gray-50 text-gray-500'
                    }`}
                  >
                    {isGraded(seg.id) ? <Check className="w-4 h-4" /> : i + 1}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Grading panel — takes 1/3 */}
          <div className="space-y-4">
            <div className="bg-white rounded-lg shadow p-4">
              <h3 className="font-semibold mb-3">
                Q{activeQuestion} — Max {maxMarks} marks
              </h3>

              {readOnly ? (
                /* Read-only grade display */
                <div>
                  {isGraded(currentSegment?.id) ? (
                    <>
                      <div className="mb-3">
                        <label className="block text-sm font-medium text-gray-700 mb-1">Marks</label>
                        <p className="text-lg font-semibold text-gray-900">
                          {grades[currentSegment.id].marks} / {maxMarks}
                        </p>
                      </div>
                      {grades[currentSegment.id].feedback && (
                        <div className="mb-3">
                          <label className="block text-sm font-medium text-gray-700 mb-1">Feedback</label>
                          <p className="text-sm text-gray-600 bg-gray-50 rounded-lg px-3 py-2">
                            {grades[currentSegment.id].feedback}
                          </p>
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="text-sm text-gray-400 italic">Not graded</p>
                  )}
                </div>
              ) : (
                /* Editable grading inputs */
                <>
                  <div className="mb-3">
                    <label className="block text-sm font-medium text-gray-700 mb-1">Marks</label>
                    <input
                      type="number"
                      min="0"
                      max={maxMarks}
                      step="0.5"
                      value={marks}
                      onChange={(e) => setMarks(e.target.value)}
                      onKeyDown={handleKeyDown}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-lg font-semibold focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      placeholder={`0 - ${maxMarks}`}
                    />
                  </div>

                  <div className="mb-3">
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Feedback <span className="text-gray-400">(optional)</span>
                    </label>
                    <textarea
                      value={feedback}
                      onChange={(e) => setFeedback(e.target.value)}
                      rows={2}
                      className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      placeholder="Add feedback..."
                    />
                  </div>

                  <button
                    onClick={handleSaveGrade}
                    disabled={saving || marks === ''}
                    className="w-full bg-blue-600 text-white py-2 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {saving ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Check className="w-4 h-4" />
                    )}
                    {saving ? 'Saving...' : isGraded(currentSegment?.id) ? 'Update Grade' : 'Save Grade'}
                  </button>

                  {isGraded(currentSegment?.id) && (
                    <p className="text-xs text-green-600 text-center mt-2">
                      Graded: {grades[currentSegment.id].marks} / {maxMarks}
                    </p>
                  )}
                </>
              )}
            </div>

            {/* Progress + advance — hidden in read-only mode */}
            {!readOnly && (
              <div className="bg-white rounded-lg shadow p-4">
                <h3 className="font-semibold mb-2">Q{activeQuestion} Progress</h3>
                <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
                  <div
                    className="bg-green-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${segments.length > 0 ? (gradedCount / segments.length) * 100 : 0}%` }}
                  />
                </div>
                <p className="text-sm text-gray-500 mb-3">
                  {gradedCount} of {segments.length} answers graded
                </p>

                {allGradedForQuestion && (
                  <button
                    onClick={handleAdvanceQuestion}
                    disabled={advancing}
                    className="w-full bg-green-600 text-white py-2 rounded-lg font-medium hover:bg-green-700 disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {advancing ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <ChevronRight className="w-4 h-4" />
                    )}
                    {advancing
                      ? 'Advancing...'
                      : activeQuestion >= gradingStatus.total_questions
                      ? 'Finish Grading'
                      : `Next: Q${activeQuestion + 1}`}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default GradingInterface;
