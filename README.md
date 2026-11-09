# raffaele.isti.cnr.it

Personal homepage of Raffaele Perego. Static site: plain HTML/CSS/JS, no build step,
works on any web server (ISTI server or GitHub Pages) and also opened from disk.

## Layout

```
index.html                       page content (bio, research, lab, projects, awards, contact)
assets/css/style.css             styles (light + dark)
assets/js/site.js                theme toggle, stats, publication filters
assets/js/publications-data.js   GENERATED: publication list
assets/img/profile.jpg           photo (from hpc.isti.cnr.it)
data/dblp.bib                    BibTeX export from DBLP (input)
data/venues.yml                  A/A* conferences, Q1 journals, badge names
data/topics.yml                  research topics (regex on titles)
data/overrides.yml               manual fixes: drop, retype, awards, selected
scripts/build_publications.py    dblp.bib -> publications-data.js
```

## Updating the publications

1. Open https://dblp.org/pid/p/RaffaelePerego.html, export **BibTeX**, save it as `data/dblp.bib`.
2. Run `python3 scripts/build_publications.py` (needs PyYAML: `python3 -m pip install --user pyyaml`).
   Papers from the last two years that DBLP has not indexed yet are pulled from OpenAlex
   automatically (the script lists them with `+ not yet in DBLP`); once DBLP has them, the
   DBLP version wins. Add papers known to neither under `extra:` in `data/overrides.yml`.
   Use `--offline` to skip OpenAlex.
3. Upload the folder to the server.

The script prints counts per type and per topic: check them, then fix misclassified
entries in `data/overrides.yml` or tune `data/venues.yml` / `data/topics.yml`.

## Preview locally

```
python3 -m http.server 8765
```
then open http://localhost:8765.
