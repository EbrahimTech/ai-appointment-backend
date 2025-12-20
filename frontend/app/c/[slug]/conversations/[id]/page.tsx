"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { ShieldAlert } from "lucide-react";

type Message = {
  id: number;
  dir: "in" | "out";
  text: string;
  ts: string;
};

type ConversationDetail = {
  id: number;
  intent: string;
  lang: string;
  fsm_state: string;
  handoff: boolean;
  patient?: {
    id: number;
    full_name: string;
    ai_enabled: boolean;
  };
  messages: Message[];
};

type TemplateItem = {
  key: string;
  lang: string;
  channel: string;
  hsm: boolean;
  variables: string[];
  enabled: boolean;
};

type DirectReplyPayload = {
  reply_mode: "direct";
  direct_message: string;
};

type TemplateReplyPayload = {
  reply_mode: "template";
  template_key: string;
  variables?: Record<string, string>;
};

const replySchema = z.object({
  template_key: z.string().min(1),
  variables: z.record(z.string()).optional(),
});

export default function ConversationDetailPage() {
  const params = useParams<{ slug: string; id: string }>();
  const slug = params.slug;
  const conversationId = params.id;

  const [replyMode, setReplyMode] = useState<"template" | "direct">("direct");
  const [lang, setLang] = useState<string>("en");
  const [templateKey, setTemplateKey] = useState<string>("");
  const [variablesJSON, setVariablesJSON] = useState<string>("{}");
  const [directMessage, setDirectMessage] = useState<string>("");
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [replyMessage, setReplyMessage] = useState<string | null>(null);
  const [patientToggleError, setPatientToggleError] = useState<string | null>(null);

  const conversationQuery = useQuery({
    queryKey: ["conversation-detail", slug, conversationId],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/conversations/${conversationId}`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load conversation");
      }
      return payload.data as ConversationDetail;
    },
    refetchInterval: (query) => {
      const data = query.state.data as ConversationDetail | undefined;
      const messages = data?.messages ?? [];
      if (!messages.length) {
        return false;
      }
      const lastTs = messages.reduce((latest, msg) => {
        const current = new Date(msg.ts).getTime();
        return current > latest ? current : latest;
      }, 0);
      const ageMs = Date.now() - lastTs;
      return ageMs <= 60_000 ? 1000 : 3000;
    },
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });

  const templatesQuery = useQuery({
    queryKey: ["templates", slug, lang],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/templates?lang=${lang}`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load templates");
      }
      return payload.data.items as TemplateItem[];
    },
    enabled: !!lang,
  });

  const orderedMessages = useMemo(() => {
    const items = [...(conversationQuery.data?.messages ?? [])];
    return items.sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime());
  }, [conversationQuery.data?.messages]);

  useEffect(() => {
    if (conversationQuery.data?.lang) {
      setLang(conversationQuery.data.lang);
    }
  }, [conversationQuery.data?.lang]);

  useEffect(() => {
    if (templatesQuery.data?.length && !templateKey) {
      setTemplateKey(templatesQuery.data[0].key);
      const placeholders = templatesQuery.data[0].variables || [];
      if (placeholders.length) {
        const defaultVars = placeholders.reduce<Record<string, string>>((acc, current) => {
          acc[current] = "";
          return acc;
        }, {});
        setVariablesJSON(JSON.stringify(defaultVars, null, 2));
      }
    }
  }, [templatesQuery.data, templateKey]);

  const previewMutation = useMutation({
    mutationFn: async (input: { template_key: string; variables?: Record<string, string> }) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/templates/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "PREVIEW_FAILED");
      }
      return payload.data as { rendered: string };
    },
    onSuccess: (data) => {
      setPreview(data.rendered);
      setError(null);
    },
    onError: (err: Error) => {
      setPreview(null);
      setError(humanizeError(err.message));
    },
  });

  const replyMutation = useMutation({
    mutationFn: async (input: {
      reply_mode: "direct" | "template";
      direct_message?: string;
      template_key?: string;
      variables?: Record<string, string>
    }) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/conversations/${conversationId}/reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "REPLY_FAILED");
      }
      return payload.data;
    },
    onSuccess: () => {
      setReplyMessage("Reply sent successfully.");
      setError(null);
      setPreview(null);
      setDirectMessage("");
      setVariablesJSON("{}");
      conversationQuery.refetch();
    },
    onError: (err: Error) => {
      setReplyMessage(null);
      setError(humanizeError(err.message));
    },
  });

  const resolveHandoff = useMutation({
    mutationFn: async () => {
      const response = await fetch(
        `/api/proxy/clinic/${slug}/conversations/${conversationId}/handoff/resolve`,
        { method: "POST" }
      );
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "RESOLVE_FAILED");
      }
      return payload.data;
    },
    onSuccess: () => {
      conversationQuery.refetch();
      templatesQuery.refetch();
    },
  });

  const patientAiToggle = useMutation({
    mutationFn: async (nextEnabled: boolean) => {
      if (!conversationQuery.data?.patient?.id) {
        throw new Error("PATIENT_NOT_FOUND");
      }
      const response = await fetch(
        `/api/proxy/clinic/${slug}/patients/${conversationQuery.data.patient.id}/ai`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ai_enabled: nextEnabled }),
        }
      );
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "AI_TOGGLE_FAILED");
      }
      return payload.data;
    },
    onSuccess: () => {
      setPatientToggleError(null);
      conversationQuery.refetch();
    },
    onError: (err: Error) => {
      setPatientToggleError(humanizeError(err.message));
    },
  });

  if (conversationQuery.isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading conversation...</p>
      </main>
    );
  }

  if (conversationQuery.isError || !conversationQuery.data) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Unable to load conversation.</p>
          <button
            type="button"
            onClick={() => conversationQuery.refetch()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  const conversation = conversationQuery.data;
  const templates = templatesQuery.data ?? [];
  const patient = conversation.patient;

  function handlePreview() {
    setReplyMessage(null);
    const parseResult = parseForm();
    if (!parseResult.success) {
      setError(parseResult.error);
      return;
    }
    if (parseResult.data.reply_mode === "direct") {
      // For direct messages, show preview directly
      setPreview(parseResult.data.direct_message);
      setError(null);
    } else {
      // For templates, use API preview
      previewMutation.mutate({
        template_key: parseResult.data.template_key,
        variables: parseResult.data.variables,
      });
    }
  }

  function handleReply() {
    const parseResult = parseForm();
    if (!parseResult.success) {
      setError(parseResult.error);
      return;
    }
    replyMutation.mutate(parseResult.data);
  }

  function parseForm():
    | { success: true; data: DirectReplyPayload | TemplateReplyPayload }
    | { success: false; error: string } {
    setError(null);

    if (replyMode === "direct") {
      if (!directMessage.trim()) {
        return { success: false, error: "Please enter a message." };
      }
      if (directMessage.length > 4096) {
        return { success: false, error: "Message is too long. Maximum 4096 characters." };
      }
      return { success: true, data: {
        reply_mode: "direct",
        direct_message: directMessage.trim()
      } };
    } else {
      const formValues = {
        reply_mode: "template" as const,
        template_key: templateKey,
      };
      const parsedTemplate = replySchema.safeParse(formValues);
      if (!parsedTemplate.success) {
        return { success: false, error: parsedTemplate.error.issues[0]?.message ?? "Invalid template key" };
      }
      let variables: Record<string, string> | undefined = undefined;
      if (variablesJSON.trim()) {
        try {
          const parsed = JSON.parse(variablesJSON);
          if (typeof parsed !== "object" || Array.isArray(parsed)) {
            return { success: false, error: "Variables JSON must be an object." };
          }
          variables = Object.fromEntries(
            Object.entries(parsed).map(([key, value]) => [key, value == null ? "" : String(value)])
          );
        } catch {
          return { success: false, error: "Variables must be valid JSON." };
        }
      }
      return { success: true, data: { ...formValues, variables } };
    }
  }

  return (
    <main className="grid gap-8 px-6 py-8 lg:grid-cols-[2fr,1fr]">
      <section className="rounded-lg border bg-white p-6 shadow-sm">
        <header className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Conversation #{conversation.id}</h1>
            <p className="text-sm text-muted-foreground">
              Intent: {conversation.intent || "—"} · FSM state: {conversation.fsm_state || "—"} · Handoff:{" "}
              {conversation.handoff ? "Yes" : "No"}
            </p>
          </div>
        </header>

        {conversation.handoff ? (
          <div className="mt-4 flex items-center justify-between rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4" />
              <div>
                <p className="font-semibold">Handoff required</p>
                <p className="text-xs">Automation paused. Please respond manually, then mark as resolved to resume.</p>
              </div>
            </div>
            <button
              onClick={() => resolveHandoff.mutate()}
              disabled={resolveHandoff.isPending}
              className="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
            >
              {resolveHandoff.isPending ? "Updating..." : "Mark resolved"}
            </button>
          </div>
        ) : null}

        {patient ? (
          <div className="mt-4 rounded-md border bg-slate-50 px-4 py-3 text-sm">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="font-semibold text-gray-900">AI for {patient.full_name}</p>
                <p className="text-xs text-gray-600">
                  Disable to route this patient directly to human support.
                </p>
              </div>
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  className="h-5 w-5 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  checked={!!patient.ai_enabled}
                  onChange={(event) => patientAiToggle.mutate(event.target.checked)}
                  disabled={patientAiToggle.isPending}
                />
                <span className="text-sm font-medium text-gray-800">
                  {patient.ai_enabled ? "Enabled" : "Disabled"}
                </span>
              </label>
            </div>
            {patientToggleError ? (
              <p className="mt-2 text-xs text-red-600">{patientToggleError}</p>
            ) : null}
          </div>
        ) : null}

        <div className="mt-6 space-y-4">
          {orderedMessages.map((message) => (
            <article
              key={message.id}
              className={`flex gap-3 rounded-lg border px-4 py-3 text-sm ${
                message.dir === "in" ? "border-emerald-200 bg-emerald-50" : "border-blue-200 bg-blue-50"
              }`}
            >
              <div className="flex-shrink-0 font-medium text-muted-foreground">
                {message.dir === "in" ? "Patient" : "Clinic"}
              </div>
              <div className="flex flex-1 flex-col gap-1">
                <p>{message.text}</p>
                <span className="text-xs text-muted-foreground">
                  {new Date(message.ts).toLocaleString()}
                </span>
              </div>
            </article>
          ))}

          {/* Quick Reply Button - Always visible */}
          {!conversation.handoff && (
            <div className="mt-6 rounded-lg border border-blue-200 bg-blue-50 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-medium text-blue-900">Quick Reply</h3>
                  <p className="text-xs text-blue-700">Send a reply to this conversation</p>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    // Scroll to reply section
                    document.querySelector('aside')?.scrollIntoView({ behavior: 'smooth' });
                  }}
                  className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 transition-colors"
                >
                  Send Reply
                </button>
              </div>
            </div>
          )}
        </div>
      </section>

      <aside className="space-y-6">
        <section className="rounded-lg border bg-white p-6 shadow-sm" id="reply-section">
          <header className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-blue-900">📤 Send Reply to Clinic</h2>
              <p className="text-sm text-muted-foreground">Choose a template and fill variables before sending.</p>
            </div>
          </header>

          <div className="mt-4 space-y-4">
            {/* Reply Mode Selection */}
            <div className="space-y-1">
              <label className="text-sm font-medium">Reply Mode</label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setReplyMode("direct");
                    setPreview(null);
                    setError(null);
                    setReplyMessage(null);
                  }}
                  className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                    replyMode === "direct"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                  }`}
                >
                  📝 Direct Message
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setReplyMode("template");
                    setPreview(null);
                    setError(null);
                    setReplyMessage(null);
                  }}
                  className={`flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                    replyMode === "template"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 text-gray-700 hover:bg-gray-200"
                  }`}
                >
                  📋 Use Template
                </button>
              </div>
            </div>

            {replyMode === "template" && (
              <div className="space-y-1">
                <label className="text-sm font-medium" htmlFor="template-lang">
                  Template language
                </label>
                <select
                  id="template-lang"
                  value={lang}
                  onChange={(event) => {
                    setLang(event.target.value);
                    setTemplateKey("");
                    setVariablesJSON("{}");
                    setPreview(null);
                    setError(null);
                    setReplyMessage(null);
                  }}
                  className="w-full rounded border px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="en">English</option>
                  <option value="ar">Arabic</option>
                </select>
              </div>
            )}

            {replyMode === "direct" ? (
              /* Direct Message Mode */
              <div className="space-y-1">
                <label className="text-sm font-medium" htmlFor="direct-message">
                  Direct Message
                </label>
                <textarea
                  id="direct-message"
                  rows={6}
                  value={directMessage}
                  onChange={(event) => setDirectMessage(event.target.value)}
                  placeholder="Type your message here..."
                  className="w-full rounded border px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
                <p className="text-xs text-muted-foreground">
                  Write your message directly. Maximum 4096 characters.
                  {directMessage.length > 0 && (
                    <span className={directMessage.length > 4096 ? "text-red-600" : "text-gray-500"}>
                      {" "}({directMessage.length}/4096)
                    </span>
                  )}
                </p>
              </div>
            ) : (
              /* Template Mode */
              <>
                <div className="space-y-1">
                  <label className="text-sm font-medium" htmlFor="template-key">
                    Template key
                  </label>
                  <select
                    id="template-key"
                    value={templateKey}
                    onChange={(event) => {
                      setTemplateKey(event.target.value);
                      const selected = templates.find((tpl) => tpl.key === event.target.value);
                      if (selected?.variables?.length) {
                        const defaults = selected.variables.reduce<Record<string, string>>((acc, current) => {
                          acc[current] = "";
                          return acc;
                        }, {});
                        setVariablesJSON(JSON.stringify(defaults, null, 2));
                      } else {
                        setVariablesJSON("{}");
                      }
                    }}
                    className="w-full rounded border px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  >
                    <option value="">
                      {templates.length === 0 ? "No templates available" : "Select template"}
                    </option>
                    {templates.map((template) => (
                      <option key={template.key} value={template.key}>
                        {template.key} {template.hsm ? "(HSM)" : ""}
                      </option>
                    ))}
                  </select>
                  {templates.length === 0 && (
                    <p className="text-xs text-amber-600 bg-amber-50 p-2 rounded">
                      ⚠️ No reply templates available. Please add templates in the Templates section first.
                    </p>
                  )}
                </div>

                <div className="space-y-1">
                  <label className="text-sm font-medium" htmlFor="variables-json">
                    Variables (JSON)
                  </label>
                  <textarea
                    id="variables-json"
                    rows={6}
                    value={variablesJSON}
                    onChange={(event) => setVariablesJSON(event.target.value)}
                    className="w-full rounded border px-3 py-2 text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                  />
                  <p className="text-xs text-muted-foreground">
                    Provide key/value pairs matching template placeholders. Leave empty objects for none.
                  </p>
                </div>
              </>
            )}

            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            {replyMessage ? <p className="text-sm text-green-600">{replyMessage}</p> : null}

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handlePreview}
                className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
                disabled={previewMutation.isPending || replyMutation.isPending}
              >
                {previewMutation.isPending ? "Previewing..." : "Preview"}
              </button>
              <button
                type="button"
                onClick={handleReply}
                className="rounded-md bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
                disabled={replyMutation.isPending || previewMutation.isPending}
              >
                {replyMutation.isPending ? "Sending..." : `📤 Send ${replyMode === "direct" ? "Message" : "Reply"}`}
              </button>
            </div>

            {preview ? (
              <div className="rounded-md border bg-slate-50 p-4 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">
                    Preview {replyMode === "direct" ? "(Direct Message)" : "(Template)"}
                  </span>
                  <button
                    type="button"
                    className="text-xs text-primary underline"
                    onClick={() => {
                      navigator.clipboard.writeText(preview);
                    }}
                  >
                    Copy
                  </button>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-slate-700">{preview}</p>
              </div>
            ) : null}
          </div>
        </section>
      </aside>
    </main>
  );
}

function humanizeError(code: string | undefined) {
  switch (code) {
    case "PATIENT_NOT_FOUND":
      return "Patient record not found for this conversation.";
    case "INVALID_TEMPLATE":
      return "Please select a valid template.";
    case "LINT_FAILED":
      return "Template variables are invalid or missing.";
    case "NO_HSM_AVAILABLE":
      return "No approved HSM is available for this template. Please choose another template.";
    case "FORBIDDEN":
      return "You do not have permission to send replies.";
    case "MESSAGE_REQUIRED":
      return "Please enter a message to send.";
    case "MESSAGE_TOO_LONG":
      return "Message is too long. Please keep it under 4096 characters.";
    case "AI_TOGGLE_FAILED":
      return "Failed to update AI setting for this patient.";
    default:
      return code || "Something went wrong. Please try again.";
  }
}
