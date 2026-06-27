import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import DocumentsPage from "./pages/DocumentsPage";
import ComparePage from "./pages/ComparePage";
import ReviewPage from "./pages/ReviewPage";
import StatsPage from "./pages/StatsPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DocumentsPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/documents/:documentId" element={<ReviewPage />} />
        <Route path="/documents/:documentId/stats" element={<StatsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
