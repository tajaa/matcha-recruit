# Cappe AI Booking Suggestions

## Scope

Add natural-language availability requests to the public Cappe booking widget.
The visitor can describe preferred days, times, staff, and ranking preferences;
the system returns up to three live options. The AI request never creates or
reserves a booking. The visitor explicitly selects an option, then the existing
booking endpoint performs the final transactional confirmation.

This feature is enabled wherever the branch is deployed for testing. It must
not be deployed to production until the AWS WAF/CloudFront protection work is
complete.

This feature PR does not add CloudFront, AWS WAF, CAPTCHA, or a persisted
AI-session table.

## Safety Boundaries

- Gemini Flash Lite extracts preferences only.
- Gemini cannot create bookings, set prices, choose unavailable staff, or invent times.
- All returned options come from the existing deterministic live-slot generator.
- Final booking confirmation uses the existing `POST /bookings` transaction and conflict check.
- No suggestion request writes to the database or sends email.
- The request is bounded by body length, honeypot, IP limits, per-site limits, and the global Gemini limiter.
- AWS WAF/CloudFront is required before production exposure.

## API

### Request

`POST /api/cappe/public/sites/{slug}/booking-suggestions`

```json
{
  "booking_type_id": "uuid",
  "location_id": "uuid or null",
  "staff_id": "uuid or null",
  "request": "I can do Tuesday morning or Friday after 2. Is Maria or Jade free? I prefer Maria. Show three options.",
  "website": ""
}
```

`staff_id` is optional. If supplied, it reflects the manual staff selection
already made in the widget. If omitted, the request may name qualified staff.
`website` is a hidden honeypot and must remain empty.

### Response

```json
{
  "timezone": "America/Los_Angeles",
  "options": [
    {
      "staff_id": "uuid",
      "staff_name": "Maria",
      "starts_at": "2026-08-18T10:00:00",
      "ends_at": "2026-08-18T11:00:00",
      "date": "2026-08-18",
      "day_label": "Tue Aug 18",
      "time_label": "10:00 AM",
      "price_cents": 5000
    }
  ],
  "unmatched_staff_names": []
}
```

No matching options returns HTTP 200 with an empty `options` list. The widget
keeps the normal deterministic picker available.

## Files

| Path | Change |
| --- | --- |
| `server/app/cappe/models/bookings.py` | Add request, option, and response models. |
| `server/app/cappe/services/booking_suggestions.py` | Add Flash Lite extraction, coercion, date-window resolution, staff matching, and deterministic ranking. |
| `server/app/cappe/routes/public/bookings.py` | Extract shared live-slot loading and add the suggestion endpoint. |
| `server/app/cappe/services/render/assets/booking.js` | Add the natural-language panel and option selection flow. |
| `server/tests/cappe/test_cappe_booking_suggestions.py` | Add pure parser, date, staff, filtering, and ranking tests. |
| `server/tests/cappe/test_cappe_public_booking_suggestions.py` | Add route, rate-limit, model, no-write, and stale-slot tests. |
| `server/tests/cappe/test_cappe_render_blocks.py` | Verify the rendered widget includes the new panel and endpoint. |

`server/app/cappe/models/cappe.py` already re-exports `models/bookings.py`; no
compatibility shim change is required.

## Models

Add to `server/app/cappe/models/bookings.py`:

```python
class CappeBookingSuggestionRequest(BaseModel):
    booking_type_id: UUID
    location_id: Optional[UUID] = None
    staff_id: Optional[UUID] = None
    request: str = Field(min_length=3, max_length=1200)
    website: str = Field(default="", max_length=200)


class CappeBookingSuggestionOption(BaseModel):
    staff_id: Optional[UUID] = None
    staff_name: Optional[str] = None
    starts_at: datetime
    ends_at: datetime
    date: str
    day_label: str
    time_label: str
    price_cents: int


class CappeBookingSuggestions(BaseModel):
    timezone: str
    options: list[CappeBookingSuggestionOption] = Field(default_factory=list)
    unmatched_staff_names: list[str] = Field(default_factory=list)
```

Export all three names in the module `__all__`.

## Service API

Create `server/app/cappe/services/booking_suggestions.py`.

