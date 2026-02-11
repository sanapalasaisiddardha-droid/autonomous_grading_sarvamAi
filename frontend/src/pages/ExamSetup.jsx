import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useDropzone } from 'react-dropzone';
import { Upload, FileText, X, Plus, Minus, ArrowLeft } from 'lucide-react';
import apiClient from '../api/client';

function ExamSetup() {
  const navigate = useNavigate();
  const location = useLocation();
  const prefill = location.state || {};

  const [step, setStep] = useState(1); // 1 = exam details, 2 = upload PDFs
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exam, setExam] = useState(null);

  const [className, setClassName] = useState(prefill.class_name || '');
  const [section, setSection] = useState(prefill.section || '');

  const [formData, setFormData] = useState({
    name: '',
    subject: '',
    total_questions: 3,
    max_marks_per_question: [10, 10, 10],
  });

  const [files, setFiles] = useState([]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { 'application/pdf': ['.pdf'] },
    onDrop: (accepted) => {
      // Validate filename pattern: roll_subject.pdf
      const valid = [];
      const invalid = [];
      accepted.forEach((file) => {
        const match = file.name.match(/^(.+)_(.+)\.pdf$/i);
        if (match) {
          valid.push(file);
        } else {
          invalid.push(file.name);
        }
      });
      if (invalid.length > 0) {
        setError(`Invalid filenames (expected roll_subject.pdf): ${invalid.join(', ')}`);
      } else {
        setError(null);
      }
      setFiles((prev) => [...prev, ...valid]);
    },
  });

  const handleQuestionCountChange = (delta) => {
    const newCount = Math.max(1, formData.total_questions + delta);
    const marks = [...formData.max_marks_per_question];
    if (delta > 0) {
      marks.push(10);
    } else if (marks.length > 1) {
      marks.pop();
    }
    setFormData({ ...formData, total_questions: newCount, max_marks_per_question: marks });
  };

  const handleMarksChange = (index, value) => {
    const marks = [...formData.max_marks_per_question];
    marks[index] = parseInt(value) || 0;
    setFormData({ ...formData, max_marks_per_question: marks });
  };

  const handleCreateExam = async (e) => {
    e.preventDefault();
    if (!className.trim() || !section.trim()) {
      setError('Class and Section are required.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // 1. Get or create the ClassSection
      const csResponse = await apiClient.post('/exams/class-sections/get-or-create/', {
        class_name: className.trim(),
        section: section.trim(),
      });
      const classSectionId = csResponse.data.id;

      // 2. Create the exam linked to the ClassSection
      const response = await apiClient.post('/exams/exams/', {
        ...formData,
        class_section: classSectionId,
      });
      setExam(response.data);
      setStep(2);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadFiles = async () => {
    if (files.length === 0) {
      setError('Please add at least one PDF file.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      for (const file of files) {
        const fd = new FormData();
        fd.append('pdf_file', file);
        fd.append('exam', exam.id);
        const match = file.name.match(/^(.+)_(.+)\.pdf$/i);
        fd.append('roll_number', match[1]);
        await apiClient.post('/exams/sheets/', fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
        });
      }
      navigate(`/processing/${exam.id}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const removeFile = (index) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="max-w-2xl mx-auto">
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </button>
      <h1 className="text-2xl font-bold mb-6">Exam Setup</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg mb-4">
          {error}
        </div>
      )}

      {step === 1 && (
        <form onSubmit={handleCreateExam} className="space-y-6">
          <div className="bg-white rounded-lg shadow p-6 space-y-4">
            <h2 className="text-lg font-semibold">Exam Details</h2>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Class</label>
                <input
                  type="text"
                  required
                  value={className}
                  onChange={(e) => setClassName(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="e.g., 4"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Section</label>
                <input
                  type="text"
                  required
                  value={section}
                  onChange={(e) => setSection(e.target.value)}
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="e.g., B"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Exam Name</label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="e.g., Mid-Term Exam 2026"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Subject</label>
              <input
                type="text"
                required
                value={formData.subject}
                onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                placeholder="e.g., Physics"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Number of Questions</label>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => handleQuestionCountChange(-1)}
                  className="p-2 rounded-lg border border-gray-300 hover:bg-gray-100"
                >
                  <Minus className="w-4 h-4" />
                </button>
                <span className="text-lg font-semibold w-8 text-center">{formData.total_questions}</span>
                <button
                  type="button"
                  onClick={() => handleQuestionCountChange(1)}
                  className="p-2 rounded-lg border border-gray-300 hover:bg-gray-100"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Max Marks per Question</label>
              <div className="grid grid-cols-4 gap-2">
                {formData.max_marks_per_question.map((marks, i) => (
                  <div key={i} className="flex flex-col items-center">
                    <span className="text-xs text-gray-500 mb-1">Q{i + 1}</span>
                    <input
                      type="number"
                      min="1"
                      value={marks}
                      onChange={(e) => handleMarksChange(i, e.target.value)}
                      className="w-full border border-gray-300 rounded-lg px-2 py-1 text-center focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Creating...' : 'Create Exam & Continue'}
          </button>
        </form>
      )}

      {step === 2 && (
        <div className="space-y-6">
          <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg">
            Exam "{exam.name}" created. Now upload answer sheet PDFs.
          </div>

          <div className="bg-white rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold mb-4">Upload Answer Sheets</h2>
            <p className="text-sm text-gray-500 mb-4">
              Files must be named as <code className="bg-gray-100 px-1 rounded">rollnumber_subject.pdf</code> (e.g., <code className="bg-gray-100 px-1 rounded">2301_physics.pdf</code>)
            </p>

            <div
              {...getRootProps()}
              className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                isDragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
              }`}
            >
              <input {...getInputProps()} />
              <Upload className="w-10 h-10 text-gray-400 mx-auto mb-3" />
              <p className="text-gray-600">Drag & drop PDF files here, or click to select</p>
            </div>

            {files.length > 0 && (
              <div className="mt-4 space-y-2">
                <h3 className="text-sm font-medium text-gray-700">{files.length} file(s) selected</h3>
                {files.map((file, i) => (
                  <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-gray-400" />
                      <span className="text-sm">{file.name}</span>
                      <span className="text-xs text-gray-400">({(file.size / 1024).toFixed(1)} KB)</span>
                    </div>
                    <button onClick={() => removeFile(i)} className="text-red-400 hover:text-red-600">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <button
            onClick={handleUploadFiles}
            disabled={loading || files.length === 0}
            className="w-full bg-blue-600 text-white py-3 rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Uploading...' : `Upload ${files.length} File(s) & Start Processing`}
          </button>
        </div>
      )}
    </div>
  );
}

export default ExamSetup;
