"use server";

import { cookies } from "next/headers";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type RouteParams = {
  params: { path: string[] };
};

export async function GET(request: Request, context: RouteParams) {
  return forward(request, context, "GET");
}

export async function POST(request: Request, context: RouteParams) {
  return forward(request, context, "POST");
}

export async function PUT(request: Request, context: RouteParams) {
  return forward(request, context, "PUT");
}

export async function PATCH(request: Request, context: RouteParams) {
  return forward(request, context, "PATCH");
}

export async function DELETE(request: Request, context: RouteParams) {
  return forward(request, context, "DELETE");
}

async function forward(request: Request, { params }: RouteParams, method: string) {
  const segments = params.path ?? [];
  const targetPath = segments.join("/");
  const cookieStore = cookies();
  const isClinicPath = segments[0] === "clinic";
  const clinicSlug = isClinicPath ? segments[1] : null;

  const supportToken = cookieStore.get("supportToken")?.value;
  const supportClinic = cookieStore.get("supportClinicSlug")?.value;
  let authToken: string | null = null;

  if (isClinicPath && supportToken && supportClinic === clinicSlug) {
    authToken = supportToken;
  } else {
    authToken = cookieStore.get("accessToken")?.value ?? null;
  }

  if (!authToken) {
    return new Response(JSON.stringify({ ok: false, error: "UNAUTHORIZED" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const requestUrl = new URL(request.url);
  const backend = new URL(targetPath, `${BACKEND_URL.replace(/\/+$/, "")}/`);
  backend.search = requestUrl.search;

  const headers: Record<string, string> = {
    Authorization: `Bearer ${authToken}`,
  };

  const isJson = request.headers.get("content-type")?.includes("application/json");
  if (isJson) {
    headers["Content-Type"] = "application/json";
  }

  let body: BodyInit | undefined;
  if (!["GET", "HEAD"].includes(method)) {
    body = await request.text();
  }

  const response = await fetch(backend.toString(), {
    method,
    headers,
    body,
  });
  const payload = await response.text();
  return new Response(payload, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("Content-Type") ?? "application/json",
    },
  });
}
