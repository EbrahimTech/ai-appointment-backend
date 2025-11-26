"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import {
  CheckCircle2,
  Circle,
  AlertCircle,
  MessageSquare,
  Calendar,
  Settings,
  Users,
  FileText,
  Clock,
  Plug,
} from "lucide-react";

type ChecklistItem = {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  status: "complete" | "pending" | "warning";
  description?: string;
};

export default function OnboardingPage() {
  const params = useParams<{ slug: string }>();
  const slug = params.slug;

  // Fetch clinic setup status
  const setupQuery = useQuery({
    queryKey: ["clinicSetup", slug],
    queryFn: async () => {
      const response = await fetch(`/api/proxy/clinic/${slug}/setup-status`);
      if (!response.ok) {
        return null;
      }
      const payload = await response.json();
      return payload.data;
    },
  });

  const setupStatus = setupQuery.data || {
    has_services: false,
    has_hours: false,
    has_whatsapp: false,
    has_google: false,
    has_users: false,
    has_templates: false,
  };

  const checklist: ChecklistItem[] = [
    {
      id: "services",
      label: "Setup Services",
      icon: Settings,
      href: `/c/${slug}/services`,
      status: setupStatus.has_services ? "complete" : "pending",
      description: "Add services your clinic offers",
    },
    {
      id: "hours",
      label: "Configure Hours",
      icon: Clock,
      href: `/c/${slug}/hours`,
      status: setupStatus.has_hours ? "complete" : "pending",
      description: "Set working hours for each service",
    },
    {
      id: "whatsapp",
      label: "Connect WhatsApp",
      icon: MessageSquare,
      href: `/c/${slug}/integrations`,
      status: setupStatus.has_whatsapp ? "complete" : "warning",
      description: "Configure WhatsApp channel for messaging",
    },
    {
      id: "google",
      label: "Connect Google Calendar",
      icon: Calendar,
      href: `/c/${slug}/integrations`,
      status: setupStatus.has_google ? "complete" : "warning",
      description: "Sync appointments with Google Calendar",
    },
    {
      id: "templates",
      label: "Review Templates",
      icon: FileText,
      href: `/c/${slug}/templates`,
      status: setupStatus.has_templates ? "complete" : "pending",
      description: "Approve WhatsApp message templates",
    },
    {
      id: "users",
      label: "Invite Team Members",
      icon: Users,
      href: `/c/${slug}/users`,
      status: setupStatus.has_users ? "complete" : "pending",
      description: "Add staff members to your clinic",
    },
  ];

  const completedCount = checklist.filter((item) => item.status === "complete").length;
  const progress = (completedCount / checklist.length) * 100;

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Setup Checklist</h1>
        <p className="text-sm text-gray-500 mt-1">Complete these steps to get your clinic ready</p>
      </div>

      {/* Progress Bar */}
      <div className="mb-8 rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700">Setup Progress</span>
          <span className="text-sm font-semibold text-gray-900">
            {completedCount} of {checklist.length} completed
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-3">
          <div
            className="bg-blue-600 h-3 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Checklist */}
      <div className="space-y-3">
        {checklist.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.id}
              href={item.href}
              className="flex items-start gap-4 rounded-lg border border-gray-200 bg-white p-5 hover:shadow-md transition-shadow"
            >
              <div className="flex-shrink-0 mt-0.5">
                {item.status === "complete" ? (
                  <CheckCircle2 className="w-6 h-6 text-green-600" />
                ) : item.status === "warning" ? (
                  <AlertCircle className="w-6 h-6 text-yellow-600" />
                ) : (
                  <Circle className="w-6 h-6 text-gray-400" />
                )}
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-3">
                  <Icon className="w-5 h-5 text-gray-500" />
                  <h3 className="text-base font-semibold text-gray-900">{item.label}</h3>
                </div>
                {item.description && (
                  <p className="text-sm text-gray-500 mt-1">{item.description}</p>
                )}
              </div>
              <div className="flex-shrink-0">
                <span className="text-sm text-blue-600 font-medium">Configure →</span>
              </div>
            </Link>
          );
        })}
      </div>

      {/* Quick Actions */}
      {completedCount === checklist.length && (
        <div className="mt-8 rounded-lg border border-green-200 bg-green-50 p-6">
          <div className="flex items-center gap-3">
            <CheckCircle2 className="w-6 h-6 text-green-600" />
            <div>
              <h3 className="text-base font-semibold text-green-900">Setup Complete!</h3>
              <p className="text-sm text-green-700 mt-1">
                Your clinic is ready. You can now start managing appointments and conversations.
              </p>
            </div>
          </div>
          <div className="mt-4 flex gap-3">
            <Link
              href={`/c/${slug}/dashboard`}
              className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 transition-colors"
            >
              Go to Dashboard
            </Link>
            <Link
              href={`/c/${slug}/conversations`}
              className="rounded-md border border-green-300 bg-white px-4 py-2 text-sm font-medium text-green-700 hover:bg-green-50 transition-colors"
            >
              View Conversations
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

