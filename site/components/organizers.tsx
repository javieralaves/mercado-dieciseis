import type { Dictionary } from "@/app/[lang]/dictionaries";

const LOGOS = [
  { src: "/logos/claude.svg", alt: "Anthropic · Claude", width: 573, height: 125 },
  { src: "/logos/causa-prima.svg", alt: "Causa Prima", width: 795, height: 97 },
  { src: "/logos/nova.svg", alt: "Nova", width: 369, height: 112 },
];

export function Organizers({ dict }: { dict: Dictionary }) {
  const o = dict.organizers;
  return (
    <section aria-labelledby="organizers" className="border-b-[3px] border-ink bg-white">
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <h2 id="organizers" className="text-center font-display text-sm font-extrabold uppercase tracking-[0.25em] text-ink/60">
          {o.title}
        </h2>
        <ul className="mt-10 grid items-center justify-items-center gap-10 sm:grid-cols-3">
          {LOGOS.map((l) => (
            <li key={l.src} className="flex h-12 items-center sm:h-14">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={l.src} alt={l.alt} width={l.width} height={l.height} className="h-8 w-auto max-w-[200px] object-contain sm:h-10" loading="lazy" />
            </li>
          ))}
        </ul>
        <p className="mx-auto mt-10 max-w-xl text-center text-ink/70">{o.thanks}</p>
      </div>
    </section>
  );
}
