import "./globals.css";
import { ReactNode } from "react";
import { cookies } from "next/headers";
import Providers from "./providers";

const messages = {
  en: {
    login: {
      title: "Sign in",
      email: "Email",
      password: "Password",
      submit: "Login",
      hqPortal: "Enter HQ",
      selectClinic: "Select clinic",
      error: "Invalid credentials",
    },
    selectClinic: {
      title: "Choose a clinic",
      button: "Continue",
    },
  },
  ar: {
    login: {
      title: "تسجيل الدخول",
      email: "البريد الإلكتروني",
      password: "كلمة المرور",
      submit: "دخول",
      hqPortal: "الدخول إلى HQ",
      selectClinic: "اختر العيادة",
      error: "بيانات الدخول غير صحيحة",
    },
    selectClinic: {
      title: "اختر العيادة",
      button: "متابعة",
    },
  },
};

export const metadata = {
  title: "AI Appointment Portal",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  const cookieStore = cookies();
  let locale = cookieStore.get("locale")?.value ?? "en";
  if (!["en", "ar"].includes(locale)) {
    locale = "en";
  }
  const direction = locale === "ar" ? "rtl" : "ltr";
  const supportToken = cookieStore.get("supportToken")?.value;
  const supportClinic = cookieStore.get("supportClinicSlug")?.value;
  const supportExpiresAt = cookieStore.get("supportExpiresAt")?.value;
  const supportSession = supportToken && supportClinic ? { token: supportToken, clinicSlug: supportClinic, expiresAt: supportExpiresAt ?? null } : null;
  return (
    <html lang={locale} dir={direction}>
      <body>
        <Providers
          locale={locale as "en" | "ar"}
          messages={messages[locale as "en" | "ar"]}
          initialSupportSession={supportSession}
        >
          {children}
        </Providers>
      </body>
    </html>
  );
}