```python
@dataclass(frozen=True)
class BookingPreference:
    staff_names: tuple[str, ...]
    windows: tuple[BookingAvailabilityWindow, ...]
    requested_count: int


@dataclass(frozen=True)
class BookingAvailabilityWindow:
    weekday: Optional[int]
    relative_week: Optional[Literal["this_week", "next_week"]]
    explicit_date: Optional[date]
    start_time: Optional[time]
    end_time: Optional[time]


async def extract_booking_preference(
    request_text: str,
    *,
    today: date,
) -> Optional[BookingPreference]:
    ...


def coerce_booking_preference(payload: object) -> Optional[BookingPreference]:
    ...


def resolve_booking_windows(
    preference: BookingPreference,
    *,
    today: date,
) -> tuple[ResolvedBookingWindow, ...]:
    ...


def resolve_staff_preferences(
    staff: Sequence[Mapping[str, Any]],
    names: Sequence[str],
) -> tuple[list[UUID], list[str]]:
    ...


def rank_booking_suggestions(
    slots: Sequence[Mapping[str, Any]],
    *,
    staff: Sequence[Mapping[str, Any]],
    preferred_staff_ids: Sequence[UUID],
    resolved_windows: Sequence[ResolvedBookingWindow],
    requested_count: int,
) -> list[dict[str, Any]]:
    ...
```

The exact `ResolvedBookingWindow` type may be private to the module if it is
not useful outside the ranking pipeline.

## Gemini Extraction

`extract_booking_preference()` is the only Gemini call in this flow.

- Use `GEMINI_FLASH_LITE` from `app.core.services.model_catalog`.
- Use `response_mime_type="application/json"`.
- Use minimal thinking and temperature `0.0` or `0.2`.
- Use a 12-second timeout.
- Use a small output cap, no more than 800 tokens.
- Treat the visitor request strictly as untrusted data.
- Extract only staff names, availability windows, and requested result count.
- Never resolve relative dates in Gemini.

Expected model shape:

```json
{
  "staff_names": ["Maria", "Jade"],
  "windows": [
    {
      "weekday": "tuesday",
      "relative_week": "this_week",
      "explicit_date": null,
      "start_time": "10:00",
      "end_time": "14:00"
    }
  ],
  "requested_count": 3
}
```

`coerce_booking_preference()` is the authorization boundary for model output:

- Require an object.
- Clamp `requested_count` to `1..3`.
- Cap staff names and availability windows.
- Accept only valid weekday names, `this_week`, `next_week`, ISO dates, and `HH:MM` times.
- Drop malformed windows.
- Reject or safely ignore unknown fields.
- Return `None` when no actionable preference remains.

## Deterministic Slot Pipeline

1. Validate body size, text length, and honeypot before model or database work.
2. Apply IP limits:
   - `cappe_booking_suggest_min`: 2 requests per minute per IP.
   - `cappe_booking_suggest_hr`: 12 requests per hour per IP.
3. Resolve the published site, active booking type, selected active location,
   and service-qualified active staff.
4. Apply the per-site budget:
   - `cappe_booking_suggest_site_hr`: 60 requests per hour per site.
5. Check `GeminiRateLimiter` with service name
   `cappe_booking_suggestions` and endpoint `parse`.
6. Load live candidates through the same availability, staff, location,
   buffer, booking, rate-rule, discount, and timezone logic as the normal slot endpoint.
7. Release the database connection before the Gemini call.
8. Call Flash Lite. Record the Gemini call in `finally` after an API request was issued.
9. Resolve relative windows from the site-local date:
   - `this_week`
   - `next_week`
   - named weekday
   - explicit ISO date
10. Match staff names case-insensitively only against active staff qualified for
    the selected booking type.
11. Treat unknown or ambiguous names as unmatched. Never guess.
12. Filter candidates so the full service duration fits inside each requested window.
13. Rank named staff in the stated order, then earliest matching time.
14. Return no more than three options.
15. Perform no insert, update, reservation, notification, or email operation.

## Shared Live-Slot Helper

Extract the current slot-loading body from
`public_booking_slots()` into:

```python
async def _load_live_booking_slots(
    conn,
    *,
    site,
    booking_type,
    location_id: UUID | None,
    timezone_name: str,
    days: int,
    staff_id: UUID | None,
) -> list[dict]:
    ...
```

Both `public_booking_slots()` and `public_booking_suggestions()` must use this
helper. The AI flow must not duplicate calendar logic.

## Route

Add to `server/app/cappe/routes/public/bookings.py`:

