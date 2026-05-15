# Plan: Blog Creator Feature — 5th project_type on mw_projects

## Context

Freelancers, consultants, and subject-matter experts use blogs as their primary top-of-funnel — thought leadership, case studies, SEO content. The existing Matcha Work project surface is 90% of what they need (sections, chat, file uploads, export), but lacks blog-specific affordances: cover image, SEO metadata, publish state, slug, reading time, tone/SEO AI helpers, and a write+preview layout.

**Primary user** (same persona as consultations): the solo knowledge worker shipping 1–4 posts/month to Substack / Medium / Ghost / personal blog. They want: AI-assisted outline → draft → revise → publish flow, with all their past posts browsable and AI that remembers their voice.

**Secondary synergy**: a consultation can seed a blog ("write a case study from this engagement"). Surface a "New blog from consultation" action once both types ship.

**Key design decision**: blog = 5th `project_type` on `mw_projects`, sibling to `general | presentation | recruiting | consultation`. Reuses `mw_projects.sections` as the post body chunks, `mw_threads.project_id` for AI chats, `project_files` for inline images + cover, existing `/export/{fmt}` (markdown/PDF/DOCX) as the output path. All blog-specific state lives in `project_data` JSONB.

**NOT the same as `core/routes/blog.py`**: that route is the admin-managed marketing-site blog backed by a separate `blog_posts` table with public listing, comments, likes. Don't conflate. Later phase can add a "publish to marketing blog" action that copies a finished project post into that table — but MVP stays in project land. Keep the two namespaces distinct: marketing blog = public CMS; project blog = authoring workspace.

---

## Data Model

No new tables. All blog shape lives in `mw_projects.project_data` JSONB:

```json
{
  "slug": "the-jurisdictional-maze",             // auto-derived from title, editable
  "excerpt": "HR leaders face...",                // 1–2 sentence TL;DR, also used as og_description fallback
  "cover_image_url": "https://cdn/.../abc.jpg",
  "cover_image_prompt": "professional consultant ...",
  "author": {
    "name": "Finch",
    "avatar_url": "https://cdn/.../me.png",
    "byline": "Freelance HR consultant"
  },
  "audience": "HR leaders at 50–500 employee companies",  // seeds AI tone/depth
  "tone": "expert-casual",                                 // expert-casual | technical | exec-brief | conversational | academic
  "tags": ["employee relations", "multi-state"],
  "seo": {
    "meta_title": "...",                                   // falls back to project.title when empty
    "meta_description": "...",                             // 150–160 char target
    "canonical_url": null,
    "og_title": null,
    "og_description": null,
    "og_image_url": null                                   // falls back to cover_image_url
  },
  "status": "draft",                                       // draft | scheduled | published
  "scheduled_at": null,                                    // ISO8601, optional
  "published_at": null,
  "distribution": {
    "copy_link_primary": "markdown",                       // markdown | html — remembered preference
    "last_published_platform": null                        // "substack" | "medium" | "ghost" | "manual" | null
  },
  "sources": [                                             // AI-referenced URLs the user can verify before publishing
    {"id": "src_1", "url": "...", "title": "...", "added_at": "..."}
  ],
  "stats": {                                               // computed + stored; refreshed on section change
    "word_count": 1240,
    "read_minutes": 6
  },
  "from_consultation_id": null                             // lineage when spawned from a consultation (Phase 3)
}
```

Post body lives in `mw_projects.sections` (already existing JSONB array of `{id, title, content}`). Sections render as h2 headings + markdown content, concatenated at export.

Project title = post title. Renaming the project renames the post. Slug auto-derives on title change (unless user manually edited slug).

---

## Backend Changes

### 1. `server/app/matcha/services/project_service.py`
Extend `_ALLOWED_PROJECT_TYPES` to include `"blog"`. Add `_seed_blog_data(extra_data)` mirroring the consultation seed:

