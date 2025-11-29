"use client";

import { ReactNode } from "react";
import { useParams, usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import {
  LayoutDashboard,
  MessageSquare,
  Calendar,
  FileText,
  Settings,
  Users,
  Clock,
  Plug,
  BookOpen,
  LogOut,
  Menu,
  X,
  CheckSquare,
  Briefcase,
} from "lucide-react";
import { useState } from "react";

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number;
};

export default function ClinicLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ slug: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const slug = params.slug;
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const navItems: NavItem[] = [
    { href: `/c/${slug}/dashboard`, label: "Dashboard", icon: LayoutDashboard },
    { href: `/c/${slug}/onboarding`, label: "Setup Checklist", icon: CheckSquare },
    { href: `/c/${slug}/conversations`, label: "Conversations", icon: MessageSquare },
    { href: `/c/${slug}/appointments`, label: "Appointments", icon: Calendar },
    { href: `/c/${slug}/templates`, label: "Templates", icon: FileText },
    { href: `/c/${slug}/services`, label: "Services & Hours", icon: Briefcase },
    { href: `/c/${slug}/users`, label: "Users", icon: Users },
    { href: `/c/${slug}/integrations`, label: "Integrations", icon: Plug },
    { href: `/c/${slug}/knowledge`, label: "Knowledge Base", icon: BookOpen },
    { href: `/c/${slug}/settings`, label: "Settings", icon: Settings },
  ];

  const handleLogout = async () => {
    await fetch("/api/session/logout", { method: "POST" });
    router.push("/login");
  };

  const isActive = (href: string) => {
    if (href === `/c/${slug}/dashboard`) {
      return pathname === href;
    }
    return pathname.startsWith(href);
  };

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black bg-opacity-50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-gray-200 transform transition-transform duration-300 ease-in-out
          lg:translate-x-0 lg:static lg:inset-0
          ${sidebarOpen ? "translate-x-0" : "-translate-x-full"}
        `}
      >
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between p-5 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-indigo-50">
            <div className="flex items-center gap-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-md">
                <LayoutDashboard className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-bold capitalize text-gray-900">{slug}</h2>
                <p className="text-xs text-gray-600 font-medium">Clinic Portal</p>
              </div>
            </div>
            <button
              onClick={() => setSidebarOpen(false)}
              className="lg:hidden p-2 rounded-md text-gray-500 hover:bg-gray-100 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto p-3 space-y-1">
            {navItems.map((item) => {
              const active = isActive(item.href);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setSidebarOpen(false)}
                  className={`
                    flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200
                    ${
                      active
                        ? "bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md"
                        : "text-gray-700 hover:bg-gray-50 hover:text-gray-900"
                    }
                  `}
                >
                  <Icon className={`w-5 h-5 ${active ? "text-white" : "text-gray-500"}`} />
                  <span className={active ? "font-semibold" : ""}>{item.label}</span>
                  {item.badge && item.badge > 0 && (
                    <span className="ml-auto bg-red-500 text-white text-xs font-bold px-2 py-0.5 rounded-full animate-pulse">
                      {item.badge}
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>

          {/* Footer */}
          <div className="p-4 border-t border-gray-200">
            <button
              onClick={handleLogout}
              className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-100 transition-colors"
            >
              <LogOut className="w-5 h-5 text-gray-500" />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden bg-gray-50">
        {/* Top bar */}
        <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shadow-sm">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden p-2 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors"
          >
            <Menu className="w-6 h-6" />
          </button>
          <div className="flex-1" />
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}

