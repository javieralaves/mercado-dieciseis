import type { Dictionary } from "@/app/[lang]/dictionaries";
import { SectionHeader } from "./section-header";

const LOOP_COLORS = ["bg-amarillo", "bg-rosa", "bg-azul text-paper", "bg-rojo text-paper", "bg-verde text-paper", "bg-naranja"];
const DOMAIN_STRIPES = ["bg-rojo", "bg-azul", "bg-amarillo", "bg-verde", "bg-rosa", "bg-naranja"];
const TILTS = ["-rotate-1", "rotate-1", "rotate-0", "-rotate-2", "rotate-2", "-rotate-1"];

export function System({ dict }: { dict: Dictionary }) {
  const s = dict.system;
  return (
    <section id="system" className="relative border-b-[3px] border-ink bg-cream">
      <div className="halftone pointer-events-none absolute inset-0 opacity-60" />
      <div className="relative mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
        <SectionHeader num={s.num} title={s.title} lead={s.lead} color="bg-azul text-paper" />

        <h3 className="font-display text-2xl font-extrabold">{s.loopTitle}</h3>
        <ol className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-6 lg:gap-3">
          {s.loop.map((step, i) => (
            <li key={step.k} className="relative">
              <div className={`cromo h-full p-5 ${LOOP_COLORS[i]}`}>
                <p className="font-mono text-xs font-bold opacity-70">0{i + 1}</p>
                <p className="mt-1 font-display text-2xl font-extrabold">{step.k}</p>
                <p className="mt-2 text-sm leading-snug opacity-90">{step.v}</p>
              </div>
              <span
                aria-hidden="true"
                className="absolute -right-3 top-1/2 z-10 hidden -translate-y-1/2 font-display text-2xl font-extrabold lg:block"
              >
                {i < s.loop.length - 1 ? "→" : "↺"}
              </span>
            </li>
          ))}
        </ol>

        <h3 className="mt-20 font-display text-2xl font-extrabold">{s.domainsTitle}</h3>
        <ul className="mt-8 grid grid-cols-1 gap-6 min-[480px]:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {s.domains.map((d, i) => (
            <li
              key={d.k}
              className={`cromo overflow-hidden transition-transform duration-200 hover:-translate-y-1 hover:rotate-0 ${TILTS[i % TILTS.length]}`}
            >
              <div className={`flex items-center justify-between border-b-[3px] border-ink px-4 py-2 ${DOMAIN_STRIPES[i % DOMAIN_STRIPES.length]}`}>
                <span className="font-mono text-xs font-extrabold">Nº {String(i + 1).padStart(2, "0")}</span>
                <span className="size-3 rounded-full border-2 border-ink bg-white" />
              </div>
              <div className="p-4">
                <p className="font-display text-xl font-extrabold leading-tight">{d.k}</p>
                <p className="mt-2 text-sm leading-snug text-ink/75">{d.v}</p>
              </div>
            </li>
          ))}
          <li className="cromo grid place-items-center bg-ink p-6 text-center text-paper -rotate-1">
            <p className="font-display text-6xl font-extrabold text-amarillo">1</p>
            <p className="mt-1 font-display text-lg font-bold leading-tight">{s.stateCard}</p>
          </li>
        </ul>
      </div>
    </section>
  );
}
