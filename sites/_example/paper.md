---
title: Paper style
style: paper
---
This page sets `style: paper` in its frontmatter, so it loads `/_shared/paper.css`
instead of the default stylesheet. Variants `@import` the default and only override
what differs, so they stay small.

There's no `# heading` in this file, so the `title` from the frontmatter is used as the
page heading.

> Adding a variant: drop `_shared/<name>.css` next to `style.css` and set `style: <name>`.
