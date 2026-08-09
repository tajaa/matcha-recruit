from enum import StrEnum


class ReleaseType(StrEnum):
    album = "album"
    ep = "ep"
    single = "single"


class ReleaseStatus(StrEnum):
    draft = "draft"
    ready = "ready"
    packaged = "packaged"
    delivered = "delivered"
    released = "released"


class ArtistRole(StrEnum):
    primary = "primary"
    featured = "featured"


class CreditRole(StrEnum):
    producer = "producer"
    performer = "performer"
    mixer = "mixer"
    mastering_engineer = "mastering_engineer"
    recording_engineer = "recording_engineer"
    featured = "featured"
    remixer = "remixer"
    other = "other"


class WriterRole(StrEnum):
    composer = "composer"
    lyricist = "lyricist"
    composer_lyricist = "composer_lyricist"
    arranger = "arranger"
    translator = "translator"


class FileKind(StrEnum):
    audio_master = "audio_master"
    artwork = "artwork"
    royalty_statement = "royalty_statement"
    package = "package"
    registration_export = "registration_export"
    rendered_video = "rendered_video"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class RegTarget(StrEnum):
    pro = "pro"
    mlc = "mlc"
    soundexchange = "soundexchange"
    distributor = "distributor"


class RegStatus(StrEnum):
    not_started = "not_started"
    in_progress = "in_progress"
    submitted = "submitted"
    confirmed = "confirmed"
    not_applicable = "not_applicable"


class DeliveryTarget(StrEnum):
    export_package = "export_package"
    youtube = "youtube"
    soundcloud = "soundcloud"


class DeliveryStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    complete = "complete"
    failed = "failed"
    manual = "manual"


class StatementStatus(StrEnum):
    uploaded = "uploaded"
    parsing = "parsing"
    parsed = "parsed"
    failed = "failed"


class MatchMethod(StrEnum):
    isrc = "isrc"
    iswc = "iswc"
    manual = "manual"
    unmatched = "unmatched"


class UpcStatus(StrEnum):
    available = "available"
    assigned = "assigned"


class CodeSource(StrEnum):
    """Who issues our ISRCs/UPCs. Drives validator severity, not just display:
    distributor-issued codes arrive after delivery, so their absence at
    packaging time is a warning; label-owned codes must be present up front."""

    own = "own"
    distributor = "distributor"
