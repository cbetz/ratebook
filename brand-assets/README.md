# Brand assets

Source: `icon.svg`, `logo.svg`. PNGs are rasterized with `rsvg-convert`:

```sh
rsvg-convert -w 256 -h 256 icon.svg -o icon.png
rsvg-convert -w 512 -h 512 icon.svg -o icon@2x.png
rsvg-convert -h 256 logo.svg -o logo.png
rsvg-convert -h 512 logo.svg -o logo@2x.png
```

> These are a **starter** design (lightning-bolt mark in the Ratebook blue). Refine before
> submitting upstream if you want a different look.

## How the icon reaches Home Assistant (in-integration, HA 2026.3+)

`home-assistant/brands` **no longer accepts custom-integration icon PRs** (the bot auto-closes
them — confirmed 2026-06-26). Since HA 2026.3.0, a custom integration ships its own brand images
from a `brand/` folder, which take priority over the brands CDN — no upstream PR, no manifest
change. See https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api.

So the icon lives at `packages/ratebook-homeassistant/custom_components/ratebook/brand/`
(`icon.png` 256×256, `icon@2x.png` 512×512) and is mirrored into the HACS distribution repo by
`scripts/sync_dist_repo.sh`. To change the icon: edit `icon.svg`, re-rasterize (above), copy the
PNGs into that `brand/` folder, then re-sync the dist repo. `logo.svg` is kept for reuse (README,
social) but a wordmark logo isn't required for the in-integration icon.
