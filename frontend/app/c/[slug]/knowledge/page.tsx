"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { Upload, CheckCircle2, Search, FileText, Languages, Tag } from "lucide-react";

type PreviewResult = {
  chunks: {
    id: number | string;
    lang: string;
    tag: string;
    score?: number;
    excerpt: string;
  }[];
  answer?: string;
};

export default function KnowledgePage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const { support } = useSupportSession();
  const readOnly = Boolean(support);
  const allowedTags = ["service", "policy", "faq", "about", "glossary"];

  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewQuery, setPreviewQuery] = useState("");
  const [previewLang, setPreviewLang] = useState("en");
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null);

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch(`/api/proxy/clinic/${slug}/kb/upload`, {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "UPLOAD_FAILED");
      }
      return payload;
    },
    onSuccess: () => {
      setFeedback("Knowledge uploaded. Publish to make it active.");
      setError(null);
    },
    onError: (err: Error) => {
      setError(err.message);
      setFeedback(null);
    },
  });

  const publishMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/kb/publish`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "PUBLISH_FAILED");
      }
      return payload;
    },
    onSuccess: () => {
      setFeedback("Knowledge published successfully.");
      setError(null);
    },
    onError: (err: Error) => {
      setError(err.message);
      setFeedback(null);
    },
  });

  const previewMutation = useMutation({
    mutationFn: async (vars: { q: string; lang: string }) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/kb/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ q: vars.q, lang: vars.lang }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "PREVIEW_FAILED");
      }
      return payload.data as PreviewResult;
    },
    onSuccess: (data) => {
      setPreviewResult(data);
      setError(null);
    },
    onError: (err: Error) => {
      setError(err.message);
      setPreviewResult(null);
    },
  });

  async function handleUpload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (readOnly) {
      setError("Cannot upload knowledge while impersonating. End support session first.");
      setFeedback(null);
      return;
    }
    const fileInput = event.currentTarget.querySelector<HTMLInputElement>("input[type='file']");
    const file = fileInput?.files?.[0];
    if (!file) {
      setError("Please choose a YAML file to upload.");
      return;
    }
    uploadMutation.mutate(file);
    event.currentTarget.reset();
  }

  function handlePublish() {
    if (readOnly) {
      setError("Cannot publish while impersonating. End support session first.");
      setFeedback(null);
      return;
    }
    publishMutation.mutate();
  }

  function handlePreview(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!previewQuery.trim()) {
      setError("Enter a question to preview.");
      return;
    }
    previewMutation.mutate({ q: previewQuery, lang: previewLang });
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 px-6 py-8">
      <div className="mx-auto max-w-5xl space-y-8">
        <header className="space-y-2">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-primary/10 p-3">
              <FileText className="h-6 w-6 text-primary" />
            </div>
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Knowledge Base</h1>
              <p className="text-sm text-muted-foreground">
                Upload YAML documents, publish them, and preview AI retrieval responses
              </p>
            </div>
          </div>
        </header>

        {readOnly ? (
          <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 shadow-sm">
            <div className="mt-0.5 rounded-full bg-amber-200 p-1">
              <svg className="h-4 w-4 text-amber-700" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
              </svg>
            </div>
            <div className="flex-1 text-sm text-amber-900">
              <p className="font-medium">Support Mode Active</p>
              <p className="mt-1 text-amber-800">Upload and publish actions are disabled while impersonating a clinic. End the support session to make changes.</p>
            </div>
          </div>
        ) : null}

        {feedback ? (
          <div className="flex items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 shadow-sm">
            <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            <p className="flex-1 text-sm font-medium text-emerald-700">{feedback}</p>
          </div>
        ) : null}
        {error ? (
          <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 shadow-sm">
            <svg className="h-5 w-5 text-red-600" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <p className="flex-1 text-sm font-medium text-red-700">{error}</p>
          </div>
        ) : null}

        <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-md transition-shadow hover:shadow-lg">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-blue-50 p-2">
              <Upload className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Upload YAML</h2>
              <p className="text-xs text-muted-foreground">Upload knowledge base documents</p>
            </div>
          </div>
          <div className="rounded-lg bg-slate-50 p-4">
            <p className="text-sm text-slate-600">
              <span className="font-medium">Format:</span> <code className="rounded bg-white px-2 py-0.5 text-xs">.yaml</code> or <code className="rounded bg-white px-2 py-0.5 text-xs">.yml</code>
            </p>
            <p className="mt-2 text-sm text-slate-600">
              <span className="font-medium">Required fields:</span>{" "}
              <code className="rounded bg-white px-2 py-0.5 text-xs">title</code>,{" "}
              <code className="rounded bg-white px-2 py-0.5 text-xs">language</code> (en/ar),{" "}
              <code className="rounded bg-white px-2 py-0.5 text-xs">tag</code> ({allowedTags.join(", ")}),{" "}
              <code className="rounded bg-white px-2 py-0.5 text-xs">body</code>
            </p>
          </div>
          <form className="flex flex-col gap-4 md:flex-row md:items-end" onSubmit={handleUpload}>
            <div className="flex-1 space-y-2">
              <label className="text-sm font-medium text-slate-700" htmlFor="kb-upload">
                Knowledge file
              </label>
              <input
                id="kb-upload"
                type="file"
                accept=".yaml,.yml"
                className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm transition-colors file:mr-4 file:rounded-md file:border-0 file:bg-primary file:px-4 file:py-1.5 file:text-sm file:font-medium file:text-primary-foreground hover:file:bg-primary/90 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
              />
            </div>
            <button
              type="submit"
              className="flex items-center justify-center gap-2 rounded-lg bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground shadow-sm transition-all hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={uploadMutation.isPending || readOnly}
            >
              <Upload className="h-4 w-4" />
              {uploadMutation.isPending ? "Uploading..." : "Upload"}
            </button>
          </form>
        </section>

        <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-md transition-shadow hover:shadow-lg">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-emerald-50 p-2">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Publish Knowledge</h2>
              <p className="text-xs text-muted-foreground">Make uploaded documents active for AI retrieval</p>
            </div>
          </div>
          <div className="rounded-lg border-l-4 border-emerald-500 bg-emerald-50 p-4">
            <p className="text-sm text-emerald-900">
              <span className="font-medium">Note:</span> Publishing will index all uploaded documents and make them available for the AI assistant to use when answering questions.
            </p>
          </div>
          <button
            type="button"
            onClick={handlePublish}
            className="flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={publishMutation.isPending || readOnly}
          >
            <CheckCircle2 className="h-4 w-4" />
            {publishMutation.isPending ? "Publishing..." : "Publish knowledge"}
          </button>
        </section>

        <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-md transition-shadow hover:shadow-lg">
          <div className="flex items-center gap-3">
            <div className="rounded-lg bg-purple-50 p-2">
              <Search className="h-5 w-5 text-purple-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Preview Retrieval</h2>
              <p className="text-xs text-muted-foreground">Test how the AI retrieves and uses your knowledge</p>
            </div>
          </div>
          <form className="grid gap-4 md:grid-cols-3" onSubmit={handlePreview}>
            <div className="md:col-span-2 space-y-2">
              <label className="flex items-center gap-2 text-sm font-medium text-slate-700" htmlFor="preview-query">
                <FileText className="h-4 w-4 text-slate-400" />
                Question
              </label>
              <input
                id="preview-query"
                value={previewQuery}
                onChange={(event) => setPreviewQuery(event.target.value)}
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm transition-colors focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-500/20"
                placeholder="Example: What whitening treatments do you offer?"
                required
              />
            </div>
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm font-medium text-slate-700" htmlFor="preview-lang">
                <Languages className="h-4 w-4 text-slate-400" />
                Language
              </label>
              <select
                id="preview-lang"
                value={previewLang}
                onChange={(event) => setPreviewLang(event.target.value)}
                className="w-full rounded-lg border border-slate-300 px-4 py-2.5 text-sm transition-colors focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-500/20"
              >
                <option value="en">English</option>
                <option value="ar">Arabic</option>
              </select>
            </div>
            <div className="md:col-span-3 flex items-center gap-2">
              <button
                type="submit"
                className="flex items-center justify-center gap-2 rounded-lg bg-purple-600 px-6 py-2.5 text-sm font-medium text-white shadow-sm transition-all hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-50"
                disabled={previewMutation.isPending}
              >
                <Search className="h-4 w-4" />
                {previewMutation.isPending ? "Searching..." : "Preview"}
              </button>
            </div>
          </form>
          {previewResult ? (
            <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-5">
              <div className="flex items-center gap-2">
                <Tag className="h-4 w-4 text-slate-500" />
                <h3 className="text-sm font-semibold text-slate-700">Retrieved Chunks ({previewResult.chunks.length})</h3>
              </div>
              {previewResult.chunks.length > 0 ? (
                <ul className="space-y-3">
                  {previewResult.chunks.map((chunk) => (
                    <li key={chunk.id} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md">
                      <div className="mb-2 flex items-center gap-2">
                        <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-700">
                          {chunk.lang.toUpperCase()}
                        </span>
                        <span className="rounded-full bg-purple-100 px-2.5 py-0.5 text-xs font-medium text-purple-700">
                          {chunk.tag}
                        </span>
                        {typeof chunk.score === "number" ? (
                          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700">
                            score: {chunk.score.toFixed(2)}
                          </span>
                        ) : null}
                      </div>
                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-600">{chunk.excerpt}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-center text-sm text-slate-500">No chunks found</p>
              )}
              {previewResult.answer ? (
                <div className="mt-4 rounded-lg border-l-4 border-emerald-500 bg-emerald-50 px-4 py-3">
                  <p className="text-xs font-semibold text-emerald-900">AI Answer Preview:</p>
                  <p className="mt-1 text-sm text-emerald-800">{previewResult.answer}</p>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
