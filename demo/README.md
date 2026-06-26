# Ratebook browser demo

A self-contained, no-build, no-network demo of the rate engine running **in the browser** —
estimate a monthly bill, and see how time-of-use charging changes the cost. It runs the real
TypeScript engine (`@ratebook/engine`), the same one held byte-for-byte to the Python engine.

Open `demo.html` in a browser (or serve the folder: `python3 -m http.server -d demo 8753` then
visit http://localhost:8753/demo.html).

`ratebook-engine.js` is a bundled build of the TS engine (includes [decimal.js](https://github.com/MikeMcl/decimal.js), MIT).
Regenerate it from source with:

```sh
packages/ratebook-ts/node_modules/.bin/esbuild packages/ratebook-ts/src/index.ts \
  --bundle --format=iife --global-name=RatebookEngine --minify \
  --outfile=demo/ratebook-engine.js
```
