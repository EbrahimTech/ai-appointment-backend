"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

type ConversationItem = {
  id: number;
  started_at?: string;
  last_message_at: string | null;
  intent: string;
  lang: string;
  status: string;
  patient?: {
    id: number;
    phone: string;
  };
};

type QueryFilters = {
  status?: string;
  intent?: string;
  lang?: string;
  q?: string;
  from?: string;
  to?: string;
  page?: number;
  size?: number;
};

const statuses = ["", "open", "handoff", "resolved"];

export default function ClinicConversationsPage() {
  const params = useParams<{ slug: string }>();
  const router = useRouter();
  const slug = params.slug;

  const [filters, setFilters] = useState<QueryFilters>({
    status: "",
    intent: "",
    lang: "",
    q: "",
    from: "",
    to: "",
    page: 1,
    size: 20,
  });

  const conversationsQuery = useQuery({
    queryKey: ["conversations", slug, filters],
    queryFn: async () => {
      const search = new URLSearchParams();
      Object.entries(filters).forEach(([key, value]) => {
        if (value) {
          search.set(key, String(value));
        }
      });
      const response = await fetch(`/api/proxy/clinic/${slug}/conversations?${search.toString()}`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load conversations");
      }
      return payload.data as { items: ConversationItem[]; page: number; size: number; total: number };
    },
  });

  const data = useMemo(() => conversationsQuery.data, [conversationsQuery.data]);

  function updateFilter(event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) {
    const { name, value } = event.target;
    setFilters((prev) => ({
      ...prev,
      [name]: value,
      page: 1,
    }));
  }

  function handlePagination(nextPage: number) {
    setFilters((prev) => ({
      ...prev,
      page: nextPage,
    }));
  }

  if (conversationsQuery.isPending) {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading conversations...</p>
      </main>
    );
  }

  if (conversationsQuery.isError || !data) {
    return (
      <main className="flex min-h-screen items-center justify-center px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-red-600">Unable to load conversations.</p>
          <button
            type="button"
            onClick={() => conversationsQuery.refetch()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="px-6 py-8">
      <h1 className="text-2xl font-semibold">Conversations</h1>
      <section className="mt-6 rounded-lg border bg-white p-4 shadow-sm">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="status">
              Status
            </label>
            <select
              id="status"
              name="status"
              value={filters.status}
              onChange={updateFilter}
              className="w-full rounded border px-3 py-2 text-sm"
            >
              {statuses.map((option) => (
                <option key={option} value={option}>
                  {option ? option.toUpperCase() : "Any"}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="intent">
              Intent
            </label>
            <input
              id="intent"
              name="intent"
              value={filters.intent}
              onChange={updateFilter}
              className="w-full rounded border px-3 py-2 text-sm"
              placeholder="e.g. booking"
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="lang">
              Language
            </label>
            <select
              id="lang"
              name="lang"
              value={filters.lang}
              onChange={updateFilter}
              className="w-full rounded border px-3 py-2 text-sm"
            >
              <option value="">Any</option>
              <option value="en">en</option>
              <option value="ar">ar</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="q">
              Search
            </label>
            <input
              id="q"
              name="q"
              value={filters.q}
              onChange={updateFilter}
              className="w-full rounded border px-3 py-2 text-sm"
              placeholder="Phone or keyword"
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="from">
              From
            </label>
            <input
              id="from"
              name="from"
              type="datetime-local"
              value={filters.from}
              onChange={updateFilter}
              className="w-full rounded border px-3 py-2 text-sm"
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="to">
              To
            </label>
            <input
              id="to"
              name="to"
              type="datetime-local"
              value={filters.to}
              onChange={updateFilter}
              className="w-full rounded border px-3 py-2 text-sm"
            />
          </div>
        </div>
      </section>

      <section className="mt-6 overflow-hidden rounded-lg border">
        <table className="min-w-full divide-y divide-border bg-white">
          <thead className="bg-secondary/40">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Patient</th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Last message</th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Intent</th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Language</th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase text-muted-foreground">Status</th>
              <th className="px-4 py-3 text-right text-xs font-semibold uppercase text-muted-foreground">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.items.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-sm text-muted-foreground">
                  No conversations match the filters.
                </td>
              </tr>
            ) : (
              data.items.map((item) => (
                <tr key={item.id} className="hover:bg-secondary/30">
                  <td className="whitespace-nowrap px-4 py-3 text-sm">
                    {item.patient?.phone ?? "Unknown"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-sm text-muted-foreground">
                    {item.last_message_at ? new Date(item.last_message_at).toLocaleString() : "—"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-sm">{item.intent || "—"}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-sm uppercase">{item.lang || "—"}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-sm">
                    <StatusPill status={item.status} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right text-sm">
                    <button
                      type="button"
                      className="rounded-md border px-3 py-1 text-sm"
                      onClick={() => router.push(`/c/${slug}/conversations/${item.id}`)}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </section>

      {data.total > (filters.size ?? 20) ? (
        <PaginationControls
          current={data.page}
          size={data.size}
          total={data.total}
          onChange={handlePagination}
        />
      ) : null}
    </main>
  );
}

function StatusPill({ status }: { status: string }) {
  const normalized = status?.toLowerCase() ?? "";
  const colors: Record<string, string> = {
    open: "bg-emerald-100 text-emerald-700",
    handoff: "bg-amber-100 text-amber-700",
    resolved: "bg-blue-100 text-blue-700",
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${colors[normalized] ?? "bg-slate-100 text-slate-600"}`}>
      {status || "unknown"}
    </span>
  );
}

function PaginationControls({
  current,
  size,
  total,
  onChange,
}: {
  current: number;
  size: number;
  total: number;
  onChange: (page: number) => void;
}) {
  const maxPage = Math.ceil(total / size);
  return (
    <div className="mt-6 flex items-center justify-between text-sm">
      <span className="text-muted-foreground">
        Page {current} of {maxPage}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="rounded border px-3 py-1 disabled:opacity-50"
          onClick={() => onChange(Math.max(1, current - 1))}
          disabled={current <= 1}
        >
          Previous
        </button>
        <button
          type="button"
          className="rounded border px-3 py-1 disabled:opacity-50"
          onClick={() => onChange(Math.min(maxPage, current + 1))}
          disabled={current >= maxPage}
        >
          Next
        </button>
      </div>
    </div>
  );
}
