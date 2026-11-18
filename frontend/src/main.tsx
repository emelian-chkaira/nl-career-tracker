import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/features/auth/AuthContext";
import App from "@/app/App";
import "@/shared/ui/styles.css";

const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: (n, e) => { const st = (e as { status?: number }).status; return n < 2 && !(st && st < 500); } } } });
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><QueryClientProvider client={qc}><BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter></QueryClientProvider></React.StrictMode>);
