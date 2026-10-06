import type { Metadata, Viewport } from "next";
import { notFound } from "next/navigation";
import { Bricolage_Grotesque, DM_Sans, JetBrains_Mono } from "next/font/google";
import { getDictionary, hasLocale, locales } from "./dictionaries";
import { SITE_URL } from "@/lib/site";
import "../globals.css";

const display = Bricolage_Grotesque({ variable: "--nf-display", subsets: ["latin"], weight: ["500", "700", "800"] });
const sans = DM_Sans({ variable: "--nf-body", subsets: ["latin"] });
const mono = JetBrains_Mono({ variable: "--nf-code", subsets: ["latin"] });

export async function generateStaticParams() {
  return locales.map((lang) => ({ lang }));
}

export const viewport: Viewport = {
  themeColor: "#FFF4DF",
};

export async function generateMetadata({ params }: LayoutProps<"/[lang]">): Promise<Metadata> {
  const { lang } = await params;
  if (!hasLocale(lang)) return {};
  const dict = getDictionary(lang);
  return {
    metadataBase: new URL(SITE_URL),
    title: dict.meta.title,
    description: dict.meta.description,
    alternates: {
      canonical: `/${lang}`,
      languages: { en: "/en", es: "/es", "x-default": "/en" },
    },
    openGraph: {
      title: dict.meta.title,
      description: dict.meta.description,
      url: `/${lang}`,
      siteName: "Bazaar · Team 16",
      locale: lang === "es" ? "es_ES" : "en_US",
      type: "website",
    },
    twitter: { card: "summary_large_image", title: dict.meta.title, description: dict.meta.description },
  };
}

export default async function RootLayout({ children, params }: LayoutProps<"/[lang]">) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();
  return (
    <html lang={lang} className={`${display.variable} ${sans.variable} ${mono.variable} antialiased`}>
      <body className="min-h-full bg-paper text-ink font-sans">{children}</body>
    </html>
  );
}
