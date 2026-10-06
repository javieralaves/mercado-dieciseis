import Link from "next/link";
import type { Dictionary, Locale } from "@/app/[lang]/dictionaries";
import { NOVA_ANNOUNCEMENT_URL, REPO_URL } from "@/lib/site";

export function Footer({ dict, lang }: { dict: Dictionary; lang: Locale }) {
  const other = lang === "en" ? "es" : "en";
  return (
    <footer className="bg-ink text-paper">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-10 sm:px-6 md:flex-row md:items-center md:justify-between lg:px-8">
        <p className="flex items-center gap-3 font-display font-bold">
          <span className="grid size-9 -rotate-6 place-items-center rounded-lg border-[3px] border-paper bg-rojo text-sm">16</span>
          {dict.footer.line}
        </p>
        <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm font-semibold text-paper/80">
          <li>
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="hover:text-amarillo">
              {dict.footer.repo}
            </a>
          </li>
          <li>
            <a href={NOVA_ANNOUNCEMENT_URL} target="_blank" rel="noreferrer" className="hover:text-amarillo">
              {dict.footer.announcement}
            </a>
          </li>
          <li>
            <Link href={`/${other}`} hrefLang={other} className="hover:text-amarillo">
              {dict.nav.switchLabel}
            </Link>
          </li>
        </ul>
      </div>
    </footer>
  );
}
