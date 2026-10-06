# Mercado explanatory site and deterministic replay

Serve locally: `python3 -m http.server 8080 --directory demo/mercado` from the repository root. The page never contacts Bazaar. It reads only the synthetic results JSON. Regenerate with `python3 mercado_demo.py > /tmp/results.json`; compare with `demo/mercado/simulation-results.json`. Implementation identifiers describe the original snapshot used for that reproducible fixture.

The site and its numbers are simulations, not achieved market results. The archived source download links to the existing published demo bundle. The integrated source in this repository is the current reference. No Sites credentials or hosting configuration are included here.
