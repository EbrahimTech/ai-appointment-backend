"use server";

import { cookies } from "next/headers";

export async function POST(request: Request) {
  const body = await request.json();
  const response = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    return new Response(JSON.stringify(payload), { status: response.status, headers: { "Content-Type": "application/json" } });
  }

  const { access, refresh, clinics, hq_role } = payload.data ?? {};
  const cookieStore = cookies();
  const accessExpires = new Date(Date.now() + 1000 * 60 * 30);
  const refreshExpires = new Date(Date.now() + 1000 * 60 * 60 * 24 * 7);

  cookieStore.set("accessToken", access, {
    httpOnly: true,
    path: "/",
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    expires: accessExpires,
  });
  cookieStore.set("refreshToken", refresh, {
    httpOnly: true,
    path: "/",
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    expires: refreshExpires,
  });
  if (hq_role) {
    cookieStore.set("hqRole", hq_role, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      expires: refreshExpires,
    });
  } else {
    cookieStore.delete("hqRole");
  }
  cookieStore.delete("supportToken");
  cookieStore.delete("supportClinicSlug");
  cookieStore.delete("supportExpiresAt");

  return new Response(JSON.stringify({ ok: true, data: { clinics, hq_role } }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
