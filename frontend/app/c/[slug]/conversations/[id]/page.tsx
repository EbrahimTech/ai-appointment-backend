"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { z } from "zod";

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

const replySchema = z.object({
  template_key: z.string().min(1),
  variables: z.record(z.string()).optional(),
});

export default function ConversationDetailPage() {
  const params = useParams<{ slug: string; id: string }>();
  const slug = params.slug;
  const conversationId = params.id;

  const [lang, setLang] = useState<string>("en");
  const [templateKey, setTemplateKey] = useState<string>("");
  const [variablesJSON, setVariablesJSON] = useState<string>("{}");
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [replyMessage, setReplyMessage] = useState<string | null>(null);

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
    mutationFn: async (input: { template_key: string; variables?: Record<string, string> }) => {
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
      conversationQuery.refetch();
    },
    onError: (err: Error) => {
      setReplyMessage(null);
      setError(humanizeError(err.message));
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

  function handlePreview() {
    setReplyMessage(null);
    const parseResult = parseForm();
    if (!parseResult.success) {
      setError(parseResult.error);
      return;
    }
    previewMutation.mutate(parseResult.data);
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
    | { success: true; data: { template_key: string; variables?: Record<string, string> } }
    | { success: false; error: string } {
    setError(null);
    const formValues = {
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
    return { success: true, data: { template_key: templateKey, variables } };
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

        <div className="mt-6 space-y-4">
          {conversation.messages.map((message) => (
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
        </div>
      </section>

      <aside className="space-y-6">
        <section className="rounded-lg border bg-white p-6 shadow-sm">
          <header className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Reply with template</h2>
              <p className="text-sm text-muted-foreground">Preview before sending to ensure variables are correct.</p>
            </div>
          </header>

          <div className="mt-4 space-y-4">
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
                className="w-full rounded border px-3 py-2 text-sm"
              >
                <option value="en">English</option>
                <option value="ar">Arabic</option>
              </select>
            </div>

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
                className="w-full rounded border px-3 py-2 text-sm"
              >
                <option value="">Select template</option>
                {templates.map((template) => (
                  <option key={template.key} value={template.key}>
                    {template.key} {template.hsm ? "(HSM)" : ""}
                  </option>
                ))}
              </select>
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
                className="w-full rounded border px-3 py-2 text-sm font-mono"
              />
              <p className="text-xs text-muted-foreground">
                Provide key/value pairs matching template placeholders. Leave empty objects for none.
              </p>
            </div>

            {error ? <p className="text-sm text-red-600">{error}</p> : null}
            {replyMessage ? <p className="text-sm text-green-600">{replyMessage}</p> : null}

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handlePreview}
                className="rounded-md border px-4 py-2 text-sm"
                disabled={previewMutation.isPending}
              >
                {previewMutation.isPending ? "Previewing..." : "Preview"}
              </button>
              <button
                type="button"
                onClick={handleReply}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
                disabled={replyMutation.isPending}
              >
                {replyMutation.isPending ? "Sending..." : "Send reply"}
              </button>
            </div>

            {preview ? (
              <div className="rounded-md border bg-slate-50 p-4 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">Preview</span>
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
    case "INVALID_TEMPLATE":
      return "Please select a valid template.";
    case "LINT_FAILED":
      return "Template variables are invalid or missing.";
    case "NO_HSM_AVAILABLE":
      return "No approved HSM is available for this template. Please choose another template.";
    case "FORBIDDEN":
      return "You do not have permission to send replies.";
    default:
      return code || "Something went wrong. Please try again.";
  }
}
