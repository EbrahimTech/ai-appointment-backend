"use client";

import { useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { MessageSquare, Search, Filter, ChevronRight, RefreshCw, Calendar, Globe, Eye } from "lucide-react";

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
      <div className="flex min-h-screen items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-sm text-gray-500">Loading conversations...</p>
        </div>
      </div>
    );
  }

  if (conversationsQuery.isError || !data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 px-4 text-center">
        <div className="space-y-4">
          <div className="flex items-center justify-center w-16 h-16 rounded-full bg-red-100 mx-auto">
            <MessageSquare className="w-8 h-8 text-red-600" />
          </div>
          <div>
            <p className="text-base font-medium text-gray-900 mb-1">Unable to load conversations</p>
            <p className="text-sm text-gray-500 mb-4">Please try again</p>
          </div>
          <button
            type="button"
            onClick={() => conversationsQuery.refetch()}
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
          <div className="flex items-start justify-between">
            <div className="flex items-start gap-4">
              <div className="flex items-center justify-center w-14 h-14 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg">
                <MessageSquare className="w-7 h-7" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-gray-900 mb-2">Conversations</h1>
                <p className="text-sm text-gray-600">Manage and monitor patient conversations</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => conversationsQuery.refetch()}
              disabled={conversationsQuery.isFetching}
              className="flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors shadow-sm"
            >
              <RefreshCw className={`w-4 h-4 ${conversationsQuery.isFetching ? "animate-spin" : ""}`} />
              <span>Refresh</span>
            </button>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Filters Section */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Filter className="w-5 h-5 text-gray-500" />
            <h2 className="text-lg font-semibold text-gray-900">Filters</h2>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="status">
              Status
            </label>
            <select
              id="status"
              name="status"
              value={filters.status}
              onChange={updateFilter}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            >
              {statuses.map((option) => (
                <option key={option} value={option}>
                    {option ? option.charAt(0).toUpperCase() + option.slice(1) : "All Statuses"}
                </option>
              ))}
            </select>
          </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="intent">
              Intent
            </label>
            <input
              id="intent"
              name="intent"
              value={filters.intent}
              onChange={updateFilter}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                placeholder="e.g. booking, inquiry"
            />
          </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="lang">
                <Globe className="w-4 h-4 inline mr-1" />
              Language
            </label>
            <select
              id="lang"
              name="lang"
              value={filters.lang}
              onChange={updateFilter}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            >
                <option value="">All Languages</option>
                <option value="en">English</option>
                <option value="ar">Arabic</option>
            </select>
          </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="q">
                <Search className="w-4 h-4 inline mr-1" />
              Search
            </label>
            <input
              id="q"
              name="q"
              value={filters.q}
              onChange={updateFilter}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                placeholder="Phone number or keyword"
            />
          </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="from">
                <Calendar className="w-4 h-4 inline mr-1" />
                From Date
            </label>
            <input
              id="from"
              name="from"
              type="datetime-local"
              value={filters.from}
              onChange={updateFilter}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            />
          </div>
            <div className="space-y-2">
              <label className="block text-sm font-medium text-gray-700" htmlFor="to">
                <Calendar className="w-4 h-4 inline mr-1" />
                To Date
            </label>
            <input
              id="to"
              name="to"
              type="datetime-local"
              value={filters.to}
              onChange={updateFilter}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            />
            </div>
          </div>
        </div>

        {/* Conversations Table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gradient-to-r from-gray-50 to-gray-100">
            <tr>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Patient
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Last Message
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Intent
                  </th>
                  <th className="px-6 py-4 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                    Language
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
            {data.items.length === 0 ? (
              <tr>
                    <td colSpan={6} className="px-6 py-12 text-center">
                      <div className="flex flex-col items-center">
                        <MessageSquare className="w-12 h-12 text-gray-400 mb-3" />
                        <p className="text-sm font-medium text-gray-900 mb-1">No conversations found</p>
                        <p className="text-xs text-gray-500">Try adjusting your filters</p>
                      </div>
                </td>
              </tr>
            ) : (
              data.items.map((item) => (
                    <tr key={item.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm font-medium text-gray-900">
                    {item.patient?.phone ?? "Unknown"}
                        </div>
                  </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-600">
                    {item.last_message_at ? new Date(item.last_message_at).toLocaleString() : "—"}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="text-sm text-gray-900">{item.intent || "—"}</div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800 uppercase">
                          {item.lang || "—"}
                        </span>
                  </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                    <StatusPill status={item.status} />
                  </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <button
                      type="button"
                          className="inline-flex items-center gap-1.5 text-blue-600 hover:text-blue-800 transition-colors"
                      onClick={() => router.push(`/c/${slug}/conversations/${item.id}`)}
                    >
                          <Eye className="w-4 h-4" />
                          <span>View</span>
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
          </div>
        </div>

        {/* Pagination */}
        {data.total > (filters.size ?? 20) && (
          <div className="mt-6">
        <PaginationControls
          current={data.page}
          size={data.size}
          total={data.total}
          onChange={handlePagination}
        />
          </div>
        )}
      </div>
    </div>
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
    <div className="bg-white rounded-lg border border-gray-200 px-6 py-4 flex items-center justify-between">
      <div className="text-sm text-gray-700">
        Showing <span className="font-medium">{(current - 1) * size + 1}</span> to{" "}
        <span className="font-medium">{Math.min(current * size, total)}</span> of{" "}
        <span className="font-medium">{total}</span> conversations
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="inline-flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          onClick={() => onChange(Math.max(1, current - 1))}
          disabled={current <= 1}
        >
          Previous
        </button>
        <span className="px-4 py-2 text-sm text-gray-700">
          Page {current} of {maxPage}
        </span>
        <button
          type="button"
          className="inline-flex items-center px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          onClick={() => onChange(Math.min(maxPage, current + 1))}
          disabled={current >= maxPage}
        >
          Next
        </button>
      </div>
    </div>
  );
}
