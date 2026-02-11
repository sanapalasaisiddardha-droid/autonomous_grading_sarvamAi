import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import ExamSetup from './pages/ExamSetup';
import ProcessingStatus from './pages/ProcessingStatus';
import SegmentReview from './pages/SegmentReview';
import GradingInterface from './pages/GradingInterface';
import ReportDashboard from './pages/ReportDashboard';

function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/exam/new" element={<ExamSetup />} />
        <Route path="/processing/:id" element={<ProcessingStatus />} />
        <Route path="/review/:id" element={<SegmentReview />} />
        <Route path="/grading/:id" element={<GradingInterface />} />
        <Route path="/report/:id" element={<ReportDashboard />} />
      </Routes>
    </Layout>
  );
}

export default App;
