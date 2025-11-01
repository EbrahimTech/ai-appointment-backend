"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { z } from "zod";

type TemplateItem = {
  key: string;
  lang: string;
  channel: string;
  hsm: boolean;
  variables: string[];
  enabled: boolean;
};

const updateSchema = z.object({
  templates: z.array(
    z.object({
      key: z.string().min(1),
      lang: z.string().min(1),
      enabled: z.boolean().optional(),
      variables: z.array(z.string()).optional(),
    })
  ),
});

export default function TemplatesPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const queryClient = useQueryClient();
  const { support } = useSupportSession();
  const readOnly = Boolean(support);

  const [lang, setLang] = useState<string>("en");
  const [search, setSearch] = useState<string>("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewRequest, setPreviewRequest] = useState<{ template_key: string; variables?: Record<string, string> } | null>(null);
  const [previewResult, setPreviewResult] = useState<string | null>(null);

  const templatesQuery = useQuery({
    queryKey: ["templates", slug, lang, search],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (lang) params.set("lang", lang);
      if (search) params.set("q", search);
      const url = `/api/proxy/clinic/${slug}/templates?${params.toString()}`;
      const response = await fetch(url);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load templates");
      }
      return payload.data.items as TemplateItem[];
    },
  });

  const updateMutation = useMutation({
    mutationFn: async (payload: { templates: { key: string; lang: string; enabled?: boolean; variables?: string[] }[] }) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/templates`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "UPDATE_FAILED");
      }
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates", slug, lang, search] });
      setFeedback("Templates updated successfully.");
      setError(null);
    },
    onError: (err: Error) => {
      setError(err.message);
      setFeedback(null);
    },
  });

  const previewMutation = useMutation({
    mutationFn: async (payload: { template_key: string; variables?: Record<string, string> }) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/templates/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "PREVIEW_FAILED");
      }
      return result.data as { rendered: string };
    },
    onSuccess: (data) => {
      setPreviewResult(data.rendered);
      setError(null);
    },
    onError: (err: Error) => {
      setPreviewResult(null);
      setError(err.message);
    },
  });

  const templates = useMemo(() => templatesQuery.data ?? [], [templatesQuery.data]);

  function toggleTemplate(template: TemplateItem, enabled: boolean) {
    if (readOnly) {
      setError("Cannot modify templates while impersonating. End support session first.");
      return;
    }
    const payload = updateSchema.safeParse({
      templates: [{ key: template.key, lang: template.lang, enabled }],
    });
    if (!payload.success) {
      setError(payload.error.issues[0]?.message ?? "Invalid payload");
      return;
    }
    updateMutation.mutate(payload.data);
  }

  function previewTemplate(template: TemplateItem) {
    let variables: Record<string, string> | undefined;
    if (template.variables?.length) {
      variables = template.variables.reduce<Record<string, string>>((acc, current) => {
        acc[current] = "";
        return acc;
      }, {});
    }
    const payload = {
      template_key: template.key,
      variables,
    };
    setPreviewRequest(payload);
    previewMutation.mutate(payload);
  }

  return (
    <main className="space-y-8 px-6 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Templates</h1>
          <p className="text-sm text-muted-foreground">Manage WhatsApp templates for automated replies.</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={lang}
            onChange={(event) => setLang(event.target.value)}
            className="rounded border px-3 py-2 text-sm"
          >
            <option value="en">English</option>
            <option value="ar">Arabic</option>
          </select>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search templates"
            className="rounded border px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={() => templatesQuery.refetch()}
            className="rounded border px-3 py-2 text-sm"
          >
            Refresh
          </button>
        </div>
      </header>
      {readOnly ? (
        <div className="rounded border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          You are impersonating a clinic. Template modifications are disabled until the support session ends.
        </div>
      ) : null}

      {feedback ? (
        <div className="rounded border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{feedback}</div>
      ) : null}
      {error ? (
        <div className="rounded border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>
      ) : null}

      <section className="rounded-lg border bg-white shadow-sm">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-secondary/40">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Key</th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Variables</th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-muted-foreground">HSM</th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Enabled</th>
              <th className="px-4 py-3 text-right text-xs font-semibold uppercase text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {templatesQuery.isPending ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-sm text-muted-foreground">
                  Loading templates...
                </td>
              </tr>
            ) : templates.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-sm text-muted-foreground">
                  No templates found for this language.
                </td>
              </tr>
            ) : (
              templates.map((template) => (
                <tr key={`${template.lang}-${template.key}`}>
                  <td className="px-4 py-3 text-sm font-medium">{template.key}</td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">
                    {template.variables?.length ? template.variables.join(", ") : "—"}
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">{template.hsm ? "Yes" : "No"}</td>
                  <td className="px-4 py-3 text-sm">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                        template.enabled ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {template.enabled ? "Enabled" : "Disabled"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-sm">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        className="rounded border px-2 py-1 text-xs"
                        onClick={() => previewTemplate(template)}
                      >
                        Preview
                      </button>
                      <button
                        type="button"
                        className="rounded border px-2 py-1 text-xs"
                        onClick={() => toggleTemplate(template, !template.enabled)}
                        disabled={updateMutation.isPending || readOnly}
                      >
                        {template.enabled ? "Disable" : "Enable"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {previewRequest ? (
        <div className="rounded-lg border bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Preview</h2>
              <p className="text-sm text-muted-foreground">
                Template: <span className="font-medium">{previewRequest.template_key}</span>
              </p>
            </div>
            <button
              type="button"
              className="text-sm text-muted-foreground underline"
              onClick={() => {
                setPreviewRequest(null);
                setPreviewResult(null);
              }}
            >
              Close
            </button>
          </div>
          {previewMutation.isPending ? (
            <p className="mt-4 text-sm text-muted-foreground">Generating preview...</p>
          ) : previewResult ? (
            <div className="mt-4 rounded border bg-slate-50 p-4 text-sm">
              <pre className="whitespace-pre-wrap text-slate-700">{previewResult}</pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </main>
  );
}
