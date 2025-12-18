"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCircle2, Clock, AlertCircle, ArrowRight } from "lucide-react";

type NotificationItem = {
  id: number | string;
  title: string;
  body: string;
  patient_name: string;
  patient_phone: string;
  conversation_id: number | null;
  status: string;
  type: string;
  created_at: string;
};

export default function NotificationsPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;
  const queryClient = useQueryClient();

  const notificationsQuery = useQuery({
    queryKey: ["notifications", slug],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/notifications`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to load notifications");
      }
      return payload.data.items as NotificationItem[];
    },
  });

  const markReadMutation = useMutation({
    mutationFn: async (id: number | string) => {
      const response = await fetch(`/api/proxy/clinic/${slug}/notifications/${id}/read`, {
        method: "POST",
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.error || "Failed to mark as read");
      }
      return payload.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications", slug] });
    },
  });

  const items = notificationsQuery.data ?? [];

  return (
    <main className="min-h-screen bg-gray-50">
      <div className="border-b bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-6 py-6">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-100 text-indigo-700">
            <Bell className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Notifications</h1>
            <p className="text-sm text-gray-600">Handoff alerts that need human attention.</p>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-6 space-y-4">
        {notificationsQuery.isLoading ? (
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm text-sm text-slate-600">
            Loading notifications...
          </div>
        ) : notificationsQuery.isError ? (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 shadow-sm flex items-start gap-3 text-sm text-red-800">
            <AlertCircle className="h-4 w-4 mt-0.5" />
            <div>
              <p className="font-semibold">Failed to load notifications</p>
              <p className="text-xs">Please refresh and try again.</p>
            </div>
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm text-center text-sm text-slate-500">
            No notifications yet.
          </div>
        ) : (
          <ul className="space-y-3">
            {items.map((item) => (
              <li
                key={item.id}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow-md"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <Clock className="h-4 w-4" />
                    <span>{new Date(item.created_at).toLocaleString()}</span>
                    <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700 font-medium">
                      {item.type}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 font-medium ${
                        item.status === "new"
                          ? "bg-emerald-50 text-emerald-700"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {item.status === "new" ? "New" : "Read"}
                    </span>
                  </div>
                  {item.status === "new" ? (
                    <button
                      onClick={() => markReadMutation.mutate(item.id)}
                      className="flex items-center gap-1 rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50"
                      disabled={markReadMutation.isPending}
                    >
                      <CheckCircle2 className="h-4 w-4" />
                      Mark read
                    </button>
                  ) : null}
                </div>
                <div className="mt-3 space-y-1">
                  <p className="text-base font-semibold text-gray-900">{item.title}</p>
                  <p className="text-sm text-slate-700">{item.body}</p>
                  <p className="text-sm text-slate-600">
                    Patient: {item.patient_name || "Unknown"} {item.patient_phone ? `(${item.patient_phone})` : ""}
                  </p>
                </div>
                {item.conversation_id ? (
                  <div className="mt-3">
                    <Link
                      href={`/c/${slug}/conversations/${item.conversation_id}`}
                      className="inline-flex items-center gap-1 text-sm font-medium text-indigo-700 hover:text-indigo-900"
                    >
                      View conversation
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </main>
  );
}
