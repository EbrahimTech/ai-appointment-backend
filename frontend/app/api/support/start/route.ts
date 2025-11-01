"use server";

import { cookies } from "next/headers";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export async function POST(request: Request) {
  const body = await request.json();
  const { clinic_id, reason, clinic_slug } = body as {
    clinic_id?: number;
    reason?: string;
    clinic_slug?: string;
  };

  const cookieStore = cookies();
  const access = cookieStore.get("accessToken");
  if (!access) {
    return new Response(JSON.stringify({ ok: false, error: "UNAUTHORIZED" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const response = await fetch(`${BACKEND_URL}/hq/support/start`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${access.value}`,
    },
    body: JSON.stringify({ clinic_id, reason }),
  });
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    return new Response(JSON.stringify(payload), {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  const data = payload.data ?? {};
  const supportToken = data.support_token;
  const expiresAt = data.expires_at ?? null;
  if (supportToken && clinic_slug) {
    const secure = process.env.NODE_ENV === "production";
    const expiresDate = expiresAt ? new Date(expiresAt) : new Date(Date.now() + 15 * 60 * 1000);
    cookieStore.set("supportToken", supportToken, {
      httpOnly: true,
      sameSite: "lax",
      secure,
      path: "/",
      expires: expiresDate,
    });
    cookieStore.set("supportClinicSlug", clinic_slug, {
      httpOnly: true,
      sameSite: "lax",
      secure,
      path: "/",
      expires: expiresDate,
    });
    if (expiresAt) {
      cookieStore.set("supportExpiresAt", expiresAt, {
        httpOnly: true,
        sameSite: "lax",
        secure,
        path: "/",
        expires: expiresDate,
      });
    }
  }

  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