```python
_ALLOWED_TONES = {"expert-casual", "technical", "exec-brief", "conversational", "academic"}
_ALLOWED_BLOG_STATUSES = {"draft", "scheduled", "published"}

def _seed_blog_data(extra_data):
    e = extra_data or {}
    return {
        "slug": _slugify(e.get("title") or ""),
        "excerpt": None,
        "cover_image_url": None,
        "cover_image_prompt": None,
        "author": e.get("author") or {},
        "audience": e.get("audience"),
        "tone": e.get("tone") if e.get("tone") in _ALLOWED_TONES else "expert-casual",
        "tags": list(e.get("tags") or []),
        "seo": {"meta_title": None, "meta_description": None, "canonical_url": None,
                "og_title": None, "og_description": None, "og_image_url": None},
        "status": "draft",
        "scheduled_at": None,
        "published_at": None,
        "distribution": {"copy_link_primary": "markdown", "last_published_platform": None},
        "sources": [],
        "stats": {"word_count": 0, "read_minutes": 0},
        "from_consultation_id": e.get("from_consultation_id"),
    }
```

Add helpers mirroring consultation's (all row-locked, `UPDATE ... RETURNING *`):

- `patch_blog(project_id, patch)` — deep-merges `seo`, `author`, `distribution`, `stats`; replaces `status`/`tone`/`tags`; validates enums; re-slugifies if title changed
- `add_blog_source(project_id, url, title)` / `delete_blog_source(project_id, source_id)`
- `set_blog_cover(project_id, url, prompt)` — writes `cover_image_url` + `cover_image_prompt`; optionally falls back into `seo.og_image_url` when og_image is empty
- `recompute_blog_stats(project_id)` — runs on any section mutation: word count = `sum(split(content))`, read_minutes = `max(1, round(wc / 225))`. Bind this into existing `_update_sections`, `add_section`, `update_section`, `delete_section` so stats stay fresh without client round-trips
- `transition_blog_status(project_id, to, scheduled_at=None)` — enforces legal transitions (draft→scheduled, scheduled→draft, draft/scheduled→published, any→draft); stamps `published_at=NOW()` on publish

### 2. `server/app/matcha/routes/matcha_work.py`

**Create endpoint** — extend existing `POST /projects` to accept `project_type="blog"` plus `blog: {audience, tone, tags, author, from_consultation_id}` in the body. If creating from a consultation, pre-populate `author` from the current user's profile and stash `from_consultation_id` for the lineage badge.

**New endpoints**:
- `PATCH /projects/{id}/blog` — partial update of title/slug/excerpt/cover/author/audience/tone/tags/seo/distribution
- `POST /projects/{id}/blog/sources` — append a source ref
- `DELETE /projects/{id}/blog/sources/{source_id}`
- `POST /projects/{id}/blog/status` — transition (body: `{to: "scheduled" | "published" | "draft", scheduled_at?}`)
- `POST /projects/{id}/blog/cover` — multipart upload (reuses `project_file_service.add_project_file`) + sets `cover_image_url`
- `POST /projects/{id}/blog/cover/generate` — AI-generated hero image via the existing Gemini-flash-image pipeline used by presentations (see `matcha_work_document.py:1838-1897`). Body: `{prompt, aspect: "16:9" | "4:3" | "1:1"}`
- `GET /projects/{id}/blog/export/{fmt}` — thin wrapper over existing `/projects/{id}/export/{fmt}` that also injects front-matter at the top for markdown (YAML title/slug/cover/tags) so Substack/Ghost import works cleanly. Supported formats: `md`, `md_frontmatter`, `html`, `docx`, `pdf`
- `GET /projects/{id}/blog/preview` — returns rendered HTML (server-side markdown→HTML via the same lib used by PDF export) including cover image, byline, reading time, and concatenated sections. Not public; auth required. Useful for the client-side preview pane without reimplementing markdown in Swift.

### 3. Blog context injector — sibling to recruiting & consultation

Add `_inject_blog_context(ctx, row)` in `matcha_work.py` near the existing injectors. Dispatch from `_inject_recruiting_project_context` when `project_type == "blog"`:

