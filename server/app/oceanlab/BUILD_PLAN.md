# Oceanlab label pipeline — audit + build plan

## Context

Goal: finish a song → it gets released. Finch owns 100% master + publishing, so the pipeline should default every split to him rather than ask.

`PROJECT.md` specs a 4-phase v1; **only Phase 1 shipped**. Everything touching bytes (audio, artwork, packaging, delivery) is unbuilt, and several PROJECT.md assumptions break in the monorepo.

**Built:** 20-table schema, CRUD for artists/contributors/works/recordings/releases/tracks/codes, ISRC+UPC assignment (row-locked, GTIN check digit, `FOR UPDATE SKIP LOCKED`), 73 green tests, Catalog/ReleaseDetail/Settings pages.

**Not built:** `storage.py`, `audio_meta.py`, `artwork.py`, `validation.py`, `packaging.py`, `video_render.py`, `services/delivery/*`, `registration_exports/*`, `royalty_parsers/*`, jobs runtime, routers for jobs/packaging/deliveries. `client/oceanlab/src/lib/upload.ts:uploadWithProgress` is written and **unused** — no upload endpoint exists.

### Monorepo blockers PROJECT.md does not account for

1. **`LocalDiskStorage` under `server/var/storage` loses masters.** Backend runs blue-green containers that are *removed* each deploy. Must be S3.
2. **`StorageService.upload_private_file` is the wrong tool** — it's `async` (oceanlab routes are sync), takes `file_bytes: bytes` (a 24/96 five-minute WAV is ~170MB, and the worker cgroup is 320M), and mints its own random key via `_generate_key`, discarding oceanlab's deterministic key scheme. Reuse its **`s3_client`** (plain sync boto3, `storage.py:45`) and `get_presigned_download_url` (sync, parses bucket from the URI, `storage.py:329`) — not that method.
3. **No ffmpeg in `server/Dockerfile`** → blocks `audio_meta` and all of YouTube. Worker shares the backend image, so one Dockerfile edit covers both.
4. **Worker memory 320M** (`docker-compose.yml:109`) and per `docker-compose.yml:100-104` **an OOM is not retried** — it is a silent FAILURE.
5. **Missing deps**: `mutagen`, `google-api-python-client`, `google-auth-oauthlib`. Present already: `Pillow`, `openpyxl`, `httpx`, `boto3`, `psycopg[binary]`.
6. **Prod not wired**: `oceanlab_app_01` unapplied (prod head still `tellus_app_15`), `OCEANLAB_TOKEN` absent from `~/matcha/.env.backend` → every route 503s. Host nginx *is* applied.

### The UPC/ISRC gate

PROJECT.md makes `R-UPC` and `A-ISRC` hard errors, so packaging is blocked without a $95 usisrc.org prefix and $30/release GS1 GTINs. DistroKid issues both free. Fix: drive those two severities off a label setting (`isrc_source`/`upc_source` ∈ `own|distributor`). `distributor` → warning + manifest reads "assigned by distributor". Ship today, flip later, no code change.

### Decisions locked

| Decision | Choice |
|---|---|
| DSP distribution | Export package → manual DistroKid upload. No consumer distributor exposes a public upload API. |
| Solo modelling | **Prefill, don't collapse.** Splits/Credits/Works stay visible, defaulted to Finch @ 100%, marked auto-created, editable. |
| Job runtime | **Celery** on the existing `matcha-worker`. |

Celery needs no new precedent — **cappe already does exactly this**: task module in `app/workers/tasks/` importing the guest app (`cappe_campaign_send.py` → `app.cappe.services.campaigns`), dispatched by lazy import inside the route handler (`app/cappe/routes/newsletter.py:196`).

---

## Stage 0 — turn prod on (no code)

1. `./scripts/migrate-prod.sh` — one revision `tellus_app_15` → `oceanlab_app_01`.
2. `OCEANLAB_TOKEN=$(openssl rand -hex 32)` into `~/matcha/.env.backend`; recreate backend container.

**Start in parallel (long poles, weeks):** YouTube Data API audit + quota-increase form; SoundCloud Artist Pro + app registration; optionally usisrc.org prefix + GS1 GTINs. **For collection (Stage 6):** MLC publisher membership (free), ASCAP or BMI publisher entity ($50/$175), SoundExchange rights-owner + featured-artist registration (free), and tick DistroKid's "YouTube Money" Content ID option — that is the practical master-side YouTube path (direct Content ID needs a catalog-size deal; own-channel AdSense additionally needs YPP: 1k subs / 4k watch-hours).

