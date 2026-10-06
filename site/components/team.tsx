import type { Dictionary } from "@/app/[lang]/dictionaries";
import { MEMBERS } from "@/lib/site";
import { LinkedInIcon } from "./icons";
import { SectionHeader } from "./section-header";

const TILTS = ["-rotate-2", "rotate-1", "-rotate-1"];

export function Team({ dict }: { dict: Dictionary }) {
  const t = dict.team;
  return (
    <section id="team" className="border-b-[3px] border-ink bg-cream">
      <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
        <SectionHeader num={t.num} title={t.title} lead={t.lead} color="bg-rojo text-paper" />
        <ul className="grid gap-10 sm:grid-cols-2 lg:grid-cols-3">
          {MEMBERS.map((m, i) => {
            const info = t.members[i];
            return (
              <li key={m.id} className={`cromo overflow-hidden transition-transform duration-200 hover:rotate-0 ${TILTS[i]}`}>
                <div className={`relative grid aspect-[4/3] place-items-center border-b-[3px] border-ink ${m.color}`}>
                  <div className="halftone-light absolute inset-0" />
                  <span className="relative font-display text-8xl font-extrabold tracking-tighter text-paper [text-shadow:5px_5px_0_var(--color-ink)]">
                    {m.initials}
                  </span>
                  <span className="absolute left-3 top-3 rounded-full border-2 border-ink bg-white px-2.5 py-0.5 font-mono text-xs font-extrabold">
                    Nº {String(i + 1).padStart(2, "0")}
                  </span>
                  <span className="absolute right-3 top-3 rounded-full border-2 border-ink bg-amarillo px-2.5 py-0.5 font-mono text-xs font-extrabold">
                    T16
                  </span>
                </div>
                <div className="p-5">
                  <p className="font-display text-2xl font-extrabold leading-tight">{info.name}</p>
                  <p className="mt-1 text-ink/70">{info.role}</p>
                  <a
                    href={m.linkedin}
                    target="_blank"
                    rel="noreferrer"
                    className="btn mt-5 bg-[#0a66c2] py-2 text-sm text-white"
                    aria-label={`${info.name} · ${t.linkedin}`}
                  >
                    <LinkedInIcon className="size-4" /> {t.linkedin}
                  </a>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
