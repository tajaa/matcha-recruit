# oceanlab v1 — Digital Label Platform: Master Ingestion Pipeline

## Context

Finch is starting a natively-digital record label (+publishing, later sync licensing for film/TV). V1 scope agreed: **master ingestion with full metadata → delivery (export package + auto YouTube upload to the label's channel + SoundCloud) → royalty setup/collection for master + publishing per release**. Internal label tool, no artist accounts. Repo `/Users/finch/Documents/github/oceanlab` is empty except bare `client/` + `server/` dirs.

**Stack:** FastAPI + PostgreSQL + SQLAlchemy (sync 2.0 `Mapped[]`, psycopg3) + Alembic in `server/`; TypeScript + React + Vite + Tailwind v4 + TanStack Query in `client/`. DB in existing `matcha-postgres` container.

Setup commands:
```bash
docker exec matcha-postgres createdb -U matcha oceanlab
docker exec matcha-postgres createdb -U matcha oceanlab_test
# DATABASE_URL=postgresql+psycopg://matcha:matcha_dev@127.0.0.1:5432/oceanlab
```

## Domain reality (verified Aug 2026)

- **DSPs:** no direct upload for new labels → v1 export package (audio+artwork+manifest) for manual DistroKid/TuneCore upload. **DDEX ERN cut** (distributors generate it themselves; model stays ERN-mappable). TuneCore accepts own ISRC+UPC; DistroKid own ISRC only.
- **YouTube:** `videos.insert` = **1600 units** against the default 10,000 units/day project quota (~6 uploads/day); `playlists.insert`/`playlistItems.insert` = 50 units each. The 100/day figure is the separate per-channel upload cap, not a quota grant. Request a quota increase together with the API audit form; until granted, multi-track deliveries span multiple days. Uploads from **unaudited API projects locked private**; audit form + OAuth app "In production" required (testing status → refresh token dies in 7 days). Build works day one; videos stay private until audit passes.
- **SoundCloud:** self-serve app registration open, requires Artist Pro sub on label account. `POST /tracks` multipart, 4GB cap.
- **Royalty orgs have no write APIs.** Max automation = generate each org's bulk file: MLC bulk work-registration spreadsheet (mechanical), ASCAP/BMI portal or MusicMark EBR/CWR (performance), SoundExchange "ISRC Ingest" spreadsheet (neighboring), distributor CSV reports in (master).
- **ISRC:** $95 once, usisrc.org prefix, self-assign `PREFIX-YY-NNNNN`, designation unique per year. **UPC:** GS1 Single GTIN $30/each or free distributor-assigned.

## Key design decisions

| Decision | Choice |
|---|---|
| Background jobs | FastAPI BackgroundTasks + `jobs` table + handler registry; client polls `/api/jobs/{id}`. Startup sweep: `running` → `failed("server restarted")`. |
| DB access | Sync SQLAlchemy 2.0, psycopg3. All heavy work (ffprobe/Pillow/zip/CSV) blocking anyway; sync routes run in threadpool. |
| Uploads | Single multipart `UploadFile`, chunked copy (Starlette spools >1MB to temp file — flat memory). Client progress via XHR `onUploadProgress`. |
| ISRC placement | **On `Recording`, not `Track`.** ISRC identifies the sound recording; Track = placement on a Release. Same master on single+album keeps one ISRC. |
| Auth | Static bearer token `OCEANLAB_TOKEN`; one dependency; 401 on mismatch. `/api/health` open. |
| CORS | None — Vite proxy `/api` → `127.0.0.1:8000`. |
| Storage | `Storage` protocol, opaque S3-style keys, `LocalDiskStorage` under `server/var/storage`. DB stores keys only. |
| YouTube upload unit | **One video per track** (still-image render via ffmpeg) + **one playlist per release** on the label channel. Privacy from config (`private` until audit passes, then `public`). Delivery is resumable across days: quota exhaustion is the *normal* case, not an edge case. |
| Money | `Numeric(12,4)` + `currency: str(3)`. Never floats. |
| PKs | UUIDv4 (`sqlalchemy.Uuid`). |
| Splits | Warn ≠100% while editing; **block at packaging gate**. |
| UI lib | Tailwind v4 + homegrown primitives, native `<dialog>`. Recharts only royalty dashboard (read `dataviz` skill first). |

## Config (`app/config.py`, pydantic-settings, `.env`)

```python
class Settings(BaseSettings):
    database_url: str
    oceanlab_token: str
    storage_root: Path = Path("var/storage")
    label_name: str = "Oceanlab"
    # YouTube
    youtube_client_secret_path: Path = Path("var/yt_client_secret.json")
    youtube_token_path: Path = Path("var/yt_token.json")
    youtube_privacy: Literal["private", "unlisted", "public"] = "private"
    youtube_category_id: str = "10"          # Music
    # SoundCloud (all optional → adapter falls back to manual mode)
    soundcloud_client_id: str | None = None
    soundcloud_client_secret: str | None = None
    soundcloud_token_path: Path = Path("var/sc_token.json")
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"            # /opt/homebrew/bin on this machine
```

## Data model (`app/models/`)

Shared `Base` w/ naming-convention MetaData + `TimestampMixin` (`created_at`, `updated_at`, server defaults). Python `enum.StrEnum` classes stored as `sa.Enum(native_enum=False)` (plain varchar + check — painless Alembic).

```
Artist: id, name(unique), sort_name?, country?(2), spotify_id?, apple_music_id?, notes?
Contributor: id, name, legal_name?, ipi_number?(11), pro_affiliation?, email?, notes?

Release: id, title, release_type: ReleaseType(album|ep|single),
  status: ReleaseStatus(draft|ready|packaged|delivered|released) = draft,
  upc?(unique,13), catalog_number?(unique), release_date?, original_release_date?,
  label_name (default settings.label_name), c_line?, p_line?, genre?, subgenre?,
  territories: str = "WW", artwork_file_id? → File(RESTRICT), primary_artist_id → Artist, notes?
ReleaseArtist: release_id(CASCADE), artist_id, role(primary|featured), position:int
  unique(release_id, artist_id, role)

Track: id, release_id → Release(CASCADE), recording_id → Recording(RESTRICT),
  disc_number:int=1, position:int, title_override?
  unique(release_id, disc_number, position) DEFERRABLE INITIALLY DEFERRED  ← reorder swaps

Recording: id, title, version?, isrc?(unique,12), explicit: bool|None (tri-state, null=unset),
  language?(2), recording_year?, audio_file_id? → File(RESTRICT),
  duration_seconds? Numeric(9,3), sample_rate?, bit_depth?, channels?, audio_format?,
  primary_artist_id → Artist

Work: id, title, iswc?(unique,11), language?, notes?
RecordingWork: recording_id, work_id — composite pk

Credit: id, recording_id(CASCADE), contributor_id, role: CreditRole(producer|performer|mixer|
  mastering_engineer|recording_engineer|featured|remixer|other), credited_as?, position:int
WorkWriter: id, work_id(CASCADE), contributor_id, role: WriterRole(composer|lyricist|
  composer_lyricist|arranger|translator), share_pct Numeric(6,3),
  publisher_name?, publisher_share_pct? Numeric(6,3)
  unique(work_id, contributor_id, role)
MasterSplit: id, recording_id(CASCADE), contributor_id, role?, share_pct Numeric(6,3)
  unique(recording_id, contributor_id)

File: id, kind: FileKind(audio_master|artwork|royalty_statement|package|registration_export|
  rendered_video), storage_key(unique), original_filename, mime_type, size_bytes:BigInteger,
  sha256(64), width?, height?
IsrcConfig: id=1, registrant_prefix(5) e.g. "QZABC", year_digits(2), next_designation:int=1
UpcCode: id, code(unique,13), status(available|assigned), release_id?, assigned_at?
Job: id, kind:str, status(queued|running|done|failed), payload JSONB, result? JSONB,
  error?, started_at?, finished_at?

RegistrationTask: id, release_id(CASCADE), target: RegTarget(pro|mlc|soundexchange|distributor),
  status: RegStatus(not_started|in_progress|submitted|confirmed|not_applicable),
  external_ref?, export_file_id? → File, submitted_at?, confirmed_at?, notes?
  unique(release_id, target)
Delivery: id, release_id(CASCADE), target: DeliveryTarget(export_package|youtube|soundcloud),
  status: DeliveryStatus(pending|in_progress|complete|failed|manual),
  package_file_id? → File, external_ref?, error?, log?, started_at?, finished_at?
DeliveryItem: id, delivery_id(CASCADE), track_id → Track, status: DeliveryStatus,
  external_ref?  (per-track YouTube video id / SoundCloud track id), error?
  unique(delivery_id, track_id)

RoyaltyStatement: id, source:str, period_start, period_end, currency(3), file_id → File,
  status(uploaded|parsing|parsed|failed), total_amount?, line_count:int=0, matched_count:int=0
RoyaltyLine: id, statement_id(CASCADE), raw JSONB, isrc?, iswc?, upc?, title_raw?,
  artist_raw?, territory?, units?:BigInteger, amount Numeric(12,4), currency(3),
  recording_id? → Recording(SET NULL), work_id? → Work(SET NULL),
  match_method(isrc|iswc|manual|unmatched)
  index(statement_id), index(isrc), index(recording_id)
```

## Server file tree

```
server/
├── pyproject.toml            # uv; fastapi, uvicorn[standard], sqlalchemy>=2, alembic,
│                             # psycopg[binary], pydantic-settings, python-multipart,
│                             # mutagen, pillow, openpyxl, google-api-python-client,
│                             # google-auth-oauthlib, httpx; dev: pytest, pytest-cov
├── .env.example  alembic.ini
├── alembic/{env.py, versions/}     # env.py imports app.models for autogenerate
├── var/                            # gitignored (storage/, yt_token.json, …)
├── scripts/
│   ├── seed.py                     # IsrcConfig row, sample artist/release (idempotent)
│   └── youtube_auth.py             # one-time installed-app OAuth → var/yt_token.json
└── app/
    ├── main.py  config.py  db.py  deps.py
    ├── models/   __init__.py base.py artist.py contributor.py release.py track.py
    │             recording.py work.py file.py codes.py job.py registration.py
    │             delivery.py royalty.py
    ├── schemas/  (mirrors models: Read/Create/Update pydantic per domain + job.py,
    │              validation.py, common.py w/ Page[T])
    ├── routers/  health.py jobs.py artists.py contributors.py releases.py tracks.py
    │             recordings.py works.py codes.py packaging.py deliveries.py
    │             registrations.py royalties.py
    ├── services/
    │   ├── storage.py audio_meta.py artwork.py isrc.py upc.py validation.py
    │   ├── packaging.py jobs.py matching.py video_render.py
    │   ├── registration_exports/  base.py mlc.py soundexchange.py pro.py
    │   ├── royalty_parsers/       base.py distrokid.py generic_csv.py
    │   └── delivery/              base.py export_package.py youtube.py soundcloud.py
    └── tests/
        ├── conftest.py  factories.py
        ├── fixtures/    (tone-16b-44k.wav, tone-24b-96k.flac, fake.mp3-as.wav,
        │                 art-3000.jpg, art-2999.png, art-cmyk.jpg, art-alpha.png,
        │                 distrokid-sample.csv, distrokid-bom-negative.csv)
        ├── test_isrc.py test_upc.py test_audio_meta.py test_artwork.py
        ├── test_validation.py test_packaging.py test_matching.py
        ├── test_royalty_parsers.py test_registration_exports.py
        ├── test_delivery_youtube.py test_video_render.py
        └── test_api_releases.py test_api_auth.py
```

## Service signatures + behavior + edge cases

### `services/storage.py`
```python
class Storage(Protocol):
    def put(self, key: str, src: BinaryIO) -> tuple[int, str]: ...   # (size_bytes, sha256), 1MB chunks
    def open(self, key: str) -> BinaryIO: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...                          # missing key = no-op
    def local_path(self, key: str) -> Path | None: ...               # None for future S3; ffmpeg needs real paths → S3 impl downloads to temp

class LocalDiskStorage(Storage):
    def __init__(self, root: Path): ...

def get_storage() -> Storage        # from settings; FastAPI dependency
```
Key scheme: `masters/{recording_id}/original.{ext}` · `artwork/{release_id}/cover.{ext}` · `packages/{release_id}/{yyyymmdd-hhmmss}/package.zip` · `statements/{statement_id}/{filename}` · `exports/{registration_id}/{filename}` · `renders/{delivery_id}/{track_id}.mp4`.
Edge cases: key traversal (`..`) → reject at construction (`_safe(key)` asserts resolved path under root); partial write → write to `key + ".tmp"`, `os.replace` on success; duplicate put → overwrite (re-upload = replace).

### `services/audio_meta.py`
```python
@dataclass
class AudioMeta:
    duration_seconds: Decimal; sample_rate: int; bit_depth: int | None
    channels: int; audio_format: Literal["wav", "flac"]

class AudioMetaError(Exception): ...   # message is user-facing

def extract(path: Path) -> AudioMeta   # ffprobe -v error -print_format json -show_streams -show_format
def _extract_mutagen(path: Path) -> AudioMeta   # fallback when ffprobe missing/fails to parse
```
Validation inside `extract`: codec must be `pcm_s16le|pcm_s24le|pcm_s32le|pcm_f32le|flac`; else `AudioMetaError("Not a WAV/FLAC master: detected {codec}")`.
Edge cases: **mp3 renamed `.wav`** → ffprobe reports mp3 codec → reject (test fixture); 32-bit float WAV → accept, `bit_depth=32`; FLAC with embedded artwork → ignore art, meta from STREAMINFO; mono → accept `channels=1` (validator warns later); 0-byte/corrupt → `AudioMetaError`; multi-stream containers → use first audio stream only; duration missing from stream → fall back to `format.duration`.

### `services/artwork.py`
```python
@dataclass
class ArtworkMeta: width: int; height: int; format: Literal["jpeg", "png"]

class ArtworkError(Exception): ...

MIN_DIM = 3000; MAX_DIM = 6000; MAX_BYTES = 20 * 2**20

def validate_artwork(data: bytes) -> ArtworkMeta
```
Rules → `ArtworkError` with exact reason: not JPEG/PNG; mode not RGB (**CMYK reject** "convert to RGB"; **RGBA/alpha reject**; `P`/`L` reject); `width != height` reject (DSPs require square); `< 3000` reject; `> 6000` or `> 20MB` reject (DistroKid ceiling); apply `ImageOps.exif_transpose` before measuring (EXIF-rotated portrait scans). Progressive JPEG → accept.

### `services/isrc.py`
```python
class IsrcError(Exception): ...       # subclasses: NotConfigured, AlreadyAssigned, Exhausted

def assign_isrc(db: Session, recording_id: UUID) -> str
def format_isrc(prefix: str, year: str, n: int) -> str      # f"{prefix}{year}{n:05d}", no hyphens in DB
def display_isrc(isrc: str) -> str                          # client-side too: CC-XXX-YY-NNNNN
```
`assign_isrc`: `SELECT … FOR UPDATE` on `IsrcConfig` row; **year rollover**: if `current_year % 100 != int(year_digits)` → set `year_digits = now`, `next_designation = 1` (ISRC spec: designation unique per year, reset allowed); increment; commit by caller.
Edge cases: recording already has ISRC → `AlreadyAssigned` → 409; prefix unconfigured (empty string default) → `NotConfigured` → 422 w/ pointer to Settings; `next_designation > 99999` → `Exhausted` → 500 alert (never realistic); concurrency → two parallel calls must yield distinct codes (test with threads).

### `services/upc.py`
```python
def add_upcs(db: Session, codes: list[str]) -> int          # validates 12/13 digits + GTIN check digit, dedupes
def assign_upc(db: Session, release_id: UUID) -> str        # oldest available FOR UPDATE SKIP LOCKED
```
Edge cases: empty pool → 409 `"UPC pool empty — add codes in Settings"`; release already has UPC → 409; bad check digit → 422 listing offending codes; 12-digit UPC-A stored zero-padded to 13 (EAN-13).

### `services/jobs.py`
```python
JobHandler = Callable[[Session, dict], dict]                # payload -> result
JOB_HANDLERS: dict[str, JobHandler] = {}                    # "extract_audio_meta", "build_package", "deliver", "parse_statement"

def register(kind: str) -> Callable[[JobHandler], JobHandler]    # decorator
def submit(db: Session, background: BackgroundTasks, kind: str, payload: dict) -> Job
def _execute(job_id: UUID) -> None      # own SessionLocal; status running→done/failed; catches Exception → error=str(e), never raises
def sweep_stale(db: Session) -> int     # startup: running→failed("server restarted")
```
Edge cases: handler raises → job `failed`, error persisted, traceback logged server-side only; unknown kind → `failed` immediately; job row committed **before** `background.add_task` so client can always poll.

### `services/validation.py`
```python
@dataclass
class Issue: code: str; severity: Literal["error", "warning"]; message: str
             field: str | None = None; track_id: UUID | None = None
@dataclass
class ValidationReport: packageable: bool; issues: list[Issue]     # packageable = no errors

def validate_release(db: Session, release_id: UUID) -> ValidationReport
```
Rule table (code → severity):
```
R-TITLE, R-ARTIST, R-DATE, R-GENRE, R-CLINE, R-PLINE, R-TERR, R-UPC      error
R-ART-MISSING / R-ART-SPEC (dims/mode from File row)                      error
R-CATNO                                                                   warning
T-EMPTY (no tracks), T-GAP (positions not 1..n per disc), T-NOREC         error
A-AUDIO (recording missing audio file), A-FORMAT, A-QUALITY (<44100 or <16bit) error
A-ISRC (unassigned), A-EXPLICIT (explicit is null)                        error
A-LANG                                                                    warning
S-MASTER (master splits present but sum ≠ 100 ± 0.01)                     warning
S-WRITERS (a linked work has zero writers)                                warning
W-NOWORK (recording linked to no work — publishing side empty)            warning
```
Edge: release_date in past → warning (allowed — catalog backfill); duplicate recording on two tracks of same release → error `T-DUP`.

### `services/packaging.py`
```python
@dataclass
class PackageResult: file_id: UUID; manifest_rows: int; total_bytes: int

def build_package(db: Session, release_id: UUID, delivery_id: UUID) -> PackageResult
def sanitize_filename(s: str) -> str    # strip /\:*?"<>|, collapse ws, NFC normalize, max 120 chars
def manifest_rows(db: Session, release_id: UUID) -> list[dict]   # shared w/ tests (golden file)
```
Zip layout (built with `zipfile.ZipFile(mode="w", ZIP_STORED)` for audio — already compressed-ish, speed > size; `shutil.copyfileobj` in 1MB chunks from `storage.open`, never full read):
```
{catalog_number} - {artist} - {title}/
├── audio/{disc}-{position:02d} {track_title}.wav|.flac
├── artwork/cover.jpg|png
├── manifest.csv
└── manifest.json
```
`manifest.csv` columns: `disc, position, track_title, version, primary_artist, featured_artists, isrc, duration, explicit, language, writers (name [role] share%; …), producers, release_title, release_type, upc, catalog_number, label, release_date, genre, subgenre, c_line, p_line, territories`.
Edge cases: title `"AM/PM"` → sanitized path (test); two tracks sanitize to same filename → suffix ` (2)`; missing audio at package time (deleted between validate and build) → job fails cleanly with which track; re-package → new timestamped key, old package File kept (audit trail).

### `services/matching.py`
```python
def normalize_isrc(s: str | None) -> str | None   # strip hyphens/spaces/dots, upper, None if not len 12
def normalize_iswc(s: str | None) -> str | None   # strip to T + 10 digits
@dataclass
class MatchStats: total: int; matched_isrc: int; matched_iswc: int; unmatched: int

def match_statement(db: Session, statement_id: UUID) -> MatchStats
def match_line_manual(db: Session, line_id: UUID, recording_id: UUID | None, work_id: UUID | None) -> RoyaltyLine
```
Rules: line ISRC → recording (also sets `work_id` when recording has exactly one linked work); else ISWC → work; else `unmatched`. `rematch` only touches `unmatched` lines (manual matches preserved).
Edge cases: lowercase/hyphenated ISRCs (DistroKid varies) → normalize both sides; ISRC present but unknown → stays unmatched even if title matches (no fuzzy in v1); duplicate lines legit (same ISRC, different store/territory) → all match; statement `matched_count` recomputed after any manual match.

### `services/royalty_parsers/base.py`
```python
@dataclass
class ParsedLine: raw: dict; isrc: str | None; iswc: str | None; upc: str | None
    title_raw: str | None; artist_raw: str | None; territory: str | None
    units: int | None; amount: Decimal; currency: str

class StatementParser(Protocol):
    source: ClassVar[str]
    def parse(self, f: BinaryIO) -> Iterator[ParsedLine]: ...

PARSERS: dict[str, type[StatementParser]]        # {"distrokid": …, "generic_csv": …}
```
`distrokid.py`: real report columns (`Sale Month, Store, Artist, Title, ISRC, UPC, Quantity, Earnings (USD)`…). Handle: **UTF-8 BOM** (`utf-8-sig`), **negative earnings** (returns/adjustments — keep, they net out), `$`/comma-formatted amounts → `Decimal`, blank ISRC rows (YouTube Ads lines), unknown extra columns tolerated (into `raw` only). Malformed row → skip + count in job result `{"skipped": n}`, never abort whole statement.
`generic_csv.py`: `column_map` dict in job payload `{"isrc": "ISRC Code", "amount": "Net Royalty", …}` — covers any distributor/PRO CSV until dedicated parser exists.

### `services/registration_exports/`
```python
class RegistrationExporter(Protocol):
    target: ClassVar[RegTarget]
    filename: ClassVar[str]                     # e.g. "mlc-bulk-{release}.xlsx"
    def generate(self, db: Session, release_id: UUID) -> tuple[str, bytes]  # (filename, content)

EXPORTERS: dict[RegTarget, RegistrationExporter]
```
- `mlc.py` (openpyxl): one row per Work — title, ISWC, writers (name, IPI, role, share), publisher name/share, linked recording ISRCs. Mirrors MLC bulk-registration template columns.
- `soundexchange.py`: ISRC Ingest sheet — ISRC, track title, artist, album title, UPC, ℗-year, label, rights-owner claim %.
- `pro.py`: EBR-style CSV (MusicMark-compatible fields: work title, writers w/ IPI+PRO+share, publisher, ISWC if known).
Edge cases: work with no writers → excluded + noted in job result; generation stores a `File(kind=registration_export)` and sets `RegistrationTask.export_file_id`, status `not_started → in_progress`.

### `services/video_render.py`
```python
class RenderError(Exception): ...
def render_track_video(audio: Path, cover: Path, out: Path, *, ffmpeg: str = "ffmpeg") -> None
    # out is the COMPLETE output path (e.g. …/{track_id}.mp4); no suffix is appended
```
Exact command (subprocess, `check=True`, stderr captured into `RenderError`):
```
ffmpeg -y -loop 1 -i {cover} -i {audio} \
  -c:v libx264 -tune stillimage -r 2 -pix_fmt yuv420p \
  -vf scale=1920:1920:flags=lanczos \
  -c:a aac -b:a 384k -ar 48000 \
  -movflags +faststart -shortest {out}
```
Edge cases: PNG cover w/ odd dimension → `scale` to even 1920 handles; FLAC input fine (ffmpeg decodes); output duration must be within 1s of master duration → verify with ffprobe post-render, reading `out` itself, else `RenderError`; temp output in scratchpad-style `var/tmp`, moved into storage on success. Callers (`delivery/youtube.py`) pass the storage-derived `renders/{delivery_id}/{track_id}.mp4` temp path directly as `out`.

## YouTube auto-upload (label channel)

**One-time setup (human):** GCP project → enable YouTube Data API v3 → OAuth client (Desktop type) → download JSON to `server/var/yt_client_secret.json` → consent screen **"In production"** → run `uv run scripts/youtube_auth.py` (opens browser, sign into the **label channel's** Google account, scope `https://www.googleapis.com/auth/youtube` — covers upload + playlist mgmt) → refresh token saved `var/yt_token.json`. Submit **API audit form** in parallel; until approved every upload is forced private regardless of requested privacy (config default `private` matches this).

### `services/delivery/base.py`
```python
class DeliveryAdapter(Protocol):
    target: ClassVar[DeliveryTarget]
    def deliver(self, db: Session, delivery: Delivery) -> None   # mutates delivery + items; raises nothing (records errors)

ADAPTERS: dict[DeliveryTarget, DeliveryAdapter]

@register_job("deliver")   # payload {"delivery_id": …}
def run_delivery(db: Session, payload: dict) -> dict
```

### `services/delivery/youtube.py`
```python
class YouTubeAdapter:
    target = DeliveryTarget.youtube
    def deliver(self, db, delivery) -> None
    # internals:
    def _client(self):                       # build("youtube","v3",credentials=…); refresh via google-auth; raises AuthError if token missing/revoked
    def _verify_channel(self, yt) -> str     # channels.list(mine=True) → channel title+id into delivery.log
    def _upload_video(self, yt, path: Path, meta: TrackVideoMeta) -> str   # returns video_id
    def _create_playlist(self, yt, release) -> str
    def _add_to_playlist(self, yt, playlist_id, video_id, position) -> None

@dataclass
class TrackVideoMeta: title: str; description: str; tags: list[str]; privacy: str; category_id: str
def video_metadata(release, track, recording, settings) -> TrackVideoMeta
```
Per release flow: verify channel → create playlist `"{primary_artist} — {release_title}"` (skip when single, 1 track) → for each track in position order: render video (`video_render`) → resumable upload (`MediaFileUpload(path, chunksize=8*2**20, resumable=True)`, loop `next_chunk()` with progress into `delivery.log`) → set `DeliveryItem.external_ref = video_id`, store rendered File → add to playlist. `delivery.external_ref` = playlist id (or lone video id).
Metadata mapping: title `"{primary_artist} - {track_title}"` (+ `" ({version})"`); description = release title, ℗ line, ISRC, writer credits, `"Auto-uploaded by oceanlab"`; tags = [artist, release, genre]; `categoryId=10`; `privacyStatus=settings.youtube_privacy`; `publishAt` **not** set in v1 (needs private + audit anyway).
Idempotency/edge cases: item already `complete` with external_ref → skip on retry (retry only failed items); `HttpError 403 quotaExceeded/uploadLimitExceeded` → item + delivery `failed`, error `"YouTube quota exhausted — retry after midnight PT"`; token refresh failure → delivery `failed` immediately, error points at re-running `youtube_auth.py`; upload interrupted mid-chunks → resumable loop retries 5× w/ exponential backoff then item `failed`; partial success (3/5 tracks) → delivery `failed` but successful items keep video ids (retry completes remainder).

### `services/delivery/soundcloud.py`
```python
class SoundCloudAdapter:
    target = DeliveryTarget.soundcloud
    def deliver(self, db, delivery) -> None    # creds unset → status "manual" + instructions in log; creds set → per-track POST /tracks
    def _upload_track(self, http: httpx.Client, audio: Path, cover: Path, meta: dict) -> str
```
`POST https://api.soundcloud.com/tracks` multipart: `track[title]`, `track[sharing]=public|private`, `track[isrc]`, `track[genre]`, `track[release_date]`, `track[asset_data]` (audio), `track[artwork_data]` (cover). OAuth code flow one-time via small local-redirect script (mirror of `youtube_auth.py`, phase 3 stretch); token JSON w/ refresh. 4GB/track cap checked pre-upload. Edge: 429 → backoff+retry 3×; token expired → refresh once then fail with instructions.

### `services/delivery/export_package.py`
Wraps `packaging.build_package`; sets `package_file_id`, status `complete`. Only adapter that runs synchronously fast.

## API endpoints (`/api`, bearer except `/health`)

```
GET  /health                                  → {status, db, storage}
GET  /jobs/{id}                               → JobRead {status, result, error}

CRUD  /artists /contributors /works /recordings /releases
      GET lists paginated ?limit=&offset= (+releases: ?status=&artist_id=&q= ilike title)
      DELETE → 409 when FK-referenced (RESTRICT) with human message

POST  /releases/{id}/artwork        multipart  → FileRead | 422 ArtworkError.message
POST  /releases/{id}/assign-upc               → {upc} | 409/422
GET   /releases/{id}/validation               → ValidationReport
POST  /releases/{id}/tracks                   {recording_id, disc_number?, position?} (position defaults next)
POST  /releases/{id}/tracks/reorder           {track_ids: UUID[]}  (full order, deferred constraint)
PATCH|DELETE /tracks/{id}
POST  /recordings/{id}/audio        multipart → {file: FileRead, job_id} (meta job enqueued)
POST  /recordings/{id}/assign-isrc            → {isrc} | 409/422
PUT   /recordings/{id}/splits                 [{contributor_id, role?, share_pct}]  (replace-all)
PUT   /recordings/{id}/credits                [{contributor_id, role, credited_as?, position}]
PUT   /recordings/{id}/works                  {work_ids: UUID[]}
PUT   /works/{id}/writers                     [{contributor_id, role, share_pct, publisher_name?, publisher_share_pct?}]

GET|PUT /settings/isrc                        {registrant_prefix, year_digits, next_designation ro}
GET|POST /upcs                                POST {codes: str[]} → {added, rejected: []}

POST  /releases/{id}/package                  → {delivery_id, job_id} | 409 {issues} when not packageable
GET   /releases/{id}/deliveries               → DeliveryRead[] (incl. items)
POST  /releases/{id}/deliveries               {target: "youtube"|"soundcloud"} → {delivery_id, job_id}
                                              409 if release.status ∉ {packaged, delivered, released}
GET   /deliveries/{id}                        → DeliveryRead (poll during upload; log tail)
GET   /deliveries/{id}/download               → StreamingResponse zip (export_package only)
POST  /deliveries/{id}/retry                  → re-enqueue; only failed/manual; failed items only

GET   /releases/{id}/registrations            → RegistrationTaskRead[4]
PATCH /registrations/{id}                     {status?, external_ref?, submitted_at?, confirmed_at?, notes?}
POST  /registrations/{id}/generate-export     → {file_id, filename, job_id}
GET   /registrations?status=&target=          cross-release board
GET   /registration-exports/{file_id}/download

POST  /royalty-statements                     multipart + form {source, period_start, period_end, currency, column_map?}
                                              → {statement_id, job_id}
GET   /royalty-statements                     GET /royalty-statements/{id}?matched=false&limit=&offset=
POST  /royalty-lines/{id}/match               {recording_id?|work_id?} (both null = unmatch)
POST  /royalty-statements/{id}/rematch        → MatchStats
GET   /royalties/summary                      ?group_by=release|recording|source&from=&to=
                                              → [{key_id, key_name, amount, currency, units}]
```

## Client

```
src/api/client.ts        axios instance; interceptor: Authorization Bearer from localStorage;
                         401 response → clear token → token gate screen
src/api/hooks/           useReleases(filters) useRelease(id) useValidation(id) useJob(id, {poll: 1500ms until done/failed})
                         useDeliveries(releaseId, {poll while any in_progress}) useAssignIsrc() useUploadAudio() …
src/lib/upload.ts        uploadWithProgress(url, file, fields, onProgress: (pct)=>void): Promise<Response>  // XHR, not fetch
src/lib/format.ts        formatDuration(sec) formatMoney(amount, currency) displayIsrc(isrc)
pages/CatalogPage        table: title, artist, type, status badge, UPC, date; filters; "New release"
pages/ReleaseDetailPage  tabs: Tracks (TrackEditor: add recording, drag-reorder → POST reorder, ISRC assign button)
                         | Metadata (form, PATCH on blur) | Validation (ValidationPanel: grouped errors/warnings,
                         re-run button, "Package" CTA enabled iff packageable)
                         | Registrations (4 targets: status select, generate-export + download, external_ref)
                         | Deliveries (per-target cards: trigger, per-item status w/ YouTube links, log tail, retry)
pages/IngestPage         wizard: pick/create recording → drop WAV/FLAC → progress bar → poll job → extracted meta table
pages/RoyaltiesPage      statements table + upload dialog (source select, period, column-map builder for generic_csv)
                         → statement detail: MatchTable (unmatched lines, inline recording/work search, match button)
                         → summary dashboard (Recharts bar by release / line by period — read dataviz skill first)
pages/SettingsPage       ISRC prefix form, UPC pool textarea-add + counts, token field
```
`npm run gen:api` = `openapi-typescript http://127.0.0.1:8000/openapi.json -o src/api/types.gen.ts`.

## Test matrix

`conftest.py`: session-scoped engine on `oceanlab_test`, `Base.metadata.create_all` once; per-test nested transaction (SAVEPOINT) rollback; `client` fixture = `TestClient(app)` w/ auth header + `dependency_overrides[get_db]`; `factories.py` = plain builder functions (`make_release(db, tracks=2, complete=True)`).

```
test_isrc:      sequential codes; year rollover resets designation to 1; already-assigned → IsrcError;
                unconfigured → NotConfigured; 8 threads × 5 allocations → 40 unique codes
test_upc:       add validates check digit + dedupes; assign consumes oldest; empty pool 409; 12→13 pad
test_audio_meta:16b/44.1 wav exact fields; 24b/96k flac; mp3-renamed-wav rejected; corrupt rejected;
                mono ok; 32-bit float ok  (fixtures generated once by ffmpeg in a conftest session fixture)
test_artwork:   3000² jpg ok; 2999 reject; cmyk reject w/ "convert to RGB"; alpha reject;
                non-square reject; exif-rotated portrait → passes after transpose; >6000 reject
test_validation:complete release → packageable, 0 errors; each missing field → its code present;
                position gap → T-GAP; dup recording → T-DUP; explicit null → A-EXPLICIT;
                splits 99.9 → S-MASTER warning only (still packageable)
test_packaging: golden manifest.csv byte-compare (fixture release, frozen ids);
                zip paths match layout; "AM/PM" title sanitized; filename collision suffixed;
                deleted audio mid-build → job failed w/ track ref
test_matching:  exact isrc; "us-abc-26-00001" lowercase+hyphens matches; iswc fallback;
                unknown isrc stays unmatched despite matching title; manual match sets method=manual;
                rematch preserves manual; matched_count recount
test_royalty_parsers: distrokid-sample.csv row count + Decimal amounts; BOM file parses;
                negative earnings kept; "$1,234.56" → Decimal("1234.56"); malformed row skipped not fatal;
                generic_csv with column_map
test_registration_exports: mlc xlsx headers + one row per work incl. writers; workless work excluded;
                soundexchange sheet has isrc+upc+claim%; pro csv writer IPI present
test_video_render: command built correctly (subprocess mocked); duration-mismatch → RenderError;
                real 2s tone render smoke test (skipif no ffmpeg)
test_delivery_youtube: googleapiclient fully mocked — playlist created once; per-track insert called
                with correct snippet/title/privacy; quotaExceeded → delivery failed + message;
                retry uploads only failed items; token missing → failed w/ auth instructions
test_api_auth:  no header 401; bad token 401; health open
test_api_releases: create→add tracks→validation 409 on package→complete→package 200 job flow
```

## Phases

**Phase 1 — skeleton + schema:** uv init + deps; config/db/deps/main + health; both DBs created; all models + initial Alembic migration + seed script; pydantic schemas; CRUD routers (artists, contributors, releases, tracks, recordings sans audio, works, splits/credits/writers PUT-replace); isrc/upc services + routers + tests; conftest/factories; client scaffold (Vite, Tailwind v4, router, query, token gate, gen:api) + Catalog + ReleaseDetail (Tracks/Metadata tabs) + Settings.
*Exit:* full catalog CRUD through UI; ISRC/UPC assign works; `alembic upgrade head` clean on fresh DB; phase-1 tests green. (Python 3.14 wheel problem → `uv python pin 3.12`.)

**Phase 2 — ingestion:** storage.py + File wiring; audio_meta.py; `POST /recordings/{id}/audio` (chunked copy + sha256 + meta job); jobs service/router + startup sweep; artwork.py + endpoint; validation.py + endpoint; client IngestPage wizard + ArtworkUploader + ValidationPanel + useJob polling.
*Exit:* 24-bit WAV in → meta fields populate; artwork rejects each bad fixture with clear message; validation live.

**Phase 3 — packaging + delivery (incl. YouTube):** status machine + package endpoint gated on validator; packaging.py + golden tests + download; delivery base registry + export_package; video_render.py; `scripts/youtube_auth.py`; YouTubeAdapter (upload + playlist + retry semantics); SoundCloudAdapter (manual fallback; live API if creds present); Deliveries tab.
*Exit:* validated release → zip downloadable + manifest correct; **YouTube delivery uploads every track as video to label channel + playlist, links visible in UI** (private until audit — expected); retry after simulated quota failure completes remaining tracks.

**Phase 4 — registrations + royalties:** RegistrationTask seed (on create + backfill script); registration_exports (mlc/soundexchange/pro) + generate/download endpoints; statement upload + parser registry + parse job; matching + rematch + manual match; Registrations tab + board page; RoyaltiesPage (upload, MatchTable, summary dashboard w/ dataviz skill).
*Exit:* DistroKid CSV → ≥90% auto-match by ISRC, rest manually resolvable; dashboard totals reconcile with statement total; MLC/SX/PRO files download with correct rows.

## External account setup (human, parallel to build)

| Org | Action | Cost |
|---|---|---|
| usisrc.org | Rights-owner ISRC prefix → Settings page | $95 once |
| GS1 US | Single GTINs → UPC pool (or distributor UPCs) | $30/ea once |
| MLC | Publisher membership (W-9 + banking) | free |
| ASCAP or BMI | Publisher entity | $50 / $175+ |
| SoundExchange | Rights-owner + featured-artist reg | free |
| SoundCloud | Artist Pro on label acct → register API app → creds in .env | ~$12–16/mo |
| Google Cloud | Project + OAuth client (In production) + `youtube_auth.py` + **audit form** + quota-increase request (audit form has a quota section) | free; audit = weeks |
| Distributor | TuneCore (own ISRC+UPC) or DistroKid (own ISRC only) | per pricing |

## Verification

Per-phase exits above; `uv run pytest` green (matrix above); `npm run build` + `tsc --noEmit` clean; E2E: seed → create release w/ 2 tracks → upload WAVs + artwork → validation green → package → unzip, inspect manifest → trigger YouTube delivery on test channel → videos + playlist appear → upload sample DistroKid CSV → match rate + dashboard reconcile.

## Risks

- YouTube uploads private until audit passes (no Google SLA — weeks). Code unaffected; flip `youtube_privacy=public` after.
- SoundCloud API tied to Artist Pro; manual mode is the contingency, zero rework either way.
- BackgroundTasks lose in-flight jobs on restart — accepted; jobs table + sweep keeps UI honest.
- Registration exports mirror current org templates (MLC/SX column names drift) — regenerate cheap, templates isolated in `registration_exports/`.
- Territories-as-string crude; promote to table only if per-territory deals appear.
