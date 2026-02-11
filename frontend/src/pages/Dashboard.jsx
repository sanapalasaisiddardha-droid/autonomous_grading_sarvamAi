import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight, FolderOpen, Users, BookOpen, Plus, ArrowLeft, Trash2 } from 'lucide-react';
import useExamStore from '../store/examStore';

function Dashboard() {
  const navigate = useNavigate();
  const {
    classes, classSections, exams,
    fetchClasses, fetchClassSections, fetchExamsByClassSection,
    deleteClass, deleteExam,
    loading, error,
    dashLevel, dashSelectedClass, dashSelectedSection, setDashNav,
  } = useExamStore();

  const level = dashLevel;
  const selectedClass = dashSelectedClass;
  const selectedSection = dashSelectedSection;
  const setLevel = (l) => setDashNav(l, dashSelectedClass, dashSelectedSection);
  const [confirmDelete, setConfirmDelete] = useState(null); // exam id pending confirmation
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    fetchClasses();
    // Restore drill-down data when returning from another page
    if (dashLevel === 2 && dashSelectedClass) {
      fetchClassSections(dashSelectedClass);
    } else if (dashLevel === 3 && dashSelectedSection) {
      fetchExamsByClassSection(dashSelectedSection.id);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleClassClick = (className) => {
    setDashNav(2, className, null);
    fetchClassSections(className);
  };

  const handleSectionClick = (section) => {
    setDashNav(3, selectedClass, section);
    fetchExamsByClassSection(section.id);
  };

  const handleBack = () => {
    if (level === 3) {
      setDashNav(2, selectedClass, null);
    } else if (level === 2) {
      setDashNav(1, null, null);
    }
  };

  const handleExamClick = (exam) => {
    const routeMap = {
      created: `/exam/new`,
      processing: `/processing/${exam.id}`,
      review: `/review/${exam.id}`,
      grading: `/grading/${exam.id}`,
      completed: `/report/${exam.id}`,
    };
    navigate(routeMap[exam.status] || `/processing/${exam.id}`);
  };

  const handleNewExam = () => {
    navigate('/exam/new', {
      state: selectedSection
        ? { class_name: selectedSection.class_name, section: selectedSection.section }
        : undefined,
    });
  };

  const handleDeleteClass = async (className) => {
    setDeleting(true);
    try {
      await deleteClass(className);
      setConfirmDelete(null);
    } catch {
      // error is set in store
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteExam = async (examId) => {
    setDeleting(true);
    try {
      await deleteExam(examId);
      setConfirmDelete(null);
      // Refresh counts at all levels
      fetchClasses();
      if (selectedSection) fetchExamsByClassSection(selectedSection.id);
      if (selectedClass) fetchClassSections(selectedClass);
    } catch {
      // error is set in store
    } finally {
      setDeleting(false);
    }
  };

  const breadcrumbs = ['Dashboard'];
  if (selectedClass) breadcrumbs.push(`Class ${selectedClass}`);
  if (selectedSection) breadcrumbs.push(`Section ${selectedSection.section}`);

  const statusColors = {
    created: 'bg-gray-100 text-gray-700',
    processing: 'bg-yellow-100 text-yellow-700',
    review: 'bg-orange-100 text-orange-700',
    grading: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
  };

  return (
    <div className="max-w-4xl mx-auto">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-gray-500 mb-4">
        {breadcrumbs.map((crumb, i) => (
          <span key={i} className="flex items-center gap-2">
            {i > 0 && <ChevronRight className="w-3 h-3" />}
            <span className={i === breadcrumbs.length - 1 ? 'text-gray-900 font-medium' : ''}>
              {crumb}
            </span>
          </span>
        ))}
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          {level > 1 && (
            <button
              onClick={handleBack}
              className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
          )}
          <h1 className="text-2xl font-bold">
            {level === 1 && 'Classes'}
            {level === 2 && `Class ${selectedClass} — Sections`}
            {level === 3 && `${selectedSection.class_name}-${selectedSection.section} — Exams`}
          </h1>
        </div>
        <button
          onClick={handleNewExam}
          className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Exam
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      {loading && (
        <div className="text-center text-gray-500 py-12">Loading...</div>
      )}

      {/* Level 1: Classes */}
      {level === 1 && !loading && (
        <>
          {classes.length === 0 ? (
            <div className="text-center py-16 bg-white rounded-lg shadow">
              <FolderOpen className="w-12 h-12 text-gray-300 mx-auto mb-4" />
              <h2 className="text-lg font-medium text-gray-600 mb-2">No classes yet</h2>
              <p className="text-gray-400 mb-6">Create your first exam to get started</p>
              <button
                onClick={handleNewExam}
                className="inline-flex items-center gap-2 bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
              >
                <Plus className="w-4 h-4" />
                New Exam
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {classes.map((cls) => (
                <div key={cls.class_name} className="bg-white rounded-lg shadow hover:shadow-md transition-shadow">
                  {/* Confirm delete banner */}
                  {confirmDelete === `class:${cls.class_name}` && (
                    <div className="bg-red-50 border-b border-red-200 px-4 py-3 rounded-t-lg">
                      <p className="text-sm text-red-700 mb-2">
                        Delete Class "{cls.class_name}" with all its sections, students, exams, and files?
                      </p>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setConfirmDelete(null)}
                          disabled={deleting}
                          className="text-sm px-3 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={() => handleDeleteClass(cls.class_name)}
                          disabled={deleting}
                          className="text-sm px-3 py-1 rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
                        >
                          {deleting ? 'Deleting...' : 'Confirm Delete'}
                        </button>
                      </div>
                    </div>
                  )}
                  <div className="p-5">
                    <div className="flex items-center justify-between mb-3">
                      <FolderOpen className="w-8 h-8 text-blue-500" />
                      <div className="flex items-center gap-1">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            const key = `class:${cls.class_name}`;
                            setConfirmDelete(confirmDelete === key ? null : key);
                          }}
                          className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                          title="Delete class"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                        <ChevronRight className="w-5 h-5 text-gray-300" />
                      </div>
                    </div>
                    <button
                      onClick={() => handleClassClick(cls.class_name)}
                      className="w-full text-left"
                    >
                      <h3 className="text-lg font-semibold">Class {cls.class_name}</h3>
                      <div className="flex gap-4 mt-2 text-sm text-gray-500">
                        <span>{cls.section_count} section{cls.section_count !== 1 ? 's' : ''}</span>
                        <span>{cls.student_count} student{cls.student_count !== 1 ? 's' : ''}</span>
                        <span>{cls.exam_count} exam{cls.exam_count !== 1 ? 's' : ''}</span>
                      </div>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Level 2: Sections */}
      {level === 2 && !loading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {classSections.length === 0 ? (
            <div className="col-span-full text-center py-12 text-gray-500">
              No sections found for this class.
            </div>
          ) : (
            classSections.map((section) => (
              <button
                key={section.id}
                onClick={() => handleSectionClick(section)}
                className="bg-white rounded-lg shadow p-5 text-left hover:shadow-md transition-shadow group"
              >
                <div className="flex items-center justify-between mb-3">
                  <Users className="w-8 h-8 text-indigo-500" />
                  <ChevronRight className="w-5 h-5 text-gray-300 group-hover:text-gray-500 transition-colors" />
                </div>
                <h3 className="text-lg font-semibold">Section {section.section}</h3>
                <div className="flex gap-4 mt-2 text-sm text-gray-500">
                  <span>{section.student_count} student{section.student_count !== 1 ? 's' : ''}</span>
                  <span>{section.exam_count} exam{section.exam_count !== 1 ? 's' : ''}</span>
                </div>
              </button>
            ))
          )}
        </div>
      )}

      {/* Level 3: Exams */}
      {level === 3 && !loading && (
        <div className="space-y-3">
          {exams.length === 0 ? (
            <div className="text-center py-12 bg-white rounded-lg shadow">
              <BookOpen className="w-12 h-12 text-gray-300 mx-auto mb-4" />
              <h2 className="text-lg font-medium text-gray-600 mb-2">No exams yet</h2>
              <p className="text-gray-400 mb-6">Create an exam for this class-section</p>
              <button
                onClick={handleNewExam}
                className="inline-flex items-center gap-2 bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700"
              >
                <Plus className="w-4 h-4" />
                New Exam
              </button>
            </div>
          ) : (
            exams.map((exam) => (
              <div key={exam.id} className="bg-white rounded-lg shadow hover:shadow-md transition-shadow">
                {/* Confirm delete banner */}
                {confirmDelete === exam.id && (
                  <div className="bg-red-50 border-b border-red-200 px-4 py-3 rounded-t-lg flex items-center justify-between">
                    <span className="text-sm text-red-700">
                      Delete "{exam.name}" and all its sheets, segments, and files?
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => setConfirmDelete(null)}
                        disabled={deleting}
                        className="text-sm px-3 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => handleDeleteExam(exam.id)}
                        disabled={deleting}
                        className="text-sm px-3 py-1 rounded bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
                      >
                        {deleting ? 'Deleting...' : 'Confirm Delete'}
                      </button>
                    </div>
                  </div>
                )}
                <div className="p-4 flex items-center justify-between">
                  <button
                    onClick={() => handleExamClick(exam)}
                    className="flex-1 text-left"
                  >
                    <h3 className="font-semibold">{exam.name}</h3>
                    <div className="flex gap-4 mt-1 text-sm text-gray-500">
                      <span>{exam.subject}</span>
                      <span>{exam.sheet_count} sheet{exam.sheet_count !== 1 ? 's' : ''}</span>
                      <span>{exam.total_questions} question{exam.total_questions !== 1 ? 's' : ''}</span>
                    </div>
                  </button>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${statusColors[exam.status] || ''}`}>
                      {exam.status}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmDelete(confirmDelete === exam.id ? null : exam.id);
                      }}
                      className="p-2 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                      title="Delete exam"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                    <ChevronRight className="w-5 h-5 text-gray-300" />
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

export default Dashboard;