---

## Stage 1 — infra + Phase-1 gaps

### 1a. Image and deps

`server/Dockerfile:6-17` — append to the stage-1 apt list:
```dockerfile
    ffmpeg \
```
`server/requirements.txt` — add:
```
mutagen>=1.47
google-api-python-client>=2.100
google-auth-oauthlib>=1.2
```
`docker-compose.yml:109` — `memory: 320M` → `768M`, comment: oceanlab ffmpeg render + resumable upload; OOM is not retried.

### 1b. `server/app/oceanlab/config.py` additions

```python
s3_bucket: str | None = None          # OCEANLAB_S3_BUCKET; None -> core private bucket
key_prefix: str = "oceanlab"
```

### 1c. `server/app/oceanlab/services/storage.py` (new)

```python
class StorageError(Exception): ...

class ObjectStore(Protocol):
    def put(self, key: str, src: BinaryIO, *, content_type: str) -> tuple[int, str]:  # (size_bytes, sha256_hex)
    def open(self, key: str) -> BinaryIO:
    def exists(self, key: str) -> bool:
    def delete(self, key: str) -> None:
    @contextmanager
    def local_copy(self, key: str) -> Iterator[Path]:      # ffmpeg needs a real path
    def presigned_url(self, key: str, expires_in: int = 900) -> str | None:

class S3Store(ObjectStore):
    def __init__(self, client, bucket: str, prefix: str): ...

class LocalDiskStore(ObjectStore):                         # dev only, when s3_bucket unset
    def __init__(self, root: Path): ...

@lru_cache(maxsize=1)
def get_store() -> ObjectStore:                            # StorageService().s3_client + settings
```

`put` is **two passes over the caller's spooled temp file, never a full read into memory**: pass 1 `hashlib.sha256` in 1MB chunks counting bytes, `src.seek(0)`, pass 2 `client.upload_fileobj(src, bucket, full_key, ExtraArgs={"ContentType":…, "ServerSideEncryption":"AES256"})` (boto3 does multipart itself). `_full_key(key) = f"{prefix}/{key}"`; reject `..` and absolute keys.

Key scheme (PROJECT.md:185, now prefixed): `masters/{recording_id}/original.{ext}` · `artwork/{release_id}/cover.{ext}` · `packages/{release_id}/{yyyymmdd-hhmmss}/package.zip` · `renders/{delivery_id}/{track_id}.mp4`. `File.storage_key` stores the un-prefixed key.

`routers/health.py:21` — replace the `storage_root.is_dir()` probe with `get_store().exists("__healthcheck__")` wrapped in try/except (returns False without raising). The `ensure_storage_root()` call added to `server/app/main.py` becomes dead once S3 is the default — drop it then.

**Tests** — `tests/test_storage.py`, `LocalDiskStore` only (no S3 in CI):
`test_put_returns_size_and_sha256` (compare against `hashlib.sha256(data).hexdigest()`) · `test_put_then_open_roundtrip` · `test_key_traversal_rejected` (`../../etc/passwd` → `StorageError`) · `test_overwrite_replaces` · `test_delete_missing_is_noop` · `test_local_copy_yields_readable_path_and_cleans_up`.

### 1d. Phase-1 gaps that block Stage 3 (from `FIXPLAN.md`, still open)

| ID | Change |
|---|---|
| FIX-17 | No UI to create recordings/contributors/works — on a fresh DB you cannot add a track. Inline recording create in `TracksTab.tsx` mirroring the artist inline-create at `CatalogPage.tsx:80-111`. |
| FIX-18 | Metadata form exposes 5 of ~14 fields. Add `c_line`, `p_line`, `territories`, `label_name`, `subgenre`, `original_release_date`, `notes`, `primary_artist_id` — the first three are hard validator errors. |
| FIX-14 | `DELETE /tracks/{id}` leaves position gaps → will trip `T-GAP`. Compact positions server-side in the same transaction (the unique is `DEFERRABLE INITIALLY DEFERRED`, so a single `UPDATE … SET position = position - 1 WHERE position > $deleted` is safe). |
| FIX-24 | `ReleaseArtist` has no endpoint but `manifest.csv` needs `featured_artists`. Add `PUT /releases/{id}/artists` taking `[{artist_id, role, position}]`, replace-all, reusing the `no_duplicates` validator now in `schemas/common.py`. |

