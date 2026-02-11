import { create } from 'zustand';
import apiClient from '../api/client';

const useExamStore = create((set, get) => ({
  // Existing state
  exams: [],
  currentExam: null,
  loading: false,
  error: null,

  // Class/Section/Student state
  classes: [],
  classSections: [],
  students: [],
  currentClassSection: null,

  // Dashboard drill-down state (persists across navigations)
  dashLevel: 1,
  dashSelectedClass: null,
  dashSelectedSection: null,
  setDashNav: (level, selectedClass, selectedSection) =>
    set({ dashLevel: level, dashSelectedClass: selectedClass, dashSelectedSection: selectedSection }),

  // --- Class/Section actions ---

  fetchClasses: async () => {
    set({ loading: true, error: null });
    try {
      const response = await apiClient.get('/exams/class-sections/classes/');
      set({ classes: response.data, loading: false });
    } catch (error) {
      set({ error: error.message, loading: false });
    }
  },

  fetchClassSections: async (className) => {
    set({ loading: true, error: null });
    try {
      const response = await apiClient.get('/exams/class-sections/', {
        params: { class_name: className },
      });
      set({ classSections: response.data, loading: false });
    } catch (error) {
      set({ error: error.message, loading: false });
    }
  },

  fetchStudents: async (classSectionId) => {
    set({ loading: true, error: null });
    try {
      const response = await apiClient.get('/exams/students/', {
        params: { class_section: classSectionId },
      });
      set({ students: response.data, loading: false });
    } catch (error) {
      set({ error: error.message, loading: false });
    }
  },

  createClassSection: async (data) => {
    set({ loading: true, error: null });
    try {
      const response = await apiClient.post('/exams/class-sections/get-or-create/', data);
      set({ loading: false });
      return response.data;
    } catch (error) {
      set({ error: error.message, loading: false });
      throw error;
    }
  },

  fetchExamsByClassSection: async (classSectionId) => {
    set({ loading: true, error: null });
    try {
      const response = await apiClient.get('/exams/exams/', {
        params: { class_section: classSectionId },
      });
      set({ exams: response.data, loading: false });
    } catch (error) {
      set({ error: error.message, loading: false });
    }
  },

  setCurrentClassSection: (cs) => set({ currentClassSection: cs }),

  // --- Existing actions ---

  fetchExams: async () => {
    set({ loading: true, error: null });
    try {
      const response = await apiClient.get('/exams/exams/');
      set({ exams: response.data, loading: false });
    } catch (error) {
      set({ error: error.message, loading: false });
    }
  },

  fetchExam: async (id) => {
    set({ loading: true, error: null });
    try {
      const response = await apiClient.get(`/exams/exams/${id}/`);
      set({ currentExam: response.data, loading: false });
    } catch (error) {
      set({ error: error.message, loading: false });
    }
  },

  createExam: async (examData) => {
    set({ loading: true, error: null });
    try {
      const response = await apiClient.post('/exams/exams/', examData);
      set((state) => ({
        exams: [response.data, ...state.exams],
        currentExam: response.data,
        loading: false,
      }));
      return response.data;
    } catch (error) {
      set({ error: error.message, loading: false });
      throw error;
    }
  },

  deleteClass: async (className) => {
    set({ loading: true, error: null });
    try {
      await apiClient.post('/exams/class-sections/delete-class/', { class_name: className });
      set((state) => ({
        classes: state.classes.filter((c) => c.class_name !== className),
        loading: false,
      }));
    } catch (error) {
      set({ error: error.message, loading: false });
      throw error;
    }
  },

  deleteExam: async (examId) => {
    set({ loading: true, error: null });
    try {
      await apiClient.delete(`/exams/exams/${examId}/`);
      set((state) => ({
        exams: state.exams.filter((e) => e.id !== examId),
        loading: false,
      }));
    } catch (error) {
      set({ error: error.message, loading: false });
      throw error;
    }
  },

  clearError: () => set({ error: null }),
}));

export default useExamStore;
