"use client";

import { useEffect, useRef, useState } from "react";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import commits from "@/data/commits.json";
import { SectionHeader } from "./section-header";

const PHASE_HOURS: [number, number][] = [
  [0, 4],
  [8, 13],
  [15, 25],
  [26, 27],
  [29, 45],
];

const PHASE_COLORS = ["bg-rojo", "bg-azul", "bg-amarillo", "bg-verde", "bg-rosa"];
const PHASE_TEXT = ["text-paper", "text-paper", "text-ink", "text-paper", "text-ink"];

const DAY_STARTS = [
  { index: 0, key: "fri" },
  { index: 5, key: "sat" },
  { index: 29, key: "sun" },
] as const;

const hours = commits.hours;
const max = Math.max(...hours.map((h) => h.human + h.auto));

function phaseOf(index: number) {
  return PHASE_HOURS.findIndex(([a, b]) => index >= a && index <= b);
}

export function Weekend({ dict }: { dict: Dictionary }) {
  const w = dict.weekend;
  const [active, setActive] = useState(0);
  const [hovered, setHovered] = useState<number | null>(null);
  const [bar, setBar] = useState<number | null>(null);
  const refs = useRef<(HTMLLIElement | null)[]>([]);
  const shown = hovered ?? active;

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActive(Number((e.target as HTMLElement).dataset.phase));
        }
      },
      { rootMargin: "-45% 0px -45% 0px" },
    );
    refs.current.forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, []);

  const dayLabel = (index: number) => {
    const day = [...DAY_STARTS].reverse().find((d) => index >= d.index)!;
    const hour = (19 + index) % 24;
    return `${w.days[day.key]} ${String(hour).padStart(2, "0")}:00`;
  };

  return (
    <section id="weekend" className="border-b-[3px] border-ink">
      <div className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
        <SectionHeader num={w.num} title={w.title} lead={w.lead} color="bg-amarillo" />

        <div className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-12">
          <div className="lg:sticky lg:top-24 lg:self-start">
            <div className="cromo p-5 sm:p-6">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="font-display text-xl font-extrabold">{w.chartTitle}</h3>
                <p className="font-mono text-[0.7rem] text-ink/60">{w.chartRange}</p>
              </div>

              <div className="relative mt-6">
                <div className="flex h-52 items-end gap-[2px] sm:h-60" role="img" aria-label={`${w.chartTitle}: ${commits.total}`}>
                  {hours.map((h, i) => {
                    const p = phaseOf(i);
                    const inPhase = p === shown;
                    return (
                      <button
                        key={h.hour}
                        type="button"
                        onMouseEnter={() => setBar(i)}
                        onMouseLeave={() => setBar(null)}
                        onFocus={() => setBar(i)}
                        onBlur={() => setBar(null)}
                        onClick={() => setBar(bar === i ? null : i)}
                        aria-label={`${dayLabel(i)}: ${h.human} ${w.byHand}, ${h.auto} ${w.automated}`}
                        className={`relative flex h-full flex-1 flex-col justify-end rounded-t-[3px] transition-opacity duration-300 ${
                          p >= 0 ? (inPhase ? "opacity-100" : "opacity-35") : "opacity-25"
                        }`}
                      >
                        <span
                          className="w-full rounded-t-[3px] bg-amarillo ring-1 ring-ink/40"
                          style={{ height: `${(h.auto / max) * 100}%` }}
                        />
                        <span className="w-full bg-ink" style={{ height: `${(h.human / max) * 100}%` }} />
                      </button>
                    );
                  })}
                </div>
                {bar !== null && (
                  <div
                    className="pointer-events-none absolute -top-3 z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-lg border-2 border-ink bg-white px-2.5 py-1.5 font-mono text-[0.7rem] shadow-hard-sm"
                    style={{ left: `${((bar + 0.5) / hours.length) * 100}%` }}
                  >
                    <strong>{dayLabel(bar)}</strong> · {hours[bar].human} {w.byHand} · {hours[bar].auto} {w.automated}
                  </div>
                )}
                <div className="mt-2 flex h-2 gap-[2px]" aria-hidden="true">
                  {hours.map((h, i) => {
                    const p = phaseOf(i);
                    return <span key={h.hour} className={`flex-1 rounded-sm ${p >= 0 ? PHASE_COLORS[p] : "bg-transparent"} ${p === shown ? "" : "opacity-30"}`} />;
                  })}
                </div>
                <div className="relative mt-2 h-4 font-mono text-[0.7rem] font-bold" aria-hidden="true">
                  {DAY_STARTS.map((d) => (
                    <span key={d.key} className="absolute border-l-2 border-ink pl-1" style={{ left: `${(d.index / hours.length) * 100}%` }}>
                      {w.days[d.key]}
                    </span>
                  ))}
                </div>
              </div>

              <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 text-sm font-semibold">
                <span className="flex items-center gap-2">
                  <span className="size-3.5 rounded-sm bg-ink" /> {w.human}
                </span>
                <span className="flex items-center gap-2">
                  <span className="size-3.5 rounded-sm bg-amarillo ring-1 ring-ink/40" /> {w.auto}
                </span>
              </div>

              <ol className="mt-6 flex flex-wrap gap-2">
                {w.phases.map((p, i) => (
                  <li key={p.title}>
                    <button
                      type="button"
                      onClick={() => refs.current[i]?.scrollIntoView({ behavior: "smooth", block: "center" })}
                      onMouseEnter={() => setHovered(i)}
                      onMouseLeave={() => setHovered(null)}
                      className={`rounded-full border-2 border-ink px-3 py-1 font-display text-xs font-bold transition ${
                        i === shown ? `${PHASE_COLORS[i]} ${PHASE_TEXT[i]} shadow-hard-sm` : "bg-white"
                      }`}
                    >
                      {i + 1}. {p.title}
                    </button>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          <ol className="relative space-y-8 before:absolute before:bottom-6 before:left-[1.4rem] before:top-6 before:w-[3px] before:bg-ink sm:before:left-[1.65rem]">
            {w.phases.map((p, i) => (
              <li
                key={p.title}
                ref={(el) => {
                  refs.current[i] = el;
                }}
                data-phase={i}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
                className="relative pl-16 sm:pl-20"
              >
                <span
                  className={`absolute left-0 top-4 grid size-12 place-items-center rounded-full border-[3px] border-ink font-display text-lg font-extrabold shadow-hard-sm transition-transform duration-300 sm:size-14 ${PHASE_COLORS[i]} ${PHASE_TEXT[i]} ${
                    i === shown ? "scale-110" : ""
                  }`}
                >
                  {i + 1}
                </span>
                <article className={`cromo p-5 transition-[translate,box-shadow] duration-300 sm:p-7 ${i === shown ? "-translate-y-1 shadow-hard-lg" : ""}`}>
                  <p className="font-mono text-xs font-bold uppercase tracking-wider text-ink/60">{p.when}</p>
                  <h3 className="mt-1 font-display text-2xl font-extrabold tracking-tight sm:text-3xl">{p.title}</h3>
                  <p className="mt-3 leading-relaxed text-ink/80">{p.summary}</p>
                  <ul className="mt-5 divide-y-2 divide-dashed divide-ink/15">
                    {p.milestones.map((m) => (
                      <li key={m.t + m.text} className="flex items-baseline gap-x-3 py-2.5">
                        <span className="w-[4.5rem] shrink-0 font-mono text-xs font-bold">{m.t}</span>
                        <span className="min-w-0 flex-1 text-[0.95rem] leading-snug">{m.text}</span>
                      </li>
                    ))}
                  </ul>
                </article>
              </li>
            ))}
          </ol>
        </div>

        <aside className="cromo mt-16 grid gap-6 bg-rojo p-6 text-paper sm:p-10 lg:grid-cols-[auto_1fr] lg:items-center lg:gap-10">
          <div className="cromo-perf border-paper/30" />
          <p className="sticker w-fit -rotate-2 bg-paper text-ink">{w.lesson.label}</p>
          <div>
            <h3 className="font-display text-3xl font-extrabold leading-tight tracking-tight text-balance sm:text-4xl">{w.lesson.title}</h3>
            <p className="mt-4 max-w-3xl text-lg leading-relaxed text-paper/90">{w.lesson.body}</p>
          </div>
        </aside>
      </div>
    </section>
  );
}
