import Image from "next/image";
import type { Dictionary } from "@/app/[lang]/dictionaries";
import teamPresenting from "@/assets/team-presenting.jpg";
import { REPO_URL } from "@/lib/site";
import { ArrowIcon, DownIcon, StarIcon } from "./icons";

const MARQUEE = [
  "Abuela",
  "El Chato",
  "Doña Pilar",
  "Los Pícaros",
  "Salamanca",
  "La Latina",
  "Malasaña",
  "Lavapiés",
  "Chamberí",
  "Retiro",
  "Duels",
  "Market Test",
  "Mercado Dieciséis",
];

export function Hero({ dict }: { dict: Dictionary }) {
  const h = dict.hero;
  return (
    <section id="top" className="relative overflow-hidden border-b-[3px] border-ink">
      <div className="halftone pointer-events-none absolute inset-0 [mask-image:linear-gradient(to_bottom,black,transparent_85%)]" />
      <div className="relative mx-auto grid max-w-7xl gap-14 px-4 pb-20 pt-12 sm:px-6 sm:pt-16 lg:grid-cols-12 lg:gap-8 lg:px-8 lg:pb-28 lg:pt-20">
        <div className="lg:col-span-7">
          <p className="sticker -rotate-1 bg-amarillo text-xs sm:text-sm">{h.kicker}</p>
          <h1 className="mt-8">
            <span className="relative inline-block font-display text-[clamp(4.5rem,17vw,11.5rem)] font-extrabold leading-[0.82] tracking-[-0.04em]">
              Bazaar
              <span className="absolute -right-16 top-0 grid size-14 rotate-12 place-items-center rounded-full border-[3px] border-ink bg-rojo font-display text-2xl tracking-normal text-paper shadow-hard-sm sm:-right-24 sm:size-20 sm:text-4xl">
                16
              </span>
            </span>
            <span className="mt-8 block max-w-2xl font-display text-2xl font-bold leading-tight tracking-tight text-balance sm:text-3xl lg:text-[2.1rem]">
              {h.title}
            </span>
          </h1>
          <p className="sticker mt-8 rotate-1 bg-azul text-paper">
            <StarIcon className="size-5 text-amarillo" />
            {h.award}
          </p>
          <div className="mt-10 flex flex-wrap gap-4">
            <a href="#weekend" className="btn bg-rojo text-paper">
              {h.primary} <DownIcon className="size-5" />
            </a>
            <a href={REPO_URL} target="_blank" rel="noreferrer" className="btn bg-white">
              {h.secondary} <ArrowIcon className="size-5" />
            </a>
          </div>
        </div>

        <div className="relative mx-auto mt-8 mb-16 w-full max-w-md sm:mb-0 lg:col-span-5 lg:mt-6 lg:max-w-none">
          <figure className="cromo rotate-2 overflow-hidden p-3 pb-0 transition-transform duration-300 hover:rotate-0">
            <div className="relative aspect-[4/3] overflow-hidden rounded-lg border-[3px] border-ink">
              <Image
                src={teamPresenting}
                alt={h.photoAlt}
                fill
                priority
                placeholder="blur"
                sizes="(min-width: 1024px) 40vw, 90vw"
                className="object-cover object-[62%_center]"
              />
            </div>
            <figcaption className="flex items-center justify-between gap-3 px-1 py-3">
              <span className="font-display text-lg font-extrabold">Nº 16 · {h.team}</span>
              <span className="text-sm font-semibold text-ink/70">{h.cardTeam}</span>
            </figcaption>
          </figure>

          <div className="cromo absolute -bottom-[5.5rem] -left-2 w-32 -rotate-6 bg-amarillo p-3 sm:-bottom-10 sm:-left-10 sm:w-52 sm:p-4 lg:animate-float">
            <p className="font-display text-4xl font-extrabold leading-none sm:text-5xl">319</p>
            <p className="mt-1 text-xs font-bold leading-snug sm:text-sm">{h.cardCommits}</p>
          </div>

          <div className="cromo absolute -right-2 -top-14 w-36 rotate-6 bg-verde p-3 text-paper sm:-right-8 sm:-top-8 sm:w-52 sm:p-4 lg:animate-float lg:[animation-delay:-3s]">
            <p className="whitespace-nowrap font-display text-3xl font-extrabold leading-none sm:text-5xl">+134 P</p>
            <p className="mt-1 text-xs font-bold leading-snug sm:text-sm">{h.cardMercado}</p>
            <p className="mt-2 inline-block rounded-full bg-ink/25 px-2 py-0.5 font-mono text-[0.65rem] uppercase tracking-wider">
              {h.cardMercadoNote}
            </p>
          </div>
        </div>
      </div>

      <div className="relative overflow-hidden border-t-[3px] border-ink bg-rojo py-3 text-paper" aria-hidden="true">
        <div className="flex w-max animate-marquee gap-8 whitespace-nowrap font-display text-xl font-extrabold uppercase tracking-wide">
          {[...MARQUEE, ...MARQUEE].map((w, i) => (
            <span key={i} className="flex items-center gap-8">
              {w}
              <StarIcon className="size-4 text-amarillo" />
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