```python
@router.post(
    "/public/sites/{slug}/booking-suggestions",
    response_model=CappeBookingSuggestions,
)
async def public_booking_suggestions(
    slug: str,
    body: CappeBookingSuggestionRequest,
    request: Request,
):
    ...
```

The route must preserve the existing public route conventions:

- Resolve only published sites.
- Validate location ownership and active status.
- Validate active booking type ownership.
- Reject reserved/test email domains only where an email is collected; this
  endpoint does not collect an email.
- Use `client_ip(request)` for limits.
- Return a stable response shape on no-match and model failure.

## Widget

Modify `server/app/cappe/services/render/assets/booking.js`:

1. Preserve the existing service, location, staff, rider, day-strip, and manual picker.
2. Add a collapsed `Describe what works` panel below staff selection.
3. Require a selected service before enabling the panel.
4. Submit the service, location, optional staff, request text, and empty honeypot.
5. Render one to three options with staff, local date/time, and price.
6. Selecting an AI option sets the existing `sel` and `selStaff` values.
7. Change the final button to `Confirm booking` after AI selection.
8. Submit final confirmation only through the existing `/bookings` endpoint.
9. On a stale option and HTTP 409, show the conflict and reload live slots.
10. If the suggestion request fails or returns no options, leave the manual picker usable.

No external script, iframe, or CSP change is part of this feature PR.

## Tests

### `server/tests/cappe/test_cappe_booking_suggestions.py`

- Reject malformed or non-object model output.
- Clamp `requested_count` to `1..3`.
- Drop invalid times, week tokens, dates, windows, and oversized name lists.
- Resolve `this_week`, `next_week`, named weekdays, and ISO dates from a fixed site-local date.
- Ensure a slot must fit fully inside a stated availability window.
- Return all live slots when no availability window is stated.
- Match `Maria` and `maria` identically.
- Return unknown and ambiguous staff names as unmatched.
- Prefer Maria before Jade.
- Fall back to Jade if Maria has no matching live slot.
- Never return more than three options.
- Preserve legacy unstaffed/shared-calendar behavior.

### `server/tests/cappe/test_cappe_public_booking_suggestions.py`

- Reject a non-empty honeypot before Gemini.
- Enforce both IP limits before Gemini.
- Enforce the per-site budget before Gemini.
- Enforce the global Gemini limiter.
- Ensure the database connection is released before model invocation.
- Return a generic recoverable response on timeout or malformed JSON.
- Assert no booking insert or update occurs.
- Assert returned options are a subset of live generated slots.
- Assert the selected option can be submitted to the existing booking endpoint.
- Assert a stale option returns the existing HTTP 409.

### `server/tests/cappe/test_cappe_render_blocks.py`

- Assert the booking block includes the request textarea.
- Assert it includes the suggestion endpoint call.
- Assert the normal picker and final booking endpoint remain present.

## Local Verification

Use the running `dev-remote.sh` environment and an existing published local
Cappe site such as `lumiere-spa`.

1. Load active booking types and qualified staff.
2. Open the rendered booking widget locally.
3. Submit a request such as:
   `I can do Tuesday morning or Friday after 2. Is Maria or Jade available this week? I prefer Maria. Show three options.`
4. Confirm every option is a live eligible slot.
5. Select one option and complete the existing confirmation flow.
6. Submit the same final booking again and confirm HTTP 409.
7. Delete the temporary local booking.
8. Confirm suggestion requests alone do not change `cappe_bookings`.

## Verification Commands

```bash
cd server
python3 -m pytest \
  tests/cappe/test_cappe_booking_suggestions.py \
  tests/cappe/test_cappe_public_booking_suggestions.py \
  tests/cappe/test_cappe_commerce.py \
  tests/cappe/test_cappe_slots.py \
  tests/cappe/test_cappe_staff_slots.py \
  tests/cappe/test_cappe_render_blocks.py -q
```

```bash
python3 -m py_compile \
  app/cappe/services/booking_suggestions.py \
  app/cappe/routes/public/bookings.py \
  app/cappe/models/bookings.py
```

## Follow-Up Infrastructure PR

The follow-up PR will put `gummfit.com` and `*.gummfit.com` behind CloudFront,
attach AWS WAF, and add AWS-native CAPTCHA/Challenge protection targeted at
`POST /api/cappe/public/sites/*/booking-suggestions`.

The current deployment routes Gummfit directly to EC2 nginx, so AWS WAF cannot
attach until CloudFront or another supported AWS edge/origin layer is added.
