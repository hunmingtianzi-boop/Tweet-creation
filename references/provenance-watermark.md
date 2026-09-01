# Generated-image provenance watermark

This workflow uses a hidden watermark only as a provenance signal for eligible
workflow-generated raster images. It is not a visible credit line, a reader
fingerprint, or independent proof of copyright ownership.

## V1 scope

V1 applies to final opaque PNG assets whose origin is
`generated-illustrative`, especially calibrated background-family assets and
fully generated raster covers. Keep the unmarked master and create a distinct
article- or organization-specific marked derivative.

V1 never modifies:

- official, user-supplied, photographed, or `documentary-evidence` images;
- logos, QR codes, or QR-safe regions;
- transparent `article-micro` PNGs;
- SVG/SMIL or other interactive source;
- Ardot QA screenshots, interaction-state screenshots, instance inventories,
  node-property evidence, or remote/data-URI assets.

An excluded asset is `not_eligible`; it is not a failed watermark. Do not make
an excluded image eligible by changing its declared origin or evidentiary role.

## Required order

Use this order for every eligible asset:

1. Preserve the approved unmarked master.
2. Run the watermark embedder and write a new final PNG plus public verification
   report. When a raw-ID record is needed, set
   `PROVENANCE_WATERMARK_PRIVATE_ROOT` to an existing directory outside every
   Git repository and write the record beneath it.
   When a normal source such as `1024x1536` exceeds the bounded V1 embed ceiling,
   supply a fresh `--resized-carrier` PNG path. The tool creates one deterministic
   proportional LANCZOS derivative, records original/carrier SHA and dimensions,
   and embeds only that carrier. It never lifts the short edge independently;
   a resize that would fall below eligibility or an extreme aspect source fails.
3. Detect the payload locally and run the fixed full-frame transport simulation
   (`width 390 when larger`, then JPEG quality 75). Do not register the
   derivative unless both results are `payload_authenticated` and the
   visual-quality limits pass.
4. Run the existing background, contrast, size, and format checks on the marked
   pixels.
5. Register the marked derivative. Its final SHA-256 and public report hash are
   the asset identity used by Ardot, the compiler, and the delivery manifest.
6. After WeChat upload, download the actual `mmbiz.qpic.cn` body image or cover
   derivative and run detection again. HTML readback alone is not watermark
   evidence.

## Detection commands

Inject `PROVENANCE_WATERMARK_KEY` from an external secret manager. Its value is
`hex:` or `base64:` encoded key material containing at least 32 random bytes;
never pass it on the command line or save it in Git, Ardot, HTML, or a public
report.

Check the exact local final asset:

```bash
audit_dir="$(mktemp -d)"
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/provenance_watermark.py" detect \
  "/absolute/path/background-final.png" \
  --report "$audit_dir/local-detect.json"
```

After saving the WeChat draft, use the locked publisher readback. It obtains
the exact hosted URL from the authoritative API response, downloads the full
object with the built-in bounded downloader, and runs the same detector. The
formal path does not depend on `curl` and does not accept a hand-entered URL.

For a nonportable current-session API draft, first create the authoritative raw
capture, use the bound Browser/Computer Use route to open the exact draft and
capture each chapter as an actual 390 px PNG, ingest those bytes with
`ingest_wechat_readback_capture.py`, and pass its create-once bundle back to the
publisher:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 capture-raw DRAFT_MEDIA_ID \
  --target-account appid:EXACT_APPID \
  --output "$EXTERNAL_READBACK_ROOT/raw-draft-UNIQUE.json"

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/ingest_wechat_readback_capture.py" \
  HANDOFF_JSON OUTPUT/candidate-report.json \
  "$EXTERNAL_READBACK_ROOT/raw-draft-UNIQUE.json" \
  --runtime-profile "$ORG_WECHAT_SESSION_ROOT/delivery-profile-UNIQUE.json" \
  --runtime-report "$ORG_WECHAT_SESSION_ROOT/delivery-preflight-report-UNIQUE.json" \
  --registry-census "$ORG_WECHAT_SESSION_ROOT/registry-census-UNIQUE.json" \
  --target-account appid:EXACT_APPID --draft-id DRAFT_MEDIA_ID \
  --article-revision 'sha256:EXACT_TRANSPORT_REVISION' \
  --host-session-id CURRENT_HOST_SESSION_ID \
  --capture-tool-id scripts/ingest_wechat_readback_capture.py \
  --observed-url https://mp.weixin.qq.com/cgi-bin/appmsg \
  --nonce FRESH_CURRENT_SESSION_NONCE_AT_LEAST_32_CHARS \
  --chapter-capture CHAPTER_ID /EXTERNAL/chapter.png RFC3339_TIME EVENT_ID \
  --output-dir "$EXTERNAL_READBACK_ROOT/ingested-capture-UNIQUE"