```
=== BLOG POST CONTEXT ===
This chat is tied to a blog post draft.
Title: {title}
Slug: {slug}
Status: {status}{(' · scheduled ' + scheduled_at) if scheduled}
Audience: {audience or '(not set — ask the user if drafting)'}
Tone: {tone}
Tags: {tags}
Word count: {stats.word_count} · Reading time: {stats.read_minutes} min
Excerpt: {excerpt or '(none)'}

Current outline (sections, in order):
  1. About the Role (142 words)
  2. Responsibilities (310 words)
  ...

SEO meta description: {seo.meta_description or '(empty — offer to draft one)'}

Open sources cited: {sources[:5] urls}
```

### 4. AI skill & prompt — `server/app/matcha/services/matcha_work_ai.py`

Add to `SUPPORTED_AI_SKILLS`: `"blog"`. Add `BLOG_FIELDS` list and `_validate_updates_for_skill` branch mirroring project fields. Fields the AI may emit under `skill="blog"`:

- `blog_outline`: `[{heading, bullets: [string]}]` — proposal the client surfaces as insertable section scaffold
- `blog_section_draft`: `{section_id, title?, content}` — full draft for one section
- `blog_section_revision`: `{section_id, content, change_summary}` — revise existing content
- `blog_title_suggestions`: `[string]` — 3–5 options
- `blog_excerpt`: string
- `blog_meta_description`: string (150–160 char target — validate)
- `blog_cover_prompt`: string — feeds /blog/cover/generate
- `blog_tag_suggestions`: `[string]`

Add new system-prompt block (same layering as consultation block):

```
BLOG posts (authoring workspace, NOT the public site blog):
- When CONSULTATION CONTEXT says blog, you're helping the user draft an article.
- Draft voice = the configured tone. Default to "expert-casual": concrete, confident, uses the user's language; avoid filler and LLM tics ("delve", "navigate the landscape", "in today's fast-paced world").
- First-pass OUTLINE requests: emit blog_outline (4–8 sections with 2–4 bullets each). Do NOT emit blog_section_draft on the same turn.
- Section drafting: emit blog_section_draft keyed by section_id. 200–450 words per section unless user asks otherwise. Embed markdown; use subheadings, short paragraphs, bullet lists where they earn their keep.
- Revisions: emit blog_section_revision with change_summary ("tightened intro; added concrete example; removed filler").
- SEO draft (meta/title/excerpt) on request only. Meta description must be 150–160 chars, lead with the pain/benefit.
- Never fabricate stats, quotes, or URLs. If you need a source, ask the user to paste one — do not make up "According to a 2024 study" content.
- Respect the configured audience: if audience is "HR leaders", don't explain what HR is.
- When suggesting a title or slug, propose multiples; never silently rename the post.
```

### 5. `_apply_ai_updates_and_operations` branch (`matcha_work.py:1207+`)

When `skill == "blog"` and `project_id`:
- `blog_outline` → don't mutate sections (user decides). Return to client via structured_update in the SSE complete payload so UI renders an "Insert as sections" button.
- `blog_section_draft` → find section by `section_id` and call `project_service.update_section` with the drafted content. Triggers `recompute_blog_stats`.
- `blog_section_revision` → same path as draft; `change_summary` bubbles up as a diff note on the assistant message.
- `blog_title_suggestions` / `blog_tag_suggestions` / `blog_excerpt` / `blog_meta_description` / `blog_cover_prompt` → return as structured_update only; client surfaces as suggestion chips the user accepts.

Continue belting: if `skill == "blog"` and `project_id` is None, drop all blog_* keys (same approach as consultation guard you just shipped).

### 6. Cover image generation

Reuse the Gemini image pipeline in `matcha_work_document.py:1838-1897` (already used for presentation covers). New endpoint `POST /projects/{id}/blog/cover/generate` constructs prompt from `{blog.cover_image_prompt or auto-compose from title + audience + tone}`, requests 16:9 by default, stores URL in `project_data.cover_image_url` and in `project_files` as a regular attachment (filename prefix `cover_`).

