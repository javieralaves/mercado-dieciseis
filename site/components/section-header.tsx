export function SectionHeader({
  num,
  title,
  lead,
  color = "bg-amarillo",
  dark = false,
}: {
  num: string;
  title: string;
  lead?: string;
  color?: string;
  dark?: boolean;
}) {
  return (
    <header className="mb-12 max-w-3xl sm:mb-16">
      <div className="flex items-start gap-4 sm:gap-6">
        <span className={`section-num ${color} ${dark ? "border-paper shadow-[3px_3px_0_0_var(--color-paper)]" : ""}`}>
          {num}
        </span>
        <h2 className="font-display text-4xl font-extrabold leading-[0.95] tracking-tight text-balance sm:text-5xl lg:text-6xl">
          {title}
        </h2>
      </div>
      {lead && <p className={`mt-6 text-lg leading-relaxed text-pretty sm:text-xl ${dark ? "text-paper/80" : "text-ink/75"}`}>{lead}</p>}
    </header>
  );
}
