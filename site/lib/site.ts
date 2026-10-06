export const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://mercado-dieciseis.vercel.app";

export const REPO_URL = "https://github.com/javieralaves/mercado-dieciseis";

export const NOVA_ANNOUNCEMENT_URL = "https://lnkd.in/p/eyRUgA_D";

export const MEMBERS = [
  { id: "alaves", initials: "JA", color: "bg-rojo", linkedin: "https://www.linkedin.com/in/javieralaves/" },
  { id: "garcia", initials: "JG", color: "bg-azul", linkedin: "https://www.linkedin.com/in/javier-garc%C3%ADa-pav%C3%B3n-99a970435/" },
  { id: "ricardo", initials: "RL", color: "bg-verde", linkedin: "https://www.linkedin.com/in/ricardol%C3%B3pezalc%C3%A1ntara/" },
] as const;
