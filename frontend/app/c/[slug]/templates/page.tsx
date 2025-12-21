"use client";

import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSupportSession } from "../../../providers";
import { z } from "zod";
import { FileText, Search, Globe, RefreshCw, Eye, ToggleLeft, ToggleRight, X, CheckCircle2, XCircle, AlertCircle, Plus } from "lucide-react";

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
  const readOnly = support?.readOnly ?? false;

  const [lang, setLang] = useState<string>("");
  const [search, setSearch] = useState<string>("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [previewRequest, setPreviewRequest] = useState<{ template_key: string; variables?: Record<string, string> } | null>(null);
  const [previewResult, setPreviewResult] = useState<string | null>(null);

  // Add Template states
  const [showAddModal, setShowAddModal] = useState(false);
  const [newTemplateCode, setNewTemplateCode] = useState("");
  const [newTemplateLanguage, setNewTemplateLanguage] = useState("en");
  const [newTemplateBody, setNewTemplateBody] = useState("");
  const [newTemplateHsmName, setNewTemplateHsmName] = useState("");
  const [newTemplateVariables, setNewTemplateVariables] = useState("");

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

  const createMutation = useMutation({
    mutationFn: async (payload: { code: string; language: string; body: string; hsm_name?: string; variables?: string[] }) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/templates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "CREATE_FAILED");
      }
      return result.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates", slug, lang, search] });
      setFeedback("Template created successfully.");
      setError(null);
      setShowAddModal(false);
      // Reset form
      setNewTemplateCode("");
      setNewTemplateLanguage("en");
      setNewTemplateBody("");
      setNewTemplateHsmName("");
      setNewTemplateVariables("");
    },
    onError: (err: Error) => {
      setError(err.message);
      setFeedback(null);
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
        // Use sample values instead of empty strings for preview
        acc[current] = `[${current}]`;
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

  function handleCreateTemplate(event: React.FormEvent) {
    event.preventDefault();
    if (readOnly) {
      setError("Cannot create templates while impersonating. End support session first.");
      return;
    }

    const variables = newTemplateVariables
      .split(",")
      .map((v) => v.trim())
      .filter((v) => v);

    const payload = {
      code: newTemplateCode.trim(),
      language: newTemplateLanguage,
      body: newTemplateBody.trim(),
      hsm_name: newTemplateHsmName.trim() || undefined,
      variables: variables.length > 0 ? variables : undefined,
    };

    createMutation.mutate(payload);
  }

  if (templatesQuery.isPending) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading templates...</p>
        </div>
      </div>
    );
  }

  if (templatesQuery.isError) {
  return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-4">
          <div className="flex items-center justify-center w-16 h-16 rounded-full bg-red-100 mx-auto">
            <FileText className="w-8 h-8 text-red-600" />
          </div>
        <div>
            <p className="text-base font-medium text-gray-900 mb-1">Unable to load templates</p>
            <p className="text-sm text-gray-500 mb-4">Please try again</p>
          </div>
          <button
            type="button"
            onClick={() => templatesQuery.refetch()}
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            <span>Retry</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header Section */}
      <div className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-start justify-between mb-6">
            <div className="flex items-start gap-4">
              <div className="flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br from-purple-500 to-pink-600 text-white shadow-lg">
                <FileText className="w-7 h-7" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900 mb-2">Templates</h1>
                <p className="text-sm text-gray-600">Manage WhatsApp templates for automated replies</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setShowAddModal(true)}
                disabled={readOnly}
                className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
              >
                <Plus className="w-4 h-4" />
                <span>Add Template</span>
              </button>
              <button
                type="button"
                onClick={() => templatesQuery.refetch()}
                disabled={templatesQuery.isFetching}
                className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors shadow-sm"
              >
                <RefreshCw className={`w-4 h-4 ${templatesQuery.isFetching ? "animate-spin" : ""}`} />
                <span>Refresh</span>
              </button>
            </div>
          </div>

          {/* Filters */}
          <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
              <Globe className="w-4 h-4 text-gray-500" />
          <select
            value={lang}
            onChange={(event) => setLang(event.target.value)}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
          >
            <option value="">All Languages</option>
            <option value="ar">Arabic</option>
            <option value="en">English</option>
          </select>
            </div>
            <div className="flex-1 max-w-md">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search templates..."
                  className="w-full pl-10 pr-4 py-2 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Alerts */}
        {readOnly && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-900">Read-only mode</p>
              <p className="text-xs text-amber-700 mt-0.5">
                You are impersonating a clinic. Template modifications are disabled until the support session ends.
              </p>
            </div>
          </div>
        )}

        {feedback && (
          <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-green-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-green-900">{feedback}</p>
            </div>
          <button
            type="button"
              onClick={() => setFeedback(null)}
              className="text-green-600 hover:text-green-800"
          >
              <X className="w-4 h-4" />
          </button>
        </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 flex items-start gap-3">
            <XCircle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-red-900">{error}</p>
            </div>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-red-600 hover:text-red-800"
            >
              <X className="w-4 h-4" />
            </button>
        </div>
        )}

        {/* Templates Table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
            <tr>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Template Key
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Language
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Variables
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    HSM
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-4 text-right text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Actions
                  </th>
            </tr>
          </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {templates.length === 0 ? (
              <tr>
                    <td colSpan={6} className="px-6 py-12 text-center">
                      <div className="flex flex-col items-center">
                        <FileText className="w-12 h-12 text-gray-400 mb-3" />
                        <p className="text-sm font-medium text-gray-900 mb-1">No templates found</p>
                        <p className="text-xs text-gray-500">Try changing the language or search term</p>
                      </div>
                </td>
              </tr>
            ) : (
              templates.map((template) => (
                    <tr key={`${template.lang}-${template.key}`} className="hover:bg-gray-50 transition-colors">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-semibold text-gray-900">{template.key}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            template.lang === 'ar'
                              ? 'bg-amber-100 text-amber-700'
                              : template.lang === 'en_US'
                              ? 'bg-blue-100 text-blue-700'
                              : 'bg-green-100 text-green-700'
                          }`}
                        >
                          {template.lang === 'ar' ? 'Arabic' : 
                           template.lang === 'en_US' ? 'English (US)' : 
                           template.lang === 'en' ? 'English' : 
                           template.lang}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm text-gray-600">
                          {template.variables?.length ? (
                            <div className="flex flex-wrap gap-1">
                              {template.variables.map((variable, idx) => (
                                <span
                                  key={idx}
                                  className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-800"
                                >
                                  {variable}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-gray-400">—</span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            template.hsm ? "bg-purple-100 text-purple-700" : "bg-gray-100 text-gray-600"
                          }`}
                        >
                          {template.hsm ? "Yes" : "No"}
                        </span>
                  </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                    <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            template.enabled ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {template.enabled ? "Enabled" : "Disabled"}
                    </span>
                  </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-blue-600 hover:bg-blue-50 transition-colors"
                        onClick={() => previewTemplate(template)}
                      >
                            <Eye className="w-3.5 h-3.5" />
                            <span>Preview</span>
                      </button>
                      <button
                        type="button"
                            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                              template.enabled
                                ? "text-amber-600 hover:bg-amber-50"
                                : "text-green-600 hover:bg-green-50"
                            }`}
                        onClick={() => toggleTemplate(template, !template.enabled)}
                        disabled={updateMutation.isPending || readOnly}
                      >
                            {template.enabled ? (
                              <>
                                <ToggleRight className="w-3.5 h-3.5" />
                                <span>Disable</span>
                              </>
                            ) : (
                              <>
                                <ToggleLeft className="w-3.5 h-3.5" />
                                <span>Enable</span>
                              </>
                            )}
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
          </div>
        </div>

        {/* Preview Modal */}
        {previewRequest && (
          <div className="bg-white rounded-xl border border-gray-200 shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
            <div>
                <h2 className="text-lg font-semibold text-gray-900">Template Preview</h2>
                <p className="text-sm text-gray-600 mt-1">
                  Template: <span className="font-medium text-gray-900">{previewRequest.template_key}</span>
              </p>
            </div>
            <button
              type="button"
                className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              onClick={() => {
                setPreviewRequest(null);
                setPreviewResult(null);
              }}
            >
                <X className="w-5 h-5" />
            </button>
          </div>
          {previewMutation.isPending ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                <span className="ml-3 text-sm text-gray-600">Generating preview...</span>
              </div>
          ) : previewResult ? (
              <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
                <pre className="whitespace-pre-wrap text-sm text-gray-700 font-mono">{previewResult}</pre>
            </div>
          ) : null}
        </div>
        )}

        {/* Add Template Modal */}
        {showAddModal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 className="text-2xl font-bold text-gray-900">Add New Template</h2>
                    <p className="text-sm text-gray-600 mt-1">Create a new WhatsApp message template</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowAddModal(false)}
                    className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                <form onSubmit={handleCreateTemplate} className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <label className="block text-sm font-medium text-gray-700" htmlFor="template-code">
                        Template Code <span className="text-red-500">*</span>
                      </label>
                      <input
                        id="template-code"
                        type="text"
                        value={newTemplateCode}
                        onChange={(e) => setNewTemplateCode(e.target.value)}
                        placeholder="hello_world"
                        className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                        required
                      />
                      <p className="text-xs text-gray-500">Lowercase, no spaces (e.g., greet, hello_world)</p>
                    </div>

                    <div className="space-y-2">
                      <label className="block text-sm font-medium text-gray-700" htmlFor="template-language">
                        Language <span className="text-red-500">*</span>
                      </label>
                      <select
                        id="template-language"
                        value={newTemplateLanguage}
                        onChange={(e) => setNewTemplateLanguage(e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                        required
                      >
                        <option value="ar">Arabic</option>
                        <option value="en">English</option>
                      </select>
                      <p className="text-xs text-gray-500">
                        ⚠️ يجب أن تطابق اللغة في Meta: English = en
                      </p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700" htmlFor="template-body">
                      Template Body <span className="text-red-500">*</span>
                    </label>
                    <textarea
                      id="template-body"
                      value={newTemplateBody}
                      onChange={(e) => setNewTemplateBody(e.target.value)}
                      placeholder="Hello {{first_name}}, welcome to our clinic!"
                      rows={6}
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors font-mono"
                      required
                    />
                    <p className="text-xs text-gray-500">Use {`{{variable_name}}`} for variables</p>
                  </div>

                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700" htmlFor="template-hsm">
                      HSM Template Name
                    </label>
                    <input
                      id="template-hsm"
                      type="text"
                      value={newTemplateHsmName}
                      onChange={(e) => setNewTemplateHsmName(e.target.value)}
                      placeholder="hello_world (optional - same as Template Code if empty)"
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    />
                    <p className="text-xs text-gray-500">Name of the template in Meta Business Manager (if different)</p>
                  </div>

                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-gray-700" htmlFor="template-variables">
                      Variables
                    </label>
                    <input
                      id="template-variables"
                      type="text"
                      value={newTemplateVariables}
                      onChange={(e) => setNewTemplateVariables(e.target.value)}
                      placeholder="first_name, last_name, date"
                      className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    />
                    <p className="text-xs text-gray-500">Comma-separated list of variable names (optional)</p>
                  </div>

                  <div className="flex items-center gap-3 pt-4">
                    <button
                      type="submit"
                      disabled={createMutation.isPending}
                      className="flex items-center gap-2 rounded-lg bg-blue-600 px-6 py-2.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
                    >
                      <Plus className="w-4 h-4" />
                      <span>{createMutation.isPending ? "Creating..." : "Create Template"}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowAddModal(false)}
                      className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

