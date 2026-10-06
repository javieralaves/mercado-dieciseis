import type { Dictionary, Locale } from "@/app/[lang]/dictionaries";
import { REPO_URL } from "@/lib/site";
import { GitHubIcon } from "./icons";

export function Nav({ dict, lang }: { dict: Dictionary; lang: Locale }) {
  const other = lang === "en" ? "es" : "en";
  const links = [
    { href: "#weekend", label: dict.nav.weekend },
    { href: "#system", label: dict.nav.system },
    { href: "#mercado", label: dict.nav.mercado },
    { href: "#team", label: dict.nav.team },
  ];
  return (
    <nav className="sticky top-0 z-50 border-b-[3px] border-ink bg-paper/90 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <a href="#top" className="flex items-center gap-2.5 font-display text-xl font-extrabold tracking-tight">
          <span className="grid size-9 -rotate-6 place-items-center rounded-lg border-[3px] border-ink bg-rojo text-sm text-paper shadow-hard-sm">
            16
          </span>
          Bazaar
        </a>
        <ul className="hidden items-center gap-1 md:flex">
          {links.map((l) => (
            <li key={l.href}>
              <a href={l.href} className="rounded-full px-3 py-1.5 font-display font-bold hover:bg-amarillo">
                {l.label}
              </a>
            </li>
          ))}
        </ul>
        <div className="flex items-center gap-2">
          <a
            href={`/${other}`}
            hrefLang={other}
            aria-label={dict.nav.switchLabel}
            className="rounded-full border-[3px] border-ink bg-white px-3 py-1 font-display text-sm font-extrabold shadow-hard-sm hover:bg-amarillo"
          >
            {dict.nav.switchTo}
          </a>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="hidden items-center gap-2 rounded-full border-[3px] border-ink bg-ink px-3 py-1 font-display text-sm font-bold text-paper shadow-hard-sm hover:bg-azul sm:inline-flex"
          >
            <GitHubIcon className="size-4" />
            {dict.nav.code}
          </a>
          <details className="group relative md:hidden">
            <summary className="list-none rounded-full border-[3px] border-ink bg-amarillo px-3 py-1 font-display text-sm font-extrabold shadow-hard-sm [&::-webkit-details-marker]:hidden">
              {dict.nav.menu}
            </summary>
            <ul className="cromo absolute right-0 mt-3 w-52 p-2">
              {links.map((l) => (
                <li key={l.href}>
                  <a href={l.href} className="block rounded-lg px-3 py-2 font-display font-bold hover:bg-amarillo">
                    {l.label}
                  </a>
                </li>
              ))}
              <li>
                <a href={REPO_URL} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-lg px-3 py-2 font-display font-bold hover:bg-amarillo">
                  <GitHubIcon className="size-4" /> {dict.nav.code}
                </a>
              </li>
            </ul>
          </details>
        </div>
      </div>
    </nav>
  );
}
