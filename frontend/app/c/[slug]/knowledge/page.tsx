"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";

type PreviewResult = {
  chunks: {
    id: number | string;
    lang: string;
    tag: string;
    excerpt: string;
  }[];
  answer?: string;
};

export default function KnowledgePage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const { support } = useSupportSession();
  const readOnly = Boolean(support);

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
    <main className="space-y-8 px-6 py-8">
      <header>
        <h1 className="text-2xl font-semibold">Knowledge base</h1>
        <p className="text-sm text-muted-foreground">
          Upload YAML, publish the latest version, and preview retrieval responses.
        </p>
      </header>

      {readOnly ? (
        <div className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          You are impersonating a clinic. Upload and publish actions are disabled until the support session ends.
        </div>
      ) : null}

      {feedback ? (
        <div className="rounded border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {feedback}
        </div>
      ) : null}
      {error ? (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      ) : null}

      <section className="space-y-4 rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Upload YAML</h2>
        <form className="flex flex-col gap-4 md:flex-row md:items-end" onSubmit={handleUpload}>
          <div className="flex-1 space-y-1">
            <label className="text-sm font-medium" htmlFor="kb-upload">
              Knowledge file
            </label>
            <input id="kb-upload" type="file" accept=".yaml,.yml" className="w-full text-sm" />
          </div>
          <button
            type="submit"
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
            disabled={uploadMutation.isPending || readOnly}
          >
            {uploadMutation.isPending ? "Uploading..." : "Upload"}
          </button>
        </form>
      </section>

      <section className="space-y-4 rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Publish</h2>
        <button
          type="button"
          onClick={handlePublish}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
          disabled={publishMutation.isPending || readOnly}
        >
          {publishMutation.isPending ? "Publishing..." : "Publish knowledge"}
        </button>
      </section>

      <section className="space-y-4 rounded-lg border bg-white p-4 shadow-sm">
        <h2 className="text-lg font-semibold">Preview</h2>
        <form className="grid gap-4 md:grid-cols-3" onSubmit={handlePreview}>
          <div className="md:col-span-2 space-y-1">
            <label className="text-sm font-medium" htmlFor="preview-query">
              Question
            </label>
            <input
              id="preview-query"
              value={previewQuery}
              onChange={(event) => setPreviewQuery(event.target.value)}
              className="w-full rounded border px-3 py-2 text-sm"
              placeholder="Example: What whitening treatments do you offer?"
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="preview-lang">
              Language
            </label>
            <select
              id="preview-lang"
              value={previewLang}
              onChange={(event) => setPreviewLang(event.target.value)}
              className="w-full rounded border px-3 py-2 text-sm"
            >
              <option value="en">English</option>
              <option value="ar">Arabic</option>
            </select>
          </div>
          <div className="md:col-span-3 flex items-center gap-2">
            <button type="submit" className="rounded-md border px-4 py-2 text-sm" disabled={previewMutation.isPending}>
              {previewMutation.isPending ? "Previewing..." : "Preview"}
            </button>
          </div>
        </form>
        {previewResult ? (
          <div className="rounded border bg-slate-50 p-4 text-sm">
            <h3 className="text-sm font-semibold text-muted-foreground">Chunks</h3>
            <ul className="mt-2 space-y-2">
              {previewResult.chunks.map((chunk) => (
                <li key={chunk.id} className="rounded border bg-white px-3 py-2">
                  <p className="font-medium">
                    [{chunk.lang}] {chunk.tag}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap text-muted-foreground">{chunk.excerpt}</p>
                </li>
              ))}
            </ul>
            {previewResult.answer ? (
              <div className="mt-4 rounded border border-primary/40 bg-primary/10 px-3 py-2">
                <span className="font-semibold">Answer preview:</span> {previewResult.answer}
              </div>
            ) : null}
          </div>
        ) : null}
      </section>
    </main>
  );
}
