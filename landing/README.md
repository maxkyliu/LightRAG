# SmartRAG — Landing Page

A self-contained, single-file marketing landing page. No build step, no
dependencies (fonts load from Google Fonts at runtime). Drop it on any static
host.

## Files

| File          | Purpose                                  |
|---------------|------------------------------------------|
| `index.html`  | The entire landing page (HTML + CSS + a tiny inline script). |
| `logo.svg`    | SmartRAG logo (header + footer).          |
| `favicon.png` | Browser tab icon + social/OG image.       |

## Before you publish — edit these

Open `index.html` and search for these markers:

| Marker         | What to change                                                        |
|----------------|----------------------------------------------------------------------|
| `EDIT-PRICE`   | The three placeholder prices (`$0`, `$XX/mo`, `$XXX/mo`).             |
| `EDIT-EMAIL`   | The waitlist address — set to `max.kyliu@gmail.com`. Change here if needed (header, hero, each pricing card, CTA band). |
| `EDIT-APP-URL` | (Reserved) If you later switch the CTA to "Launch the app", point it here. |
| LinkedIn       | Already set to `https://www.linkedin.com/in/ka-yan-liu-1a134b32/`.    |

The quota numbers (100 MB / 1k queries, 2 GB / 20k queries, unlimited) match the
real per-tier defaults enforced by the SmartRAG API, so they're accurate as-is.

## Preview locally

```bash
cd landing
python3 -m http.server 8137
# open http://localhost:8137
```

## Deploy to cloud (pick one)

- **Static bucket + CDN:** upload the three files to S3 / GCS / Azure Blob, front
  with CloudFront / Cloud CDN.
- **Netlify / Vercel / Cloudflare Pages:** point at this `landing/` directory.
- **GitHub Pages:** publish the `landing/` folder.
- **Nginx:** copy the files into a server root and serve statically.

## Growing into payments + accounts

When you're ready for Stripe checkout and user accounts (per your note), migrate
this single file into a Next.js app: each `<section>` here maps cleanly to a
component, the design tokens at the top of the `<style>` block become your theme,
and the `mailto:` CTAs become real signup / checkout routes. Nothing here locks
you in.
