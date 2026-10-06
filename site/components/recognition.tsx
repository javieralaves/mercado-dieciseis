import Image from "next/image";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import teamOrganizers from "@/assets/team-organizers.jpg";
import room from "@/assets/room.jpg";
import { NOVA_ANNOUNCEMENT_URL } from "@/lib/site";
import { ArrowIcon, StarIcon } from "./icons";

export function Recognition({ dict }: { dict: Dictionary }) {
  const r = dict.recognition;
  return (
    <section className="relative overflow-hidden border-b-[3px] border-ink bg-ink text-paper">
      <div className="halftone-light pointer-events-none absolute inset-0" />
      <div className="relative mx-auto grid max-w-7xl items-center gap-16 px-4 py-20 sm:px-6 lg:grid-cols-2 lg:px-8 lg:py-28">
        <div>
          <p className="sticker -rotate-2 border-paper bg-amarillo text-ink shadow-[3px_3px_0_0_var(--color-paper)]">
            <StarIcon className="size-4" /> {r.label}
          </p>
          <h2 className="mt-8 font-display text-[2.6rem] font-extrabold leading-[0.92] tracking-tight text-balance break-words sm:text-6xl lg:text-7xl">
            {r.title}
          </h2>
          <p className="mt-8 max-w-xl text-lg leading-relaxed text-paper/80 sm:text-xl">{r.body}</p>
          <div className="mt-10 flex flex-wrap items-center gap-5">
            <a
              href={NOVA_ANNOUNCEMENT_URL}
              target="_blank"
              rel="noreferrer"
              className="btn border-paper bg-amarillo text-ink shadow-[5px_5px_0_0_var(--color-paper)] hover:shadow-[9px_9px_0_0_var(--color-paper)]"
            >
              {r.link} <ArrowIcon className="size-5" />
            </a>
            <span className="rounded-xl border-[3px] border-paper bg-white px-3 py-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logos/nova.svg" alt="Nova" className="h-7 w-auto" width={92} height={28} />
            </span>
          </div>
        </div>

        <div className="relative pt-14 sm:pt-16">
          <figure className="cromo -rotate-2 border-paper p-3 shadow-[9px_9px_0_0_var(--color-rojo)]">
            <div className="relative aspect-[3/2] overflow-hidden rounded-lg border-[3px] border-ink">
              <Image src={teamOrganizers} alt={r.photoAlt} fill placeholder="blur" sizes="(min-width: 1024px) 45vw, 92vw" className="object-cover" />
            </div>
            <figcaption className="px-1 pt-3 text-sm font-bold text-ink">{r.caption}</figcaption>
          </figure>
          <figure className="cromo absolute -top-2 right-2 w-2/5 rotate-6 border-paper p-2 shadow-[6px_6px_0_0_var(--color-azul)] sm:right-6">
            <div className="relative aspect-[3/2] overflow-hidden rounded-md border-2 border-ink">
              <Image src={room} alt={r.roomAlt} fill placeholder="blur" sizes="(min-width: 1024px) 20vw, 40vw" className="object-cover" />
            </div>
          </figure>
        </div>
      </div>
    </section>
  );
}