### 7. Slug utility

```python
import re
def _slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80] or "untitled"
```

On title change in `update_project`, also re-derive slug **only if** the current slug matches the previous title's slug (i.e. user hasn't manually edited). Otherwise preserve user override.

---

## macOS Client Changes

### 1. Models — `desktop/Matcha/Matcha/Models/MatchaWorkModels.swift`

Below `MWConsultationData`:

```swift
struct MWBlogData {
    var slug: String?
    var excerpt: String?
    var coverImageUrl: String?
    var coverImagePrompt: String?
    var author: MWBlogAuthor
    var audience: String?
    var tone: String
    var tags: [String]
    var seo: MWBlogSEO
    var status: String          // draft | scheduled | published
    var scheduledAt: String?
    var publishedAt: String?
    var distribution: MWBlogDistribution
    var sources: [MWBlogSource]
    var stats: MWBlogStats
    var fromConsultationId: String?

    static func from(projectData: [String: AnyCodable]?) -> MWBlogData { /* parse */ }

    var readingTimeLabel: String { "\(max(1, stats.readMinutes)) min read" }
    var characterBudget: (meta: Int, title: Int) { (meta: 160, title: 60) }
}

struct MWBlogAuthor: Codable, Hashable { var name: String?; var avatarUrl: String?; var byline: String? }
struct MWBlogSEO: Codable, Hashable { var metaTitle, metaDescription, canonicalUrl, ogTitle, ogDescription, ogImageUrl: String? }
struct MWBlogStats: Codable, Hashable { var wordCount: Int; var readMinutes: Int }
struct MWBlogSource: Codable, Hashable, Identifiable { let id: String; var url: String; var title: String? }
struct MWBlogDistribution: Codable, Hashable { var copyLinkPrimary: String; var lastPublishedPlatform: String? }
```

### 2. `MatchaWorkService` additions

- `createBlog(title, audience, tone, tags, author, fromConsultationId) -> MWProject`
- `patchBlog(id, ...) -> MWProject`
- `addBlogSource`, `deleteBlogSource`
- `transitionBlogStatus(id, to, scheduledAt)`
- `uploadBlogCover(id, data, filename) -> MWProject`
- `generateBlogCover(id, prompt, aspect) -> MWProject`
- `exportBlog(id, fmt) -> Data`
- `previewBlog(id) -> String` (HTML)

### 3. `ProjectDetailViewModel`

- `blogData: MWBlogData` computed
- Mutators for each helper
- `applyOutline(sections:)` — bulk insert proposed outline sections via existing `addProjectSection`
- `insertSectionDraft(sectionId, content)` — thin wrapper over `updateProjectSection`

### 4. `BlogEditorView.swift` (new right panel)

Tabs in the right pane (replaces `standardLayout` when `projectType == "blog"`):

| Tab | Contents |
|---|---|
| **Write** | HSplit. **Left**: sections sidebar (reuse ProjectDetailView standardLayout sections column) + `SectionEditorView` for active section. **Right**: live markdown preview pane. Toolbar above editor: word-count chip, reading-time chip, tone chip, + section button. Cmd-K command palette: "Expand this section", "Tighten", "Add example", "Summarize so far", "Suggest title" — each fires a canned prompt into the linked chat. |
| **Cover** | AsyncImage of current cover + two actions: "Upload image" (file picker → `uploadBlogCover`) / "Generate with AI" (prompt text field → `generateBlogCover`). Regenerate button with aspect ratio segmented picker (16:9 / 4:3 / 1:1). |
| **SEO** | Title input (live char count vs 60). Slug input with auto-derive + lock toggle. Excerpt multiline with char count. Meta description (target 150–160, red at <120 or >170). Tag chips with add input. Audience text field. Tone segmented. Cover image doubles as OG image by default; override toggle exposes `og_image_url` field. |
| **Publish** | Status pill (draft/scheduled/published). **Schedule**: date/time picker (only when status=scheduled). **Distribution**: two primary buttons — "Copy markdown" (front-matter variant) and "Copy HTML". Secondary "Export…" menu (PDF / DOCX / plain markdown). Last-published hint + "Publish now" action that flips status→published and stamps `published_at`. Phase 2 will add direct Ghost/Substack/Medium publish buttons here. |
| **Sources** | List of cited URLs (from AI sources array). Add/remove rows. User vets before publishing. |

