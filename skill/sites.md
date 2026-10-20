# Sites

A site is a folder served at `/<name>/` through the symlink `sites/<name>`. In it:

- `.md` renders with the shared style (server-side highlighting, copy buttons, mermaid).
- A folder's `README.md` (or `readme.md`, `index.md`) is its index page, unless the folder has
  an `index.html`; a folder with neither shows a file listing.
- `.html` and every other file is served as-is.

`$LANTERN_ROOT/sites/_example/` is a working example of each feature.

Frontmatter, all optional:

```yaml
---
title: Deploy notes        # <title>, heading and landing card; fallback: first "# heading", then file name
description: How we deploy # landing card text (README only)
style: paper               # /_shared/paper.css instead of style.css
scripts: [mermaid]         # extra vendored scripts; a ```mermaid block loads mermaid by itself
---
```

## Existing docs

**Folder.** Pick the narrowest folder holding the docs: `docs/`, `doc/`, `documentation/`,
or the folder the user named. A repo whose only doc is its root README gets two options in the
proposal: link the repo root (`--whole-repo`, with its full exposure), or a new `docs/` site
(§ Blank site) whose README covers what colleagues need.

**Audit.** Read every doc in the folder. Each finding names the file and line, the problem
and the fix you offer:

- **Escaping links**: links and images starting with `/` resolve against the lantern host, and
  `../` paths that climb above the linked folder leave the site; both 404 once served. Fix: a
  relative path inside the folder, or link the parent folder instead.
- **Broken links**: relative links and images whose target file is missing.
- **Unrendered formats**: `.rst`, `.adoc`, `.docx` and `.ipynb` download as raw files. Flag
  notebooks only; static notebook publishing is planned (lantern `TODO.md`, Phase 6).
- **Index**: no `README.md`/`index.md`/`index.html` at the top means a bare file listing.
  Offer a README with `title`, `description` and links to the main docs.
- **Landing card**: a README without `title`/`description` frontmatter; offer both.
- **Weight**: files over ~50 MB, data dumps, build output riding along.
- **Generated docs**: with `mkdocs.yml`, Docusaurus or Sphinx, the `.md` sources render but
  the site nav is lost. Linking a built HTML folder (`site/`, `_build/html/`) works too, as
  long as the user keeps it built.

Fixes are edits in the user's repo: offer them in the proposal and apply only those accepted.

**Commands.** Survey with `lantern add-site <name> <dir> --dry-run`; run the same without
`--dry-run`.

## Blank site

- In a repo: `lantern new-site <name> <repo>/docs` (or the folder the user names; it must be
  new or empty).
- With no repo: `lantern new-site <name>` creates `pages/<name>/` in the content repo.

The stub `README.md` has a `title` and H1 derived from the name, and a commented-out
`description` line. Replace that line with a one-line description (the user's, or what the site
is for), and give the title its real spelling (`ViCap`, not `Vicap`). Write more content only
when the user asked for it.

## Pages

A page goes in the site's own folder: `readlink -f $LANTERN_ROOT/sites/<name>` (another repo
or the content repo). Link each new page from the site's README.

- **Markdown** is the default: a `.md` file with frontmatter, linking siblings relatively
  (`other.md`, `img/chart.png`).
- **HTML** when the page needs layout or interactivity. Start from
  `$LANTERN_ROOT/sites/_example/showcase.html`: the shared stylesheet and the `lantern-bar`
  breadcrumb header. Add `<script defer src="/_shared/lantern.js"></script>` when the page has
  code blocks. Links stay relative; scripts and styles come from `/_shared/` (Offline rule).
