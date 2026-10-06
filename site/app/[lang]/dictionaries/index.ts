import { en } from "./en";
import { es } from "./es";

export type { Dictionary } from "./en";

const dictionaries = { en, es };

export type Locale = keyof typeof dictionaries;

export const locales = Object.keys(dictionaries) as Locale[];

export const hasLocale = (locale: string): locale is Locale => locale in dictionaries;

export const getDictionary = (locale: Locale) => dictionaries[locale];
