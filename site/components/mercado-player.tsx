"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import data from "@/data/mercado.json";

type Scenario = (typeof data.scenarios)[number];
type Frame = Scenario["frames"][number];
type Offer = Frame["offers"][number];
type ScenarioId = keyof Dictionary["mercado"]["player"]["scenarios"];
type Status = keyof Dictionary["mercado"]["player"]["status"];

const ORDER: ScenarioId[] = ["three", "four", "partial", "value", "reject", "cash"];
const LETTERS = "ABCD";
const NODE_FILL = ["var(--color-rojo)", "var(--color-azul)", "var(--color-amarillo)", "var(--color-verde)"];
const NODE_TEXT = ["var(--color-paper)", "var(--color-paper)", "var(--color-ink)", "var(--color-paper)"];
const NODE_BG = ["bg-rojo text-paper", "bg-azul text-paper", "bg-amarillo text-ink", "bg-verde text-paper"];
const SET_COLORS: Record<string, string> = {
  LAT: "var(--color-rojo)",
  CHA: "var(--color-azul)",
  SAL: "var(--color-amarillo)",
  RET: "var(--color-verde)",
};
const SET_BG: Record<string, string> = {
  LAT: "bg-rojo text-paper",
  CHA: "bg-azul text-paper",
  SAL: "bg-amarillo text-ink",
  RET: "bg-verde text-paper",
};

const STEP_MS = 1800;
const CX = 200;
const CY = 202;
const NODE_R = 34;

const scenarios = Object.fromEntries(data.scenarios.map((s) => [s.id, s])) as Record<ScenarioId, Scenario>;

const indexOf = (team: string) => Number(team.slice(1)) - 1;
const letter = (team: string) => LETTERS[indexOf(team)] ?? team;
const setOf = (card: string) => card.split("-")[0];

function nodePositions(n: number) {
  const r = n === 3 ? 122 : 140;
  const start = n === 4 ? -135 : -90;
  return Array.from({ length: n }, (_, i) => {
    const a = (start + (i * 360) / n) * (Math.PI / 180);
    return { x: CX + r * Math.cos(a), y: CY + r * Math.sin(a) };
  });
}

function routeFor(s: Scenario): Offer[] {
  const best = s.frames.reduce((acc, f) => (f.offers.length > acc.length ? f.offers : acc), [] as Offer[]);
  if (best.length || s.frames.every((f) => f.state === "no_route")) return best;
  return scenarios.three.frames.at(-1)!.offers;
}

const REDUCED_QUERY = "(prefers-reduced-motion: reduce)";

