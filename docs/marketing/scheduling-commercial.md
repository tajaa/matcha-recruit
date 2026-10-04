# Scheduling commercial

Configure it at `/admin/landing-media` → **Scheduling commercial**. Upload files,
preview each edit, enable the checkbox, then choose **Save commercial**. The
commercial replaces the home page’s illustrative hero animation at `/`.
`/scheduling-v2` redirects to `/`, preserving query parameters and section links.
The incidents page retains its existing behavior.

- Desktop: landscape 16:9, ideally 1920×1080.
- Mobile: a separate vertical 9:16 edit, ideally 1080×1920. Below 768 CSS pixels,
  the player selects it; without it, the landscape edit is shown without cropping.
- MP4 with H.264/AAC is recommended; WebM is accepted. MOV is not accepted for
  this player. Limit: 150 MB per film. Export MP4 with the metadata/“fast start”
  at the beginning so playback can start without downloading the entire film.
- Upload matching JPG/PNG/WebP posters (5 MB each), plus English WebVTT captions
  (1 MB) when the film contains speech. The shared caption file assumes the two
  edits have the same timings; burn in captions if the edits use different timing.
- The uploader shows the selected filename and size, followed by preparation,
  measured transfer progress, and file verification. A 100% transfer still waits
  for storage confirmation and verification; it is not a published commercial.
- Uploading alone does not enable the commercial. Preview the verified upload,
  enable the checkbox, then save. A failed replacement preserves the previous
  commercial. Settings patch only the commercial JSON field in the existing
  `platform_settings.landing_media` setting. No database migration is needed.
- Retired hero, walkthrough, logo, and testimonial controls are removed from this
  page because the current scheduling/incidents landing pages do not consume
  those fields. Stored legacy settings and backend endpoints are preserved.

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
configuration proposal and is not automatically applied. Review the merged
proposal with `./deploy/configure-scheduling-media-cors.sh PUBLIC_BUCKET`; an
authorized operator can apply it by adding `--apply`. The helper backs up the old
rules, preserves existing entries, and stops on permission or configuration
errors. Only `NoSuchCORSConfiguration` is treated as an empty configuration.
Use an operator identity with `s3:GetBucketCORS` and `s3:PutBucketCORS`; the runtime
application identity does not need those administrative permissions.
S3 needs POST for
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

## Upload troubleshooting

An HTTP 413 from `/api/admin/landing-media/upload` is the retired uploader hitting
the application proxy's request-size limit. Its old 25 MB video allowance also
exceeded the active 20 MB nginx limit. Do not increase the global proxy limit for
commercials: use the direct-to-S3 commercial uploader, which accepts up to 150 MB
per video. 1080p alone does not determine file size; the codec, duration, and
bitrate matter.

If production still shows the retired Hero/Save All controls, compare the SHA in
`/version.json` with the merged release. The frontend and backend both need the
commercial upload changes. A newer frontend with an older backend now shows an
explicit unavailable-server error and disables uploads, instead of attempting
missing endpoints. Browser network/CORS errors during transfer still require the
public bucket's existing CORS rules to allow the admin origin and POST. A missing
GetBucketCORS permission on the application identity prevents an administrative
CORS read; it does not establish whether a browser POST preflight succeeds.
An unauthenticated OPTIONS request with the admin Origin and
`Access-Control-Request-Method: POST` checks that separately. A response saying
`CORS is not enabled for this bucket` requires the public bucket's CORS setup,
even after the frontend and backend are deployed.

References: [S3 signed POST documentation](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/generate_presigned_post.html),
[Browser autoplay behavior](https://developer.mozilla.org/en-US/docs/Web/Media/Guides/Autoplay).
