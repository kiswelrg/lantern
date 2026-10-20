# Vendored assets

Everything the pages load lives here, so lantern works on a LAN without internet.

| File | Version | Source | License |
|------|---------|--------|---------|
| `mermaid.min.js` | 11.17.2 | npm `mermaid` → `dist/mermaid.min.js` | MIT (`mermaid.LICENSE`) |

To add a script `foo` that docs can request with `scripts: [foo]`, save it as
`foo.min.js` here; if it needs initialising, add that to `_shared/lantern.js`.

Code highlighting needs nothing here: Caddy's `markdown` highlights code blocks on the
server (Chroma) and `style.css` colours the token classes.
