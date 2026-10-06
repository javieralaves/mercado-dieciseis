import type { Dictionary } from "@/app/[lang]/dictionaries";
import { MercadoPlayer } from "./mercado-player";
import { SectionHeader } from "./section-header";

const PROBLEM_STYLES = [
  "bg-rojo text-paper -rotate-2",
  "bg-azul text-paper rotate-1",
  "bg-amarillo -rotate-1",
];
const GUARANTEE_STYLES = ["bg-white", "bg-rosa", "bg-amarillo", "bg-white", "bg-cream", "bg-azul text-paper"];

export function Mercado({ dict }: { dict: Dictionary }) {
  const m = dict.mercado;
  return (
    <section id="mercado" className="border-b-[3px] border-ink">
      <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
        <SectionHeader num={m.num} title={m.title} lead={m.lead} color="bg-verde text-paper" />

        <div className="grid items-center gap-8 lg:grid-cols-[1fr_auto]">
          <div>
            <h3 className="font-display text-2xl font-extrabold">{m.problemTitle}</h3>
            <ul className="mt-6 grid gap-4 sm:grid-cols-3">
              {m.problem.map((p, i) => (
                <li key={p} className={`cromo p-5 font-display text-lg font-bold leading-snug ${PROBLEM_STYLES[i]}`}>
                  <span className="mb-3 grid size-10 place-items-center rounded-full border-[3px] border-ink bg-white font-extrabold text-ink">
                    {"ABC"[i]}
                  </span>
                  {p}
                </li>
              ))}
            </ul>
          </div>
          <p className="sticker justify-self-start rotate-2 bg-ink px-6 py-3 text-base text-paper sm:text-lg lg:max-w-xs lg:justify-self-end lg:rounded-3xl">
            {m.problemPunch}
          </p>
        </div>

        <div className="mt-20">
          <h3 className="mb-6 font-display text-3xl font-extrabold tracking-tight">{m.player.title}</h3>
          <MercadoPlayer dict={m.player} />
          <p className="mt-6 max-w-4xl font-mono text-xs leading-relaxed text-ink/65">{m.player.footnote}</p>
        </div>

        <div className="mt-20 grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <div className="cromo self-start bg-ink p-7 text-paper sm:p-9">
            <h3 className="font-display text-3xl font-extrabold leading-tight tracking-tight">{m.afterTitle}</h3>
            <p className="mt-4 text-lg leading-relaxed text-paper/85">{m.after}</p>
          </div>
          <div>
            <h3 className="font-display text-2xl font-extrabold">{m.guaranteesTitle}</h3>
            <ul className="mt-6 grid gap-5 sm:grid-cols-2">
              {m.guarantees.map((g, i) => (
                <li key={g.k} className={`cromo p-5 ${GUARANTEE_STYLES[i]}`}>
                  <p className="font-display text-lg font-extrabold leading-tight">{g.k}</p>
                  <p className="mt-2 text-sm leading-relaxed opacity-85">{g.v}</p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
