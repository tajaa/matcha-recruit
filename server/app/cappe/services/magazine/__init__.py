"""Photo-journalism magazines (`cappemag01`→). Stories are `cappe_posts` laid
out as blocks; each site has at most one magazine (`cappe_magazines`).

  * `topics` — the topic vocabulary;
  * `story_schema` — the story blocks, the five layouts, `normalize_story`;
  * `richtext` — constrained Markdown → safe HTML;
  * `stories` — saving a story (derived body, reading time, used pictures);
  * `figures` / `story_render` / `pages` — the server-rendered pages;
  * `magazines` — a site's magazine settings and whether it is live.

Spec: `server/app/cappe/CLAUDE.md` §Magazines.
"""
