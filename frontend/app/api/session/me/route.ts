"use server";

import { cookies } from "next/headers";

export async function GET() {
  const cookieStore = cookies();
  const access = cookieStore.get("accessToken");
  if (!access) {
    return new Response(JSON.stringify({ ok: false, error: "UNAUTHORIZED" }), { status: 401, headers: { "Content-Type": "application/json" } });
  }

  const response = await fetch(`${process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000"}/auth/me`, {
    headers: { Authorization: `Bearer ${access.value}` },
  });
  const payload = await response.json();
  return new Response(JSON.stringify(payload), {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
