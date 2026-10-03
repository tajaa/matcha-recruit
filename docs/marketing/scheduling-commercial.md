# Scheduling commercial

Configure it at `/admin/landing-media` → **Scheduling commercial**. Upload files,
preview each edit, enable the checkbox, then choose **Save commercial**. The
commercial replaces the illustrative schedule animation on `/scheduling-v2`.
The original `/` and incidents pages retain their existing behavior.

- Desktop: landscape 16:9, ideally 1920×1080.
- Mobile: a separate vertical 9:16 edit, ideally 1080×1920. Below 768 CSS pixels,
  the player selects it; without it, the landscape edit is shown without cropping.
- MP4 with H.264/AAC is recommended; WebM is accepted. MOV is not accepted for
  this player. Limit: 150 MB per film. Export MP4 with the metadata/“fast start”
  at the beginning so playback can start without downloading the entire film.
- Upload matching JPG/PNG/WebP posters (5 MB each), plus English WebVTT captions
  (1 MB) when the film contains speech. The shared caption file assumes the two
  edits have the same timings; burn in captions if the edits use different timing.
- Uploading alone does not enable the commercial. Saves to the legacy media form
  and commercial settings patch separate JSON fields in the existing
  `platform_settings.landing_media` setting. No database migration is needed.

The hero previews silently only while visible; reduced-motion and data-saver
visitors get a still player. “Watch with sound” starts the full film with native
play/pause, volume, seeking, and fullscreen controls. Skip restores the schedule
demo and offers replay. API or playback errors fall back to the schedule demo.
The page remains scrollable throughout.

## Storage prerequisites

The existing public `S3_BUCKET`, its write credentials, and `CLOUDFRONT_DOMAIN`
must be configured. The server signs an exact-key, exact-size S3 POST for 15
minutes. Browser uploads bypass nginx and never send application auth tokens to
S3. Completion and enabled settings are checked with S3 `HeadObject` before the
settings write. Upload keys live under `landing/scheduling-commercial/<slot>/`.
They use unique UUID names, AES256 encryption, and immutable cache headers.
Clearing/replacing a slot removes the reference; it does not delete S3 objects.

Merge the rule in `deploy/s3-cors-scheduling-commercial.json` into the public
bucket's existing CORS configuration; preserve other rules. Add the exact
production/admin origin if it differs from the listed domains. This file is a
configuration proposal and is not automatically applied. S3 needs POST for
uploads and GET/HEAD for anonymous media/caption access. CloudFront must serve
this prefix through the existing S3 origin, support byte-range requests, and
return an `Access-Control-Allow-Origin` response header for captions. Forwarding
S3 CORS responses or a CloudFront response-headers policy can provide it.
Credentials need `s3:PutObject` and `s3:GetObject` on the prefix (HeadObject uses
the latter). No public bucket ACL is needed; use the existing CloudFront origin
access configuration. Upload content is public marketing media.

Deploy the backend and frontend together. Verify a real upload, save, desktop
playback/seeking, vertical phone playback, captions, skip, and the disabled state.
No AWS policy, database setting, or asset is changed by the implementation tests.

References: [S3 signed POST documentation](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/generate_presigned_post.html),
[Browser autoplay behavior](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay).