Preview pane: for MVP use Swift `AttributedString(markdown:)` like `MessageBubbleView` does (no server round-trip). Limitation: no inline image rendering beyond what AttributedString supports — fine for MVP.

### 5. `NewBlogSheet.swift`

Modal (width ~500) with fields:
- **Title** (required, becomes project title)
- **Audience** (helpful — feeds AI tone)
- **Tone** (segmented: expert-casual / technical / exec-brief / conversational / academic)
- **Tags** (comma-separated)
- **Starter outline toggle** — if on, submits an AI request immediately to return `blog_outline`; sections are inserted when the user accepts. If off, create empty.

### 6. Sidebar integration

Add `"blog"` to `ContentView.swift` popover picker under the existing Projects `+` menu (icon `square.stack.3d.up`). Don't create a separate "Blogs" sidebar section — blogs live under Projects with a small blog-badge on each row. Rationale: users tend to have many more blogs over time than consultations; keeping them in the Projects list avoids a crowded sidebar, and stage/status filtering in ProjectListView can surface unpublished drafts.

Extend `ProjectListView` row to show:
- Blog badge + reading-time chip when `projectType == "blog"`
- Status pill (draft/scheduled/published) with color coding
- Filter bar above the Projects list: All / Drafts / Scheduled / Published (only when blog posts exist)

### 7. `ProjectDetailView.swift` fourth branch

```swift
if viewModel.project?.projectType == "recruiting" {
    recruitingLayout
} else if viewModel.project?.projectType == "consultation" {
    consultationLayout
} else if viewModel.project?.projectType == "blog" {
    blogLayout
} else {
    standardLayout
}
```

`blogLayout`: HSplit of `ChatPanelView` (left, ~360 min) + `BlogEditorView` (right).

---

## Phases

### Phase 1 — Write → Preview → Export (3–4 days)
Minimum viable writing loop.

- Backend: `blog` project_type + seed, `PATCH /blog`, `POST /blog/status` (draft↔published only), `recompute_blog_stats` on section writes, export front-matter wrapper, blog context injector, system prompt block, `_apply_ai_updates_and_operations` blog branch
- macOS: `MWBlogData`, NewBlogSheet, BlogEditorView with Write + Publish tabs (status toggle + copy markdown/HTML), ProjectDetailView fourth branch, ProjectListView badge + filter
- AI: outline, section draft, section revision, title suggestions
- Export: markdown with front-matter, existing PDF/DOCX paths

### Phase 2 — Cover image + SEO tab (2–3 days)
The "looks like a real blog" phase.

- Backend: cover upload + AI generation endpoints, source refs CRUD
- macOS: Cover tab, SEO tab, Sources tab, AI-suggested title/meta/excerpt/tags/tag chips
- Slug auto-derive + manual override

### Phase 3 — Scheduling + consultation handoff (2 days)
- Backend: scheduled publish worker (Celery) that flips status at `scheduled_at`, `POST /blog/from-consultation/{cid}` endpoint that spawns a blog project pre-populated from a consultation's session summaries
- macOS: schedule date/time picker, "New blog from this consultation" button in `ConsultationDetailView`

### Phase 4 — Direct publish integrations (later, not MVP)
- Ghost Admin API (most freelance-friendly)
- Substack (no official API — use email-to-publish or clipboard fallback)
- Medium API (deprecated but still works)
- Admin-only: "Publish to marketing site blog" — copies finished project into `blog_posts` table for public site