python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 capture-readback \
  HANDOFF_JSON OUTPUT/candidate-report.json DRAFT_MEDIA_ID \
  --target-account appid:EXACT_APPID \
  --output-dir "$EXTERNAL_READBACK_ROOT/readback-UNIQUE" \
  --capture-bundle "$EXTERNAL_READBACK_ROOT/ingested-capture-UNIQUE/capture-bundle.json"
```

Repeat `--chapter-capture` for every chapter. The live browser may use a token
query internally, but that query is never persisted; the ingestor accepts only
a credential-free WeChat URL with no query or fragment. All raw/bundle/readback
destinations are external, symlink-free, parent-precreated, and create-once.
The bundle is explicitly `host_attested=false`, `portable=false`, and
`publication_authority=false`; no signer is needed to finish the draft
readback, and this evidence cannot authorize `freepublish`.

The portable signed route remains separate and uses its host screenshot
manifest instead of `--capture-bundle`:

```bash
python3 -I -S "$ORG_WECHAT_RUNTIME_ROOT/scripts/secure_runner.py" \
  "$ORG_WECHAT_RUNTIME_ROOT/scripts/wechat_publisher.py" \
  --store DELIVERY/publisher.sqlite3 capture-readback \
  HANDOFF_JSON OUTPUT/compile-report.json DRAFT_MEDIA_ID \
  --target-account appid:EXACT_APPID \
  --output-dir "$EXTERNAL_READBACK_ROOT/portable-readback-UNIQUE" \
  --screenshots DELIVERY/portable-signed-wechat-chapter-screenshots.json
