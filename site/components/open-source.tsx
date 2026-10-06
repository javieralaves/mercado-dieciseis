import type { Dictionary } from "@/app/[lang]/dictionaries";
import { REPO_URL } from "@/lib/site";
import { ArrowIcon, GitHubIcon } from "./icons";
import { SectionHeader } from "./section-header";

const COMMANDS = [
  `git clone ${REPO_URL}.git`,
  "cd mercado-dieciseis",
  "python3 mercado_demo.py > results.json",
  "python3 -m unittest discover -s tests",
];

export function OpenSource({ dict }: { dict: Dictionary }) {
  const c = dict.code;
  return (
    <section id="code" className="relative overflow-hidden border-b-[3px] border-ink bg-azul text-paper">
      <div className="halftone-light pointer-events-none absolute inset-0" />
      <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-4 py-20 sm:px-6 lg:grid-cols-2 lg:px-8 lg:py-24">
        <div>
          <SectionHeader num={c.num} title={c.title} lead={c.lead} color="bg-amarillo text-ink" dark />
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="btn -mt-4 border-paper bg-paper text-ink shadow-[5px_5px_0_0_var(--color-ink)]"
          >
            <GitHubIcon className="size-5" /> {c.cta} <ArrowIcon className="size-5" />
          </a>
        </div>
        <div className="cromo overflow-hidden border-ink bg-ink shadow-[9px_9px_0_0_var(--color-amarillo)]">
          <div className="flex items-center gap-2 border-b-[3px] border-paper/15 px-4 py-3">
            <span className="size-3 rounded-full bg-rojo" />
            <span className="size-3 rounded-full bg-amarillo" />
            <span className="size-3 rounded-full bg-verde" />
            <span className="ml-3 font-mono text-xs text-paper/60">mercado-dieciseis</span>
          </div>
          <pre className="overflow-x-auto p-5 font-mono text-[0.8rem] leading-7 text-paper sm:text-sm">
            {COMMANDS.map((cmd) => (
              <code key={cmd} className="block">
                <span className="select-none text-amarillo">$ </span>
                {cmd}
              </code>
            ))}
            <code className="mt-3 block text-verde">Ran 102 tests · OK</code>
          </pre>
          <p className="border-t-[3px] border-paper/15 px-5 py-3 font-mono text-xs text-paper/60">{c.needs}</p>
        </div>
      </div>
    </section>
  );
}
