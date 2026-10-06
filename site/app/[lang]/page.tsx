import { notFound } from "next/navigation";
import { Footer } from "@/components/footer";
import { Hero } from "@/components/hero";
import { Mercado } from "@/components/mercado";
import { Nav } from "@/components/nav";
import { OpenSource } from "@/components/open-source";
import { Organizers } from "@/components/organizers";
import { Recognition } from "@/components/recognition";
import { Stats } from "@/components/stats";
import { System } from "@/components/system";
import { Team } from "@/components/team";
import { Weekend } from "@/components/weekend";
import { getDictionary, hasLocale } from "./dictionaries";

export default async function Page({ params }: PageProps<"/[lang]">) {
  const { lang } = await params;
  if (!hasLocale(lang)) notFound();
  const dict = getDictionary(lang);
  return (
    <>
      <Nav dict={dict} lang={lang} />
      <main>
        <Hero dict={dict} />
        <Recognition dict={dict} />
        <Stats dict={dict} />
        <Weekend dict={dict} />
        <System dict={dict} />
        <Mercado dict={dict} />
        <OpenSource dict={dict} />
        <Team dict={dict} />
        <Organizers dict={dict} />
      </main>
      <Footer dict={dict} lang={lang} />
    </>
  );
}