```

A successful readback records every eligible carrier as `transport_verified`
in `watermark-carrier-census.json`; its bound detector result contains both
`status: payload_authenticated` and `authenticated: true`. For the local final,
`input_sha256` must equal the embed report's `post_sha256`. WeChat may re-encode
the hosted object, so its byte SHA may differ; compare `algorithm`,
`payload_fingerprint`, `key_epoch`, `version`, and `purpose` with the local embed
evidence before the outer workflow records `transport_verified`.

Exit `1` means `not_detected`: the file may be unmarked, the selected key may be
wrong, or transport may have destroyed the signal. It does not prove the image
was never marked. Exit `2` means an input, key, path, CLI, or format error. The
detector currently accepts complete PNG/JPEG images, not HTML error pages or
WebP. `repeat_vote_agreement` and `mean_abs_margin` are diagnostics, not
probabilities or ownership scores. Ordinary detection must not request
`--private-record`; raw watermark IDs stay in the Git-external private registry.

Never add the first watermark in `compile_wechat.py`: doing so would bypass the
registered asset hash and the Ardot revision evidence. Never overwrite the
unmarked master or stack a new watermark over an already marked derivative.
The image, public report, and private record are create-once outputs: an existing
path or even a broken symlink is a blocking error. Choose a fresh derivative
name instead of silently replacing prior evidence.

## Privacy and key boundary

The embedded payload contains only a scheme version, purpose, key epoch, a
cryptographically random opaque watermark ID, and a truncated HMAC. It must not
contain an organization name, article title, account ID, author, OpenID, reader,
device, or recipient identifier.

Keep the master secret and the private watermark-ID mapping outside Git,
organization packs, article folders, Ardot, generated HTML, and logs. Public
manifests may record only a non-reversible payload fingerprint, key identifier,
scheme, source/final hashes, report hash, and verification status. Use separate
derived embedding and authentication keys. Missing key material is a blocking
error; there is no hard-coded fallback key.

Provision at least 32 random key bytes in a secret manager. The environment
value must use `hex:` or `base64:` encoding; a bare passphrase is rejected.
`key_id` is only a short lowercase hyphenated lookup label (maximum 64
characters), never key material. The symmetric V1 detector key can also mint a
valid payload, so this implementation is an internal provenance control rather
than an independent third-party signature service.

The preserved unmarked master remains locally available for re-derivation but
is ignored by Git under the standard `unwatermarked-masters/` path. Restore it
from the organization's private asset store when moving the pack to another
machine. Do not include it in a public delivery bundle.

## Evidence and states

The public asset evidence uses these states:

- `embedded`: a marked derivative was written;
- `local_verified`: the derivative passed authenticated detection, content-hash
  binding, and local visual QA;
- `transport_verified`: the actual WeChat-hosted derivative passed authenticated
  detection after draft readback;
- `transport_lost`: a locally verified mark was not recoverable after the
  WeChat transport transformation;
- `not_eligible`: the asset is outside V1 scope.

Only `local_verified` may be described as successfully watermarked. It requires
fresh external-key authentication of the current marked bytes, independent
PSNR calculation, strict report-schema validation, and an independently rerun
390 px/JPEG Q75 simulation; a JSON field claiming `authenticated: true` is not
evidence. Only
`transport_verified` may be described as surviving the WeChat delivery path.
`not_detected` never proves that an image was never marked.

For a required policy, failed CDN/cover readback detection blocks publication.
For an `optional` policy, one stronger re-embed profile may be attempted while
remaining within visual-quality limits; a second failure records
`transport_lost` and must be reported rather than silently ignored.

## Quality and robustness

The watermark must live in visible pixel content rather than EXIF, PNG text
chunks, filenames, least-significant bits, transparent RGB, or SVG metadata.
V1 uses a keyed, spatially repeated mid-frequency luminance signal with authenticated payload
recovery. Local marked output must remain visually indistinguishable at the
390 px article viewport and meet at least `PSNR >= 42 dB`. Detection tests cover
an untouched PNG, a metadata-free re-save, JPEG quality 75, a 390 px resize,
their combined full-frame transform, an unmarked negative, and a wrong-key
negative. Every individual derivative must pass the combined simulation before
registration; a carrier that fails is rejected rather than being rescued by a
forged report or excessive strength.

V1 does **not** promise recovery after cropping, adding screenshot borders,
rotation, perspective changes, severe blur, or retaining only part of the
image. It validates the complete hosted body image or complete cover derivative,
not a cropped phone screenshot. Prepare a cover at its final aspect and pixel
geometry before embedding. Actual WeChat CDN and mobile-preview behavior
remains the final transport test.

`authenticated` means only that the compact payload HMAC is valid under the
supplied key. It does not by itself prove authorship, copyright ownership,
publication, or unchanged visual content. Public detection reports bind the
exact input SHA-256, byte length, format, and dimensions. The diagnostic
`repeat_vote_agreement` is not a probability or attribution score.

Inputs are restricted to regular, single-frame files and bounded by format,
byte, pixel, edge, and aspect-ratio limits before full decode. Oversized,
malformed, truncated, animated, FIFO/device, and decompression-bomb inputs fail
closed without a traceback. Embed, PSNR, and transport-simulation carriers must
also be fully opaque; detection may inspect a PNG with Alpha but does not make
that file an eligible V1 carrier.

Do not increase strength past the visual-quality limit merely to make a poor
carrier pass. Keep at least two independently marked eligible carriers in a
normal article when available, such as a cover and a later background.
