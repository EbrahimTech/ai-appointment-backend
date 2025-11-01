"use client";

import { createContext, useContext, useMemo, useState } from "react";
import { NextIntlClientProvider, AbstractIntlMessages } from "next-intl";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

type SupportSession = {
  token: string;
  clinicSlug: string;
  expiresAt: string | null;
};

type SupportSessionContextValue = {
  support: SupportSession | null;
  setSupport: (session: SupportSession) => void;
  clearSupport: () => void;
};

const SupportSessionContext = createContext<SupportSessionContextValue | undefined>(undefined);

export function useSupportSession() {
  const ctx = useContext(SupportSessionContext);
  if (!ctx) {
    throw new Error("useSupportSession must be used within SupportSessionProvider");
  }
  return ctx;
}

function SupportSessionBanner() {
  const { support, clearSupport } = useSupportSession();
  const [isStopping, setIsStopping] = useState(false);

  if (!support) {
    return null;
  }

  async function stopSession() {
    try {
      setIsStopping(true);
      const response = await fetch("/api/support/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || payload?.ok === false) {
        throw new Error(payload.error || "Failed to stop support session");
      }
      clearSupport();
    } catch (error) {
      console.error(error);
    } finally {
      setIsStopping(false);
    }
  }

  return (
    <div className="flex items-center justify-between gap-4 border-b border-amber-300 bg-amber-100 px-4 py-2 text-sm text-amber-900">
      <span>
        Impersonating clinic <strong>{support.clinicSlug}</strong>. Read-only actions only (template replies allowed).
        {support.expiresAt ? ` Session expires at ${new Date(support.expiresAt).toLocaleString()}.` : ""}
      </span>
      <button
        type="button"
        onClick={stopSession}
        disabled={isStopping}
        className="rounded border border-amber-500 px-3 py-1 text-xs font-medium text-amber-900"
      >
        {isStopping ? "Stopping..." : "Stop"}
      </button>
    </div>
  );
}

type ProvidersProps = {
  locale: "en" | "ar";
  messages: AbstractIntlMessages;
  initialSupportSession: SupportSession | null;
  children: React.ReactNode;
};

export default function Providers({ locale, messages, initialSupportSession, children }: ProvidersProps) {
  const [queryClient] = useState(() => new QueryClient());
  const [support, setSupportState] = useState<SupportSession | null>(initialSupportSession);

  const contextValue = useMemo<SupportSessionContextValue>(
    () => ({
      support,
      setSupport: (session) => setSupportState(session),
      clearSupport: () => setSupportState(null),
    }),
    [support]
  );

  return (
    <NextIntlClientProvider locale={locale} messages={messages}>
      <QueryClientProvider client={queryClient}>
        <SupportSessionContext.Provider value={contextValue}>
          <SupportSessionBanner />
          {children}
        </SupportSessionContext.Provider>
      </QueryClientProvider>
    </NextIntlClientProvider>
  );
}
