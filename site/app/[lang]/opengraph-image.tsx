import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";
import { getDictionary, hasLocale } from "./dictionaries";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Bazaar · Team 16 · Claude Hackathon Madrid";

export default async function Image({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  const dict = getDictionary(hasLocale(lang) ? lang : "en");
  const photo = await readFile(join(process.cwd(), "assets/og-photo.jpg"), "base64");

  return new ImageResponse(
    (
      <div style={{ display: "flex", width: "100%", height: "100%", background: "#fff4df", padding: 48, gap: 44 }}>
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", flex: 1 }}>
          <div
            style={{
              display: "flex",
              alignSelf: "flex-start",
              background: "#ffc83a",
              border: "5px solid #17120e",
              borderRadius: 999,
              padding: "8px 22px",
              fontSize: 24,
              fontWeight: 700,
              color: "#17120e",
            }}
          >
            Claude Hackathon Madrid · The Bazaar
          </div>
          <div style={{ display: "flex", alignItems: "flex-start" }}>
            <div style={{ display: "flex", fontSize: 168, fontWeight: 900, letterSpacing: -8, color: "#17120e", lineHeight: 1 }}>Bazaar</div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: 96,
                height: 96,
                marginLeft: 8,
                borderRadius: 999,
                background: "#e5322d",
                border: "5px solid #17120e",
                color: "#fff4df",
                fontSize: 44,
                fontWeight: 900,
                transform: "rotate(12deg)",
              }}
            >
              16
            </div>
          </div>
          <div
            style={{
              display: "flex",
              alignSelf: "flex-start",
              background: "#2347e6",
              color: "#fff4df",
              border: "5px solid #17120e",
              borderRadius: 999,
              padding: "12px 26px",
              fontSize: 28,
              fontWeight: 800,
              boxShadow: "6px 6px 0 #17120e",
            }}
          >
            ★ {dict.hero.award}
          </div>
        </div>
        <div
          style={{
            display: "flex",
            width: 400,
            height: 534,
            border: "6px solid #17120e",
            borderRadius: 28,
            background: "white",
            padding: 12,
            boxShadow: "12px 12px 0 #17120e",
            transform: "rotate(3deg)",
          }}
        >
          {/* eslint-disable-next-line jsx-a11y/alt-text */}
          <img
            src={`data:image/jpeg;base64,${photo}`}
            width={364}
            height={498}
            style={{ objectFit: "cover", objectPosition: "48% 50%", borderRadius: 16, border: "4px solid #17120e" }}
          />
        </div>
      </div>
    ),
    size,
  );
}