### Phase 5 — Analytics / comments / collaboration polish (later)
- Analytics hook (read count, dwell) once there's a public host
- Per-post comments or external Disqus embed
- Multi-author sharing via `mw_project_collaborators` (already works, just surface author picker)

---

## Critical Files

**Backend**
- `server/app/matcha/services/project_service.py` — `_ALLOWED_PROJECT_TYPES` + `_seed_blog_data` + `patch_blog` + source CRUD + `recompute_blog_stats` hooks + `_slugify`
- `server/app/matcha/routes/matcha_work.py` — `POST /projects` extension, new `/blog/*` endpoints, `_inject_blog_context` sibling, blog branch in `_apply_ai_updates_and_operations` (near line 1207), blog skill guard when no project_id
- `server/app/matcha/services/matcha_work_ai.py` — `SUPPORTED_AI_SKILLS`, `BLOG_FIELDS`, `_validate_updates_for_skill` branch, system-prompt blog block
- `server/app/matcha/services/matcha_work_document.py:1838-1897` — reuse Gemini flash-image pipeline

**Client**
- `desktop/Matcha/Matcha/Models/MatchaWorkModels.swift` — MWBlogData + sub-structs
- `desktop/Matcha/Matcha/Services/MatchaWorkService.swift` — blog methods
- `desktop/Matcha/Matcha/ViewModels/ProjectDetailViewModel.swift` — `blogData` computed + mutators
- `desktop/Matcha/Matcha/Views/MatchaWork/ProjectDetailView.swift` — fourth branch
- `desktop/Matcha/Matcha/Views/MatchaWork/BlogEditorView.swift` — NEW
- `desktop/Matcha/Matcha/Views/MatchaWork/NewBlogSheet.swift` — NEW
- `desktop/Matcha/Matcha/Views/MatchaWork/MarkdownPreviewView.swift` — NEW (thin wrapper over `AttributedString(markdown:)` with styling)
- `desktop/Matcha/Matcha/Views/MatchaWork/ProjectListView.swift` — blog badge + filter bar
- `desktop/Matcha/Matcha/App/ContentView.swift` — `+` popover fourth entry
- `desktop/Matcha/Matcha.xcodeproj/project.pbxproj` — 3 new file entries

**Reuse (do not touch)**
- `mw_projects` / `mw_project_files` / `mw_threads` / `mw_project_collaborators`
- `project_file_service.add_project_file`
- `SectionEditorView.swift` for section editing
- `MessageBubbleView.swift` markdown renderer (shared pattern)
- Existing export pipeline in `matcha_work.py:4795-4935` (add front-matter wrapper, do not rewrite)
- `core/routes/blog.py` + `core/models/blog.py` (the MARKETING-SITE blog — Phase 4 "publish to" target, otherwise untouched)

---

## Verification

### Backend
```bash
cd server
python3 -m pytest tests/ -v -k "project or blog"
python3 run.py
```

Manual curl flow:
```bash
# 1. Create blog
PID=$(curl -sXPOST $API/matcha-work/projects -H "Authorization: Bearer $T" \
  -d '{
    "title":"The Jurisdictional Maze",
    "project_type":"blog",
    "blog": {"audience":"HR leaders","tone":"expert-casual","tags":["compliance","multi-state"]}
  }' | jq -r .id)

# 2. Check seed
curl -s $API/matcha-work/projects/$PID -H "..." | jq '.project_data | {slug, tone, status, stats}'

# 3. Add a section and verify stats auto-update
curl -XPOST $API/matcha-work/projects/$PID/sections -H "..." \
  -d '{"title":"Intro","content":"The shift toward remote work has transformed HR..."}'
curl -s $API/matcha-work/projects/$PID -H "..." | jq '.project_data.stats'

# 4. Ask AI for outline
# (through the chat stream endpoint; AI should emit blog_outline)

# 5. Patch SEO
curl -XPATCH $API/matcha-work/projects/$PID/blog -H "..." \
  -d '{"seo":{"meta_description":"How HR leaders navigate multi-state compliance without a 50-state law firm on retainer."}}'

# 6. Publish
curl -XPOST $API/matcha-work/projects/$PID/blog/status -H "..." -d '{"to":"published"}'

# 7. Export with front-matter
curl $API/matcha-work/projects/$PID/blog/export/md_frontmatter -H "..." -o out.md
head -20 out.md   # should show YAML front-matter
```