function subscribeReducedMotion(onChange: () => void) {
  const mq = window.matchMedia(REDUCED_QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

function usePrefersReducedMotion() {
  return useSyncExternalStore(
    subscribeReducedMotion,
    () => window.matchMedia(REDUCED_QUERY).matches,
    () => false,
  );
}

export function MercadoPlayer({ dict }: { dict: Dictionary["mercado"]["player"] }) {
  const [id, setId] = useState<ScenarioId>("three");
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const reduced = usePrefersReducedMotion();
  const root = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  const scenario = scenarios[id];
  const frames = scenario.frames;
  const frame = frames[step];
  const last = frames.length - 1;
  const positions = nodePositions(scenario.count);
  const route = routeFor(scenario);

  const isPlaying = playing && step < last;

  useEffect(() => {
    if (!isPlaying) return;
    const t = setTimeout(() => setStep((s) => s + 1), STEP_MS);
    return () => clearTimeout(t);
  }, [isPlaying, step]);

  useEffect(() => {
    if (reduced || !root.current) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting && !started.current) {
          started.current = true;
          setPlaying(true);
        }
      },
      { threshold: 0.45 },
    );
    io.observe(root.current);
    return () => io.disconnect();
  }, [reduced]);

  const choose = (next: ScenarioId) => {
    setId(next);
    setStep(0);
    setPlaying(!reduced);
  };

  const toggle = () => {
    if (step >= last) {
      setStep(0);
      setPlaying(true);
    } else setPlaying(!isPlaying);
  };

  const edges: { offer: Offer; status: Status | "proposed" }[] = frame.offers.length
    ? frame.offers.map((o) => ({ offer: o, status: o.status as Status }))
    : frame.state === "offered" || (frame.state === "running" && step > 0)
      ? route.map((o) => ({ offer: o, status: "proposed" as const }))
      : [];

  const log =
    step === 0
      ? scenario.history.map(
          (h) => `${letter(h.team)} ⇄ ${h.counterparty}: ${h.offered} → ${h.wanted} · ${dict.walked}`,
        )
      : frame.notices;

  return (
    <div ref={root} id="cycle-player" className="grid gap-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:gap-10">
      <div className="cromo relative overflow-hidden bg-white p-3 sm:p-5">
        <div className="halftone pointer-events-none absolute inset-0 opacity-50" />
        <div className="relative flex items-center justify-between gap-3 px-1">
          <p className="font-mono text-xs font-bold uppercase tracking-wider text-ink/60">
            {step + 1}/{frames.length} · {dict.frames[step]}
          </p>
          <p className="font-mono text-xs font-bold text-ink/60">{data.synthetic ? `seed ${data.seed}` : ""}</p>
        </div>
        <svg viewBox="0 0 400 400" className="relative w-full" role="img" aria-label={`${dict.title}: ${dict.scenarios[id].label}, ${dict.frames[step]}`}>
          <defs>
            {(["ink", "verde", "rojo"] as const).map((c) => (
              <marker key={c} id={`arrow-${c}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                <path d="M0 0 L10 5 L0 10 z" fill={`var(--color-${c})`} />
              </marker>
            ))}
          </defs>

          {edges.map(({ offer, status }) => {
            const a = positions[indexOf(offer.seller)];
            const b = positions[indexOf(offer.buyer)];
            if (!a || !b) return null;
            const dx = b.x - a.x;
            const dy = b.y - a.y;
            const len = Math.hypot(dx, dy);
            const ux = dx / len;
            const uy = dy / len;
            const pad = NODE_R + 8;
            const x1 = a.x + ux * pad;
            const y1 = a.y + uy * pad;
            const x2 = b.x - ux * pad;
            const y2 = b.y - uy * pad;
            const mx = (a.x + b.x) / 2;
            const my = (a.y + b.y) / 2;
            const color = status === "settled" ? "verde" : status === "cancelled" ? "rojo" : "ink";
            const set = setOf(offer.card);
            return (
              <g key={`${offer.seller}-${offer.buyer}`} className="transition-opacity duration-500" opacity={status === "proposed" ? 0.45 : 1}>
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke={`var(--color-${color})`}
                  strokeWidth={status === "settled" ? 5 : status === "proposed" ? 2.5 : 3.5}
                  strokeDasharray={status === "open" || status === "cancelled" ? "8 7" : status === "proposed" ? "2 7" : undefined}
                  strokeLinecap="round"
                  markerEnd={`url(#arrow-${color})`}
                />
                {status === "settled" && !reduced && (
                  <circle r="6" fill="var(--color-amarillo)" stroke="var(--color-ink)" strokeWidth="2">
                    <animateMotion dur="1.4s" repeatCount="indefinite" path={`M${x1},${y1} L${x2},${y2}`} />
                  </circle>
                )}
                <g transform={`translate(${mx} ${my})`}>
                  <rect x="-33" y="-24" width="66" height="26" rx="6" fill={SET_COLORS[set] ?? "white"} stroke="var(--color-ink)" strokeWidth="2.5" />
                  <text y="-6.5" textAnchor="middle" className="font-mono" fontSize="12" fontWeight="800" fill={set === "SAL" ? "var(--color-ink)" : "var(--color-paper)"}>
                    {offer.card}
                  </text>
                  {status !== "proposed" && (
                    <>
                      <rect x="-30" y="4" width="60" height="20" rx="10" fill="white" stroke="var(--color-ink)" strokeWidth="2" />
                      <text y="18" textAnchor="middle" className="font-mono" fontSize="11" fontWeight="700" fill="var(--color-ink)">
                        {offer.price} P
                      </text>
                    </>
                  )}
                </g>
              </g>
            );
          })}

          {frame.teams.map((t, i) => {
            const p = positions[i];
            const gain = t.gain;
            const badgeY = p.y < CY - 40 ? -60 : 58;
            return (
              <g key={t.team} transform={`translate(${p.x} ${p.y})`}>
                <circle r={NODE_R + 4} fill="var(--color-ink)" transform="translate(4 4)" />
                <circle r={NODE_R + 4} fill={NODE_FILL[i]} stroke="var(--color-ink)" strokeWidth="3.5" />
                <text y="13" textAnchor="middle" className="font-display" fontSize="38" fontWeight="800" fill={NODE_TEXT[i]}>
                  {LETTERS[i]}
                </text>
                {step === 0 && scenario.history.some((h) => h.team === t.team) && (
                  <g transform={`translate(0 ${badgeY})`}>
                    <rect x="-40" y="-12" width="80" height="22" rx="11" fill="white" stroke="var(--color-ink)" strokeWidth="2" />
                    <text y="4" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--color-rojo)">
                      ✕ {dict.walked}
                    </text>
                  </g>
                )}
                {gain > 0 && (
                  <g transform={`translate(0 ${badgeY})`}>
                    <rect x="-34" y="-14" width="68" height="26" rx="13" fill="var(--color-verde)" stroke="var(--color-ink)" strokeWidth="2.5" />
                    <text y="5" textAnchor="middle" className="font-display" fontSize="15" fontWeight="800" fill="var(--color-paper)">
                      +{gain} P
                    </text>
                  </g>
                )}
                {t.human_required && (
                  <g transform={`translate(${NODE_R - 2} ${-NODE_R + 2})`}>
                    {!reduced && (
                      <circle r="13" fill="var(--color-rojo)" opacity="0.4">
                        <animate attributeName="r" values="13;22;13" dur="1.6s" repeatCount="indefinite" />
                        <animate attributeName="opacity" values="0.4;0;0.4" dur="1.6s" repeatCount="indefinite" />
                      </circle>
                    )}
                    <circle r="13" fill="var(--color-rojo)" stroke="var(--color-ink)" strokeWidth="2.5" />
                    <text y="6" textAnchor="middle" fontSize="17" fontWeight="900" fill="var(--color-paper)">
                      ?
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      </div>

      <div className="flex flex-col gap-5">
        <div role="tablist" aria-label={dict.title} className="flex flex-wrap gap-2">
          {ORDER.map((s) => (
            <button
              key={s}
              role="tab"
              type="button"
              aria-selected={s === id}
              onClick={() => choose(s)}
              className={`rounded-full border-[3px] border-ink px-3.5 py-1.5 font-display text-sm font-bold transition ${
                s === id ? "bg-ink text-paper shadow-[3px_3px_0_0_var(--color-amarillo)]" : "bg-white hover:bg-amarillo"
              }`}
            >
              {dict.scenarios[s].label}
            </button>
          ))}
        </div>
        <p className="min-h-[3.5rem] text-lg leading-snug">{dict.scenarios[id].desc}</p>

        <div>
          <div className="flex gap-1.5">
            {frames.map((f, i) => (
              <button
                key={i}
                type="button"
                aria-label={`${i + 1}. ${dict.frames[i]}`}
                aria-current={i === step ? "step" : undefined}
                onClick={() => {
                  setPlaying(false);
                  setStep(i);
                }}
                className={`h-3 flex-1 rounded-full border-2 border-ink transition-colors ${i <= step ? "bg-ink" : "bg-white"}`}
              />
            ))}
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button type="button" onClick={() => { setPlaying(false); setStep((s) => Math.max(0, s - 1)); }} disabled={step === 0} className="btn bg-white px-3.5 py-2 text-sm disabled:opacity-40" aria-label={dict.prev}>
              ←
            </button>
            <button type="button" onClick={toggle} className="btn min-w-32 justify-center bg-amarillo py-2 text-sm">
              {isPlaying ? dict.pause : step >= last ? dict.restart : dict.play}
            </button>
            <button type="button" onClick={() => { setPlaying(false); setStep((s) => Math.min(last, s + 1)); }} disabled={step >= last} className="btn bg-white px-3.5 py-2 text-sm disabled:opacity-40" aria-label={dict.next}>
              →
            </button>
          </div>
        </div>

        <dl className="grid grid-cols-3 gap-3">
          {[
            { k: dict.surplus, v: `${frame.gain} P`, c: frame.gain > 0 ? "bg-verde text-paper" : "bg-white" },
            { k: dict.fees, v: `${frame.fees} P`, c: "bg-white" },
            { k: dict.trades, v: String(frame.trades), c: "bg-white" },
          ].map((m) => (
            <div key={m.k} className={`rounded-xl border-[3px] border-ink p-3 shadow-hard-sm transition-colors duration-500 ${m.c}`}>
              <dt className="text-[0.7rem] font-bold uppercase leading-tight tracking-wide opacity-75">{m.k}</dt>
              <dd className="mt-1 font-display text-2xl font-extrabold sm:text-3xl">{m.v}</dd>
            </div>
          ))}
        </dl>
        <p className="-mt-2 font-mono text-xs text-ink/70">
          {dict.baseline}: <strong>{dict.baselineValue}</strong>
        </p>

        <table className="w-full overflow-hidden rounded-xl border-[3px] border-ink bg-white text-sm shadow-hard-sm">
          <thead className="bg-cream text-left font-display text-xs uppercase tracking-wide">
            <tr>
              <th className="px-3 py-2">{dict.team}</th>
              <th className="px-3 py-2">{dict.holds}</th>
              <th className="px-3 py-2 text-right">{dict.gain}</th>
            </tr>
          </thead>
          <tbody className="divide-y-2 divide-ink/10">
            {frame.teams.map((t, i) => (
              <tr key={t.team}>
                <td className="px-3 py-2">
                  <span className="flex items-center gap-2">
                    <span className={`grid size-7 place-items-center rounded-full border-2 border-ink font-display font-extrabold ${NODE_BG[i]}`}>{LETTERS[i]}</span>
                    {t.human_required && <span className="rounded-full bg-rojo px-2 py-0.5 text-[0.65rem] font-bold text-paper">{dict.asksHuman}</span>}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <span className="flex flex-wrap gap-1">
                    {t.holdings.map((c, j) => (
                      <span key={c + j} className={`rounded-md border-2 border-ink px-1.5 font-mono text-[0.7rem] font-bold ${SET_BG[setOf(c)] ?? "bg-white"}`}>
                        {c}
                      </span>
                    ))}
                  </span>
                </td>
                <td className={`px-3 py-2 text-right font-display text-lg font-extrabold ${t.gain > 0 ? "text-verde" : "text-ink/40"}`}>
                  {t.gain > 0 ? `+${t.gain}` : "0"} P
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        <div className="rounded-xl border-[3px] border-ink bg-ink p-4 font-mono text-xs leading-relaxed text-paper shadow-hard-sm" aria-live="polite">
          <p className="mb-2 font-bold uppercase tracking-wider text-amarillo">{dict.log}</p>
          {log.length ? (
            <ul className="space-y-1">
              {log.map((l, i) => (
                <li key={i} className="before:mr-2 before:text-verde before:content-['›']">
                  {l}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-paper/70">{dict.noLog}</p>
          )}
        </div>
      </div>
    </div>
  );
}
