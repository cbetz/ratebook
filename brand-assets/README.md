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

## `home-assistant/brands` PR (lists the integration's icon in HA + the HACS scoreboard)

1. Fork [home-assistant/brands](https://github.com/home-assistant/brands).
2. Add under `custom_integrations/ratebook/`:
   - `icon.png` (256×256) and `icon@2x.png` (512×512) — **required**
   - `logo.png` / `logo@2x.png` — optional wordmark (the brands CI may ask you to trim width)
3. The folder name must equal the integration `domain`: **`ratebook`**.
4. Open the PR; brands CI checks dimensions, format, and transparency.

Guidelines: https://github.com/home-assistant/brands#guidelines

Until this merges, the integration still installs and works — the brand icon only affects the
icon Home Assistant shows and the public install scoreboard at analytics.home-assistant.io.
