import type { Dictionary } from "@/app/[lang]/dictionaries";

const STYLES = [
  "bg-amarillo -rotate-2",
  "bg-white rotate-1",
  "bg-rosa -rotate-1",
  "bg-azul text-paper rotate-2",
  "bg-verde text-paper -rotate-2",
  "bg-naranja rotate-1",
];

export function Stats({ dict }: { dict: Dictionary }) {
  return (
    <section aria-label="Numbers" className="border-b-[3px] border-ink bg-cream">
      <ul className="mx-auto grid max-w-7xl grid-cols-2 gap-5 px-4 py-14 sm:grid-cols-3 sm:gap-6 sm:px-6 lg:px-8 xl:grid-cols-6">
        {dict.stats.map((s, i) => (
          <li key={s.label} className={`cromo p-5 transition-transform duration-200 hover:rotate-0 ${STYLES[i % STYLES.length]}`}>
            <p className="font-display text-4xl font-extrabold leading-none tracking-tight sm:text-5xl">{s.value}</p>
            <p className="mt-2 font-display text-base font-bold leading-tight">{s.label}</p>
            <p className="mt-2 text-xs font-medium leading-snug opacity-75">{s.note}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
