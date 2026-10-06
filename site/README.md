# Bazaar · Team 16 landing page

Next.js 16 (App Router, Cache Components) with Tailwind CSS v4. Bilingual: `/en` and `/es`;
`/` redirects by `Accept-Language` in `proxy.ts`.

```bash
npm install
npm run dev     # http://localhost:3000
npm run build
```

- Copy lives in `app/[lang]/dictionaries/` (`en.ts` is the source type, `es.ts` must match it).
- `data/commits.json` is the hourly commit histogram; `data/mercado.json` holds the synthetic
  scenarios replayed by the cycle player, exported from `../mercado_demo.py`.
- `NEXT_PUBLIC_SITE_URL` overrides the canonical URL used in metadata and the OG image.