**Tests:** `test_delete_track_compacts_positions` (3 tracks, delete #2, assert positions `[1,2]`) · `test_put_release_artists_replace_all` · `test_put_release_artists_duplicate_422`.

---

## Stage 2 — label defaults (the streamlining)

### Migration `server/alembic/versions/oceanlab_app_02_label_defaults.py`

`revision = "oceanlab_app_02"`, `down_revision = "oceanlab_app_01"`. Hand-SQL per `server/app/oceanlab/CLAUDE.md`.

```sql
CREATE TABLE oceanlab_label_settings (
  id                     INTEGER PRIMARY KEY,
  default_artist_id      UUID REFERENCES oceanlab_artists(id) ON DELETE SET NULL,
  default_contributor_id UUID REFERENCES oceanlab_contributors(id) ON DELETE SET NULL,
  default_genre          VARCHAR,
  default_territories    VARCHAR NOT NULL DEFAULT 'WW',
  c_line_template        VARCHAR NOT NULL DEFAULT '{year} {label}',
  p_line_template        VARCHAR NOT NULL DEFAULT '{year} {label}',
  isrc_source            VARCHAR NOT NULL DEFAULT 'distributor',
  upc_source             VARCHAR NOT NULL DEFAULT 'distributor',
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT ck_oceanlab_label_settings_singleton CHECK (id = 1),
  CONSTRAINT ck_oceanlab_label_settings_isrc_source CHECK (isrc_source IN ('own','distributor')),
  CONSTRAINT ck_oceanlab_label_settings_upc_source  CHECK (upc_source  IN ('own','distributor'))
);
INSERT INTO oceanlab_label_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
```
`downgrade()` drops the table. Mirror in `models/settings.py` (`LabelSettings`) + `enums.py` (`CodeSource(StrEnum): own, distributor`). Add the table to `tests/conftest.py:_TRUNCATE_TABLES` **and** re-seed the `id=1` row in the `db_real` teardown, alongside the existing `oceanlab_isrc_config` re-seed at `conftest.py:113`.

### `server/app/oceanlab/services/defaults.py` (new)

```python
def get_label_settings(db: Session) -> LabelSettings          # INSERT … ON CONFLICT DO NOTHING then SELECT (FIX-5 race shape)
def apply_release_defaults(db: Session, data: dict) -> dict   # fills label_name, c_line, p_line, territories, genre, primary_artist_id
def seed_recording_ownership(db: Session, recording: Recording) -> None
    # 1 MasterSplit(contributor=default, share_pct=100)
    # 1 Work(title=recording.title) + RecordingWork + WorkWriter(role=composer_lyricist, share_pct=100)
    # no-op when default_contributor_id is NULL
def render_line(template: str, *, year: int, label: str) -> str   # "{year} {label}" -> "2026 Oceanlab"
```

Wire: `routers/releases.py:create_release` calls `apply_release_defaults` on the payload dict before constructing `Release`; `routers/recordings.py:create_recording` calls `seed_recording_ownership` after `db.flush()`, before commit. Both only fill fields the caller left `None` — an explicit value always wins.

Routes: `GET|PUT /settings/label` (`LabelSettingsRead`/`LabelSettingsUpdate`).

Client: `SettingsPage.tsx` "Label defaults" section; auto-created rows get an `auto` chip in the Splits/Works tabs.

**Tests** — `tests/test_defaults.py`:
`test_create_release_fills_c_line_p_line_territories` · `test_explicit_value_wins_over_default` · `test_create_recording_seeds_100pct_master_split` · `test_create_recording_seeds_work_and_writer` · `test_no_default_contributor_seeds_nothing` · `test_render_line_substitutes_year_and_label` · `test_get_label_settings_concurrent_first_call` (2 threads, exactly one row).

---

## Stage 3 — ingest

### `services/audio_meta.py`

```python
@dataclass(frozen=True)
class AudioMeta:
    duration_seconds: Decimal; sample_rate: int; bit_depth: int | None
    channels: int; audio_format: Literal["wav", "flac"]

class AudioMetaError(Exception): ...        # message is user-facing

ACCEPTED_CODECS = {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "flac"}

def extract(path: Path, *, ffprobe: str = "ffprobe") -> AudioMeta
def _extract_mutagen(path: Path) -> AudioMeta               # fallback when ffprobe absent/unparsable
```
`ffprobe -v error -print_format json -show_streams -show_format`; first audio stream only; duration falls back to `format.duration`.

**Tests** (`tests/test_audio_meta.py`, fixtures generated once by a session-scoped ffmpeg fixture, `skipif` no ffmpeg):
`test_wav_16b_44k_exact_fields` (`sample_rate==44100, bit_depth==16, channels==2, audio_format=="wav"`) · `test_flac_24b_96k` · `test_mp3_renamed_wav_rejected` (asserts `"Not a WAV/FLAC master"` in message) · `test_corrupt_file_raises` · `test_mono_accepted` (`channels==1`) · `test_float32_accepted` (`bit_depth==32`) · `test_duration_from_format_when_stream_lacks_it`.

### `services/artwork.py`

```python
@dataclass(frozen=True)
class ArtworkMeta: width: int; height: int; format: Literal["jpeg", "png"]

class ArtworkError(Exception): ...
MIN_DIM, MAX_DIM, MAX_BYTES = 3000, 6000, 20 * 2**20

def validate_artwork(data: bytes) -> ArtworkMeta
```
`ImageOps.exif_transpose` before measuring. Reject: not JPEG/PNG; mode ∉ {RGB} (CMYK → `"convert to RGB"`, RGBA/P/L rejected); non-square; `<3000`; `>6000`; `>20MB`. Progressive JPEG accepted.

**Tests** (`tests/test_artwork.py`, fixtures built in-memory with Pillow):
`test_3000_square_jpeg_ok` · `test_2999_rejected` · `test_cmyk_rejected_mentions_rgb` · `test_alpha_rejected` · `test_non_square_rejected` · `test_exif_rotated_portrait_passes_after_transpose` · `test_over_6000_rejected` · `test_over_20mb_rejected` · `test_progressive_jpeg_accepted`.

### `services/validation.py`

```python
@dataclass(frozen=True)
class Issue:
    code: str; severity: Literal["error", "warning"]; message: str
    field: str | None = None; track_id: uuid.UUID | None = None

@dataclass(frozen=True)
class ValidationReport:
    packageable: bool; issues: list[Issue]      # packageable = no severity=="error"

def validate_release(db: Session, release_id: uuid.UUID) -> ValidationReport
```
Rule table per PROJECT.md:257-269, **except** `R-UPC` and `A-ISRC`, whose severity is `"error" if settings.upc_source == own else "warning"` (same for `isrc_source`).

**Tests** (`tests/test_validation.py`, reusing `factories.make_release(db, tracks=2, complete=True)`):
`test_complete_release_packageable` (0 errors) · one parametrised case per error code clearing its field and asserting the code appears (`R-TITLE`, `R-DATE`, `R-GENRE`, `R-CLINE`, `R-PLINE`, `R-TERR`, `R-ART-MISSING`, `T-EMPTY`, `A-AUDIO`, `A-EXPLICIT`) · `test_position_gap_yields_T_GAP` · `test_duplicate_recording_yields_T_DUP` · `test_splits_99_9_is_warning_only_still_packageable` · **`test_upc_missing_is_warning_when_source_distributor`** · **`test_upc_missing_is_error_when_source_own`** · same pair for ISRC.

### Jobs on Celery

`server/app/workers/tasks/oceanlab_jobs.py` (new; add `"app.workers.tasks.oceanlab_jobs"` to `celery_app.py`'s `include` list at line 23-64):

```python
JobHandler = Callable[[Session, dict], dict]
JOB_HANDLERS: dict[str, JobHandler] = {}         # "extract_audio_meta" | "build_package" | "run_delivery"

@celery_app.task(name="oceanlab.run_job", bind=True, max_retries=0)
def run_oceanlab_job(self, job_id: str) -> None:
    # own Session via app.oceanlab.db._session_factory()
    # queued -> running (started_at) -> done(result)/failed(error); never re-raises
```
`server/app/oceanlab/services/jobs.py`:
```python
def submit(db: Session, kind: str, payload: dict) -> Job     # commits the row, THEN lazy-imports and .delay(str(job.id))
def sweep_stale(db: Session) -> int                          # running -> failed("server restarted")
```
Row commits before dispatch so the client can always poll. `sweep_stale` runs from the monolith lifespan (same block that currently calls `ensure_storage_root` in `server/app/main.py`).

### Routes

```
POST /recordings/{id}/audio    multipart file -> {"file": FileRead, "job_id": UUID}   # 422 on AudioMetaError
POST /releases/{id}/artwork    multipart file -> FileRead                              # 422 ArtworkError.message
GET  /releases/{id}/validation -> ValidationReport
GET  /jobs/{id}                -> JobRead {status, result, error}
```
Audio upload is store-then-probe: `store.put()` → `File` row → `submit("extract_audio_meta")`; the job does `local_copy` → `extract` → writes `duration_seconds/sample_rate/bit_depth/channels/audio_format` onto the `Recording`. Artwork validates **inline** (bytes are already in memory and small) and writes `width`/`height` onto the `File`.

**Tests** (`tests/test_api_ingest.py`, `monkeypatch` `get_store` to `LocalDiskStore(tmp_path)` and `JOB_HANDLERS["extract_audio_meta"]` run inline):
`test_upload_audio_creates_file_and_job` · `test_upload_audio_populates_recording_meta` · `test_upload_bad_codec_422` · `test_upload_artwork_sets_width_height` · `test_upload_bad_artwork_422_message` · `test_get_job_returns_status`.

### Client

`pages/IngestPage.tsx` wiring the existing `lib/upload.ts:uploadWithProgress`; `useJob(id, {refetchInterval: 1500 until done|failed})`; `components/ValidationPanel.tsx` grouping errors/warnings with a Package CTA enabled iff `packageable`.

---

## Stage 4 — packaging + DistroKid handoff

### `services/packaging.py`

```python
@dataclass(frozen=True)
class PackageResult: file_id: uuid.UUID; manifest_rows: int; total_bytes: int

def build_package(db: Session, release_id: uuid.UUID, delivery_id: uuid.UUID) -> PackageResult
def sanitize_filename(s: str) -> str          # strip /\:*?"<>|, collapse ws, NFC, max 120
def manifest_rows(db: Session, release_id: uuid.UUID) -> list[dict]    # shared with the golden test
```
Zip layout + `manifest.csv` columns exactly PROJECT.md:280-288. `ZIP_STORED`, `shutil.copyfileobj` in 1MB chunks from `store.open()` — **never full-read a master** (768M worker). Zip is built into `tempfile.NamedTemporaryFile`, then `store.put()`.

### Status machine

`POST /releases/{id}/package` → 409 `{"issues": [...]}` when `not packageable`; else `Release.status = packaged`, create `Delivery(target=export_package)`, `submit("build_package")`. Re-introduce a guarded transition (`FIXNOTES.md` F4 deliberately removed `status` from `ReleaseUpdate` — keep it out; transitions happen only here).

`GET /deliveries/{id}/download` → 302 to `store.presigned_url(key)`, or `StreamingResponse` for `LocalDiskStore`.

**Tests** (`tests/test_packaging.py`):
`test_golden_manifest_csv_byte_compare` (frozen-id fixture release vs `tests/fixtures/manifest-golden.csv`) · `test_zip_paths_match_layout` · `test_am_pm_title_sanitized` (`"AM/PM"` → no directory split) · `test_filename_collision_suffixed` (two tracks → `… (2).wav`) · `test_missing_audio_mid_build_fails_with_track_ref` · `test_package_blocked_409_lists_issues` · `test_repackage_creates_new_key_keeps_old_file_row`.

**This is the DSP path**: validated release → zip → drag into DistroKid → Spotify/Apple/Amazon/TikTok.

---

## Stage 5 — YouTube + SoundCloud

### `services/video_render.py`

```python
class RenderError(Exception): ...
def render_track_video(audio: Path, cover: Path, out: Path, *, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> None
```
Exact command PROJECT.md:342-347. Post-render `ffprobe` the output; `RenderError` if duration differs from the master by >1s.

### `services/delivery/base.py`

```python
class DeliveryAdapter(Protocol):
    target: ClassVar[DeliveryTarget]
    def deliver(self, db: Session, delivery: Delivery) -> None    # mutates delivery+items, records errors, raises nothing

ADAPTERS: dict[DeliveryTarget, DeliveryAdapter]
```

### `services/delivery/youtube.py`

```python
@dataclass(frozen=True)
class TrackVideoMeta: title: str; description: str; tags: list[str]; privacy: str; category_id: str

def video_metadata(release, track, recording, settings) -> TrackVideoMeta

class YouTubeAdapter:
    target = DeliveryTarget.youtube
    def deliver(self, db, delivery) -> None
    def _client(self)                                              # AuthError if token missing/revoked
    def _verify_channel(self, yt) -> str
    def _upload_video(self, yt, path: Path, meta: TrackVideoMeta) -> str
    def _create_playlist(self, yt, release) -> str
    def _add_to_playlist(self, yt, playlist_id, video_id, position) -> None
```
Semantics per PROJECT.md:382-384: playlist per release (skipped for a 1-track single), `MediaFileUpload(chunksize=8*2**20, resumable=True)`, `DeliveryItem.external_ref = video_id`, items already `complete` skipped on retry, `403 quotaExceeded` → `"YouTube quota exhausted — retry after midnight PT"`.

`scripts/youtube_auth.py` — one-time installed-app OAuth, scope `https://www.googleapis.com/auth/youtube`. **Store the refresh token in S3 or `.env.backend`, not container disk** (same blue-green reasoning as masters).

### `services/delivery/soundcloud.py`

```python
class SoundCloudAdapter:
    target = DeliveryTarget.soundcloud
    def deliver(self, db, delivery) -> None        # creds unset -> status=manual + instructions in log
    def _upload_track(self, http: httpx.Client, audio: Path, cover: Path, meta: dict) -> str
```
`POST https://api.soundcloud.com/tracks` multipart; 4GB pre-check; 429 → backoff ×3.

### Routes
```
GET  /releases/{id}/deliveries -> DeliveryRead[]           (incl. items)
POST /releases/{id}/deliveries {"target": "youtube"|"soundcloud"} -> {delivery_id, job_id}   # 409 if status ∉ {packaged,delivered,released}
GET  /deliveries/{id}          -> DeliveryRead             (poll; log tail)
POST /deliveries/{id}/retry    -> re-enqueue failed items only
```

**Tests** (`tests/test_delivery_youtube.py`, `googleapiclient` fully mocked):
`test_playlist_created_once_for_multitrack` · `test_single_track_skips_playlist` · `test_insert_called_with_correct_snippet_and_privacy` · `test_quota_exceeded_marks_failed_with_message` · `test_retry_skips_complete_items` · `test_missing_token_fails_with_auth_instructions` · `test_partial_success_keeps_video_ids`.
`tests/test_video_render.py`: `test_command_shape` (subprocess mocked, assert exact argv) · `test_duration_mismatch_raises` · `test_real_2s_tone_render` (`skipif` no ffmpeg).

Optional cheap add: **Audius** as a third `DeliveryTarget` — the one platform with an open upload API and no audit gate. One adapter, no new infra.

---

## Stage 6 — registrations (get YouTube master + pub money flowing)

How YouTube money actually reaches a self-administered label — four pipes, each needing one registration and later producing one statement:

| Pipe | Side | Register via | Statement in |
|---|---|---|---|
| Content ID on other people's uploads + Art Tracks | master | DistroKid "YouTube Money" checkbox (tracked on the `distributor` RegistrationTask) | DistroKid CSV (`Store = "YouTube (Content ID)"` / `"YouTube Ads"` lines) |
| Own-channel AdSense (the videos Stage 5 uploads) | master | YPP on the label channel | YouTube Studio revenue CSV, keyed by **video id** — which we hold in `DeliveryItem.external_ref` |
| Performance royalties (YouTube's PRO blanket license) | publishing | ASCAP/BMI work registration → `pro.py` export | PRO statement CSV (`generic_csv` + column_map) |
| YouTube Music streaming mechanicals | publishing | MLC bulk work registration → `mlc.py` export | MLC statement CSV (`generic_csv` + column_map) |

(SoundExchange is webcast radio, not YouTube — but it's free money on the same rails, so the exporter ships too.)

### Seeding

`routers/releases.py:create_release` — after `db.flush()`, insert 4 `RegistrationTask` rows (one per `RegTarget`, `status=not_started`). `scripts/backfill_registrations.py` does the same `INSERT … ON CONFLICT (release_id, target) DO NOTHING` for existing releases.

### `services/registration_exports/` (new package)

```python
# base.py
class RegistrationExporter(Protocol):
    target: ClassVar[RegTarget]
    filename_template: ClassVar[str]                 # "mlc-bulk-{catalog}.xlsx"
    def generate(self, db: Session, release_id: uuid.UUID) -> tuple[str, bytes]   # (filename, content)

EXPORTERS: dict[RegTarget, RegistrationExporter]     # {mlc, soundexchange, pro}
```
- `mlc.py` (openpyxl) — one row per `Work`: title, ISWC, writers (name, IPI, role, share %), publisher name/share, linked recording ISRCs. Mirrors the MLC bulk-registration template columns.
- `pro.py` — EBR-style CSV (MusicMark-compatible): work title, writers w/ IPI + PRO + share, publisher, ISWC if known.
- `soundexchange.py` — ISRC Ingest sheet: ISRC, track title, artist, album, UPC, ℗-year, label, rights-owner claim % (100).

Generation stores `File(kind=registration_export)`, sets `RegistrationTask.export_file_id`, bumps `not_started → in_progress`. A work with zero writers is excluded and noted in the job result — though Stage 2's `seed_recording_ownership` makes that structurally rare.

### Routes

```
GET   /releases/{id}/registrations        -> RegistrationTaskRead[4]
PATCH /registrations/{id}                 {status?, external_ref?, submitted_at?, confirmed_at?, notes?}
POST  /registrations/{id}/generate-export -> {file_id, filename}          # sync — files are tiny
GET   /registrations?status=&target=      -> cross-release board
GET   /registration-exports/{file_id}/download
```

Client: Registrations tab on `ReleaseDetailPage` (4 target cards: status select, generate + download, external_ref field) + a small cross-release board page.

**Tests** — `tests/test_registration_exports.py`:
`test_release_create_seeds_four_tasks` · `test_mlc_xlsx_headers_and_one_row_per_work_with_writers` (openpyxl round-trip on the generated bytes) · `test_workless_work_excluded` · `test_soundexchange_sheet_has_isrc_upc_claim_pct` · `test_pro_csv_includes_writer_ipi_and_share` · `test_generate_sets_export_file_and_status`.

## Stage 7 — royalty ingestion + matching (see the money per song)

### Migration `oceanlab_app_03_royalty_ingest` (chained off `oceanlab_app_02`)

```sql
ALTER TABLE oceanlab_royalty_lines ADD COLUMN external_id VARCHAR;          -- YouTube video id etc.
CREATE INDEX ix_oceanlab_royalty_lines_external_id ON oceanlab_royalty_lines (external_id);
-- widen the match_method CHECK: isrc|iswc|manual|unmatched -> + external_id
ALTER TABLE oceanlab_royalty_lines DROP CONSTRAINT ck_oceanlab_royalty_lines_match_method;
ALTER TABLE oceanlab_royalty_lines ADD CONSTRAINT ck_oceanlab_royalty_lines_match_method
  CHECK (match_method IN ('isrc','iswc','external_id','manual','unmatched'));
ALTER TABLE oceanlab_royalty_statements ADD COLUMN side VARCHAR NOT NULL DEFAULT 'master'
  CONSTRAINT ck_oceanlab_royalty_statements_side CHECK (side IN ('master','publishing'));
```
(Verify the autogenerated CHECK name against `oceanlab_app_01_standalone.py` before writing — `native_enum=False` names it via the `name="match_method"` kwarg.) Mirror in `models/royalty.py` + `enums.py` (`MatchMethod.external_id`, `StatementSide(StrEnum): master, publishing`).

### `services/royalty_parsers/` (new package)

```python
# base.py
@dataclass(frozen=True)
class ParsedLine:
    raw: dict; isrc: str | None; iswc: str | None; upc: str | None
    external_id: str | None; title_raw: str | None; artist_raw: str | None
    territory: str | None; units: int | None; amount: Decimal; currency: str

class StatementParser(Protocol):
    source: ClassVar[str]
    def parse(self, f: BinaryIO) -> Iterator[ParsedLine]

PARSERS: dict[str, type[StatementParser]]   # {"distrokid", "youtube_channel", "generic_csv"}
```
- `distrokid.py` — real report columns (`Sale Month, Store, Artist, Title, ISRC, UPC, Quantity, Earnings (USD)…`). Handles: UTF-8 BOM (`utf-8-sig`), negative earnings kept (returns net out), `"$1,234.56"` → `Decimal("1234.56")`, blank-ISRC YouTube Ads rows, unknown columns tolerated into `raw`. Malformed row → skip + count in job result, never abort.
- `youtube_channel.py` — YouTube Studio Analytics "Video" export: video id → `external_id`, `Estimated revenue` → amount (USD), `Views` → units. This is the own-channel AdSense pipe; ISRC is absent by design, matching goes through the video id.
- `generic_csv.py` — `column_map` in the job payload (`{"iswc": "ISWC", "amount": "Royalty Amount", …}`) — covers ASCAP/BMI/MLC statements until dedicated parsers earn their keep.

### `services/matching.py`

```python
def normalize_isrc(s: str | None) -> str | None      # strip -/./space, upper, None unless len 12
def normalize_iswc(s: str | None) -> str | None      # strip to T + 10 digits

@dataclass(frozen=True)
class MatchStats: total: int; matched_isrc: int; matched_external_id: int; matched_iswc: int; unmatched: int

def match_statement(db: Session, statement_id: uuid.UUID) -> MatchStats
def match_line_manual(db, line_id, recording_id: uuid.UUID | None, work_id: uuid.UUID | None) -> RoyaltyLine
```
Match order per line: **(1)** ISRC → `Recording` (when the recording has exactly one linked work, also set `work_id` — this is what routes master-statement lines to the pub side automatically); **(2)** `external_id` → `DeliveryItem.external_ref` → `Track.recording_id` (scoped to `Delivery.target == youtube`); **(3)** ISWC → `Work`; else `unmatched`. `rematch` touches only `unmatched` lines (manual matches preserved); `matched_count` recomputed after any change.

### Routes + job

```
POST /royalty-statements    multipart file + form {source, side, period_start, period_end, currency, column_map?}
                            -> {statement_id, job_id}      # parse runs as submit("parse_statement")
GET  /royalty-statements    ;  GET /royalty-statements/{id}?matched=false&limit=&offset=
POST /royalty-lines/{id}/match      {recording_id? | work_id?}     # both null = unmatch
POST /royalty-statements/{id}/rematch  -> MatchStats
GET  /royalties/summary     ?group_by=release|recording|source&side=&from=&to=
                            -> [{key_id, key_name, side, amount, currency, units}]
```
`parse_statement` handler joins the Stage 3 `JOB_HANDLERS` registry; statement `uploaded → parsing → parsed/failed`, then `match_statement` runs in the same job.

Client: `RoyaltiesPage` — statements table + upload dialog (source select, side toggle, period, column-map builder for generic_csv) → statement detail with `MatchTable` (unmatched lines, inline recording/work search) → summary dashboard, master vs publishing split per release (Recharts — **read the `dataviz` skill before writing chart code**).

**Tests** — `tests/test_royalty_parsers.py` + `tests/test_matching.py`:
`test_distrokid_sample_row_count_and_decimal_amounts` · `test_bom_file_parses` · `test_negative_earnings_kept` · `test_dollar_comma_amount_to_decimal` · `test_malformed_row_skipped_not_fatal` · `test_youtube_channel_csv_maps_video_id_to_external_id` · `test_generic_csv_with_column_map` · `test_match_exact_isrc` · `test_match_lowercase_hyphenated_isrc` · `test_match_video_id_via_delivery_item` · `test_isrc_match_sets_work_when_single_linked_work` · `test_unknown_isrc_stays_unmatched_despite_title` · `test_manual_match_survives_rematch` · `test_matched_count_recomputed` · `test_summary_groups_by_release_and_side`.

---

## Verification

1. **Stage 1** — `docker build` then `docker run --rm <img> ffprobe -version`; `pytest app/oceanlab/tests -q` still ≥73 green; upload a WAV, confirm the S3 object exists, redeploy blue-green, confirm it still resolves.
2. **Stage 2** — create a release through the UI with only title/type/artist; assert `c_line`/`p_line`/`territories`/`genre` populated and `MasterSplit` + `Work` + `WorkWriter` all exist at 100%.
3. **Stage 3** — the fixture matrix above; validator green on `make_release(tracks=2, complete=True)` and each cleared field surfacing its own code.
4. **Stage 4** — golden manifest byte-compare, then **actually upload the zip to DistroKid**. That round trip is the only real proof the manifest carries what a distributor needs.
5. **Stage 5** — deliver a 2-track release to a *test* YouTube channel: playlist + both videos with correct titles/description/ISRC, links live in the Deliveries tab. `docker restart matcha-worker` mid-upload, then retry, and confirm only the unfinished track re-uploads.
6. **Stage 6** — create a release, assert 4 registration tasks exist; generate all three exports and open them by hand (MLC xlsx has the work + Finch 100%, PRO CSV has IPI/share, SX sheet has ISRC+UPC+100% claim).
7. **Stage 7** — upload the DistroKid sample CSV → ≥90% auto-match by ISRC; upload a YouTube Studio revenue CSV for a delivered release → lines match via video id with zero manual work; dashboard master/publishing totals reconcile against each statement's own total.
8. **End to end** — one real song: ingest → validate → package → DistroKid + YouTube + SoundCloud, same ISRC visible on all three; registrations board shows MLC/PRO/SX submitted; first real statements ingest and land on the right song.
