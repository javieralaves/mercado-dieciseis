import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest) {
  const accept = request.headers.get("accept-language") ?? "";
  const preferred = accept.split(",")[0]?.trim().toLowerCase() ?? "";
  const lang = preferred.startsWith("es") ? "es" : "en";
  return NextResponse.redirect(new URL(`/${lang}`, request.url));
}

export const config = {
  matcher: "/",
};