### macOS happy path
1. Launch personal account. Sidebar → Projects `+` → Blog → fill "The Jurisdictional Maze" + audience + tone → create.
2. BlogEditorView loads on Write tab. Chat panel left, Write/Preview right.
3. Ask AI "draft me an outline for this post". Complete event → `blog_outline` returned → "Insert as sections" button visible → click → 6 sections inserted.
4. Click a section → SectionEditorView opens. Ask chat "expand this section" → assistant emits `blog_section_draft` → section auto-updated + toast "Section drafted · 280 words".
5. Word-count chip at top updates to the new total. Reading-time chip recomputes.
6. Switch to Cover tab → "Generate with AI" → prompt pre-filled from title + audience → cover appears.
7. SEO tab → AI-suggest meta description button → `blog_meta_description` → click "Use this" → field populated.
8. Publish tab → "Copy markdown" → paste into Substack → verify front-matter parses.
9. Status → Published → `published_at` stamped. Sidebar row now shows green "published" chip.
10. Create a second blog from scratch → confirm `/blog/status` draft state, no phantom sections from prior.

### Regression
- General project → still loads standardLayout
- Consultation project → still loads consultationLayout
- Recruiting project → still loads recruitingLayout
- Plain thread (no project) → no-project guard still prevents `skill="blog"` hallucinations (same branch as `project` guard already shipped)

### Tight dev loops
- `cd desktop/Matcha && xcodebuild -scheme Matcha build` after each Swift change
- `python3 -m pytest tests/matcha_work/ -v -x` after each backend change

---

## Risk / Open Questions

1. **Markdown preview in Swift vs server-rendered HTML**: Phase 1 uses Swift's `AttributedString(markdown:)`. It can't render embedded images or complex tables well. Option: for the Preview pane, call `/blog/preview` and render HTML via `WKWebView`. Fidelity win vs extra plumbing. Recommend starting with Swift AttributedString, add WKWebView in Phase 2 if users complain.

2. **Cover image generation cost**: Gemini image generation is pay-per-call. Gate with a per-user quota (reuse `token_budget_service` pattern) or cap to 5/post.

3. **Front-matter dialect**: Ghost uses its own YAML, Substack ignores front-matter, Medium ignores. Default export = Ghost-compatible YAML since it's the most permissive. Plain `md` stays without front-matter as escape hatch.

4. **Slug collisions**: slugs aren't unique in the project namespace (different users can have same slug), which is fine because we don't host them publicly. If/when we publish to marketing site (Phase 4), that table already has slug uniqueness.

5. **AI honesty about sources**: system prompt forbids fabricating citations but models still do. UI surfaces `sources` list prominently; block publish status transition if `content` has `[N]` citation markers but `sources` is empty? Probably annoying for MVP. Add a soft warning toast instead.

6. **Consultation → blog handoff (Phase 3)**: when spawning from a consultation, should we auto-include session notes in the first section, or just pass the consultation context to the AI so it can ask "what angle do you want to write about"? Latter is better — don't pre-fill body, let the user choose.

7. **Image-in-body uploads**: for MVP, user pastes external URLs in markdown. Phase 2 adds a drag-drop into SectionEditor that uploads via `project_files` and inserts markdown `![alt](url)`.

8. **Public URL / hosting**: explicitly out of scope. Always "copy markdown" / "copy HTML" for MVP. If demand emerges, Phase 4 adds CMS publish integrations — still no public hosting in-app.

9. **Existing `core/routes/blog.py`**: 100% unrelated. MVP doesn't touch it. Phase 4's "publish to marketing blog" is admin-only and becomes the only crossover point — still a one-way copy, not a shared model.
