import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import DocumentsPage from "./pages/DocumentsPage";
import ReviewPage from "./pages/ReviewPage";
import StatsPage from "./pages/StatsPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DocumentsPage />} />
        <Route path="/documents/:documentId" element={<ReviewPage />} />
        <Route path="/documents/:documentId/stats" element={<StatsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
