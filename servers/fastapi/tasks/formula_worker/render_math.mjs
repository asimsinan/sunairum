#!/usr/bin/env node
/**
 * Render TeX → self-contained SVG paths (MathJax).
 * stdin JSON: { "tex": "...", "display": true, "color": "#0F172A" }
 * stdout: SVG fragment (no XML declaration, no foreignObject/style)
 */
import { mathjax } from "mathjax-full/js/mathjax.js";
import { TeX } from "mathjax-full/js/input/tex.js";
import { SVG } from "mathjax-full/js/output/svg.js";
import { liteAdaptor } from "mathjax-full/js/adaptors/liteAdaptor.js";
import { RegisterHTMLHandler } from "mathjax-full/js/handlers/html.js";
import { AllPackages } from "mathjax-full/js/input/tex/AllPackages.js";

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);

const tex = new TeX({
  packages: AllPackages.filter((p) => p !== "bussproofs"),
});
const svg = new SVG({ fontCache: "local" });
const html = mathjax.document("", { InputJax: tex, OutputJax: svg });

function scrubSvg(raw, color) {
  let out = String(raw || "");
  // Pipeline forbids <style>, class=, foreignObject.
  out = out.replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, "");
  out = out.replace(/\sstyle="[^"]*"/gi, "");
  out = out.replace(/\sclass="[^"]*"/g, "");
  out = out.replace(/\srole="[^"]*"/g, "");
  out = out.replace(/\sfocusable="[^"]*"/g, "");
  out = out.replace(/currentColor/g, color);
  return out;
}

function readSize(svgText) {
  // Prefer explicit ex sizes from MathJax; fall back to viewBox aspect.
  const wm = /width="([-\d.]+)ex"/.exec(svgText);
  const hm = /height="([-\d.]+)ex"/.exec(svgText);
  const ex = 9.6; // ~16px em → 0.6em ex
  let w = wm ? parseFloat(wm[1]) * ex : NaN;
  let h = hm ? parseFloat(hm[1]) * ex : NaN;
  const parts = ((svgText.match(/viewBox="([^"]+)"/) || ["", ""])[1] || "")
    .trim()
    .split(/\s+/);
  const vbW = parts.length === 4 ? parseFloat(parts[2]) : NaN;
  const vbH = parts.length === 4 ? parseFloat(parts[3]) : NaN;
  if ((!Number.isFinite(w) || w <= 0) && Number.isFinite(vbW) && vbW > 0) {
    // MathJax internal units ≈ 1000 per em; em≈16px
    w = (vbW / 1000) * 16;
  }
  if ((!Number.isFinite(h) || h <= 0) && Number.isFinite(vbH) && vbH > 0) {
    h = (vbH / 1000) * 16;
  }
  if (!Number.isFinite(w) || w <= 0) w = 320;
  if (!Number.isFinite(h) || h <= 0) h = 56;
  return {
    w: Math.max(40, Math.min(1100, w)),
    h: Math.max(28, Math.min(220, h)),
    viewBox: parts.length === 4 ? parts.join(" ") : "",
  };
}

async function main() {
  const chunks = [];
  for await (const c of process.stdin) chunks.push(c);
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  let input = {};
  try {
    input = raw ? JSON.parse(raw) : {};
  } catch (err) {
    process.stderr.write(`invalid json: ${err}\n`);
    process.exit(2);
  }
  const texSrc = String(input.tex || "").trim();
  if (!texSrc) {
    process.stderr.write("empty tex\n");
    process.exit(3);
  }
  const display = input.display !== false;
  const color = String(input.color || "#0F172A");

  let node;
  try {
    node = html.convert(texSrc, {
      display,
      em: 16,
      ex: 8,
      containerWidth: 1280,
    });
  } catch (err) {
    process.stderr.write(`mathjax failed: ${err}\n`);
    process.exit(4);
  }

  let fragment = adaptor.innerHTML(node);
  if (!/<svg\b/i.test(fragment)) {
    fragment = adaptor.outerHTML(node);
  }
  // Read size BEFORE rewriting width/height so viewBox stays authoritative.
  const size = readSize(fragment);
  fragment = scrubSvg(fragment, color);
  // Keep MathJax viewBox (glyph coords). Only advertise px width/height for layout.
  if (/\bwidth="/i.test(fragment)) {
    fragment = fragment.replace(/\bwidth="[^"]*"/i, `width="${size.w.toFixed(1)}"`);
  } else {
    fragment = fragment.replace(/<svg\b/i, `<svg width="${size.w.toFixed(1)}"`);
  }
  if (/\bheight="/i.test(fragment)) {
    fragment = fragment.replace(/\bheight="[^"]*"/i, `height="${size.h.toFixed(1)}"`);
  } else {
    fragment = fragment.replace(/<svg\b/i, `<svg height="${size.h.toFixed(1)}"`);
  }
  if (size.viewBox && !/\bviewBox="/i.test(fragment)) {
    fragment = fragment.replace(
      /<svg\b/i,
      `<svg viewBox="${size.viewBox}"`,
    );
  }
  if (!/data-sunairum-formula-math=/.test(fragment)) {
    fragment = fragment.replace(
      /<svg\b/i,
      '<svg data-sunairum-formula-math="1"',
    );
  }
  // Force ink via fill only. A root stroke (even with MathJax stroke-width="0"
  // on inner <g>) can still double-paint glyphs after rsvg rasterization.
  if (!/\bfill="/i.test(fragment.slice(0, 160))) {
    fragment = fragment.replace(
      /<svg\b/i,
      `<svg fill="${color}" stroke="none"`,
    );
  }
  // Neutralize inherited strokes so filled MathJax paths are not outlined again.
  fragment = fragment.replace(/\sstroke="[^"]*"/gi, ' stroke="none"');
  fragment = fragment.replace(/\sstroke-width="[^"]*"/gi, ' stroke-width="0"');
  // Emit layout hint as data attrs (Python reads width/height; viewBox preserved).
  fragment = fragment.replace(
    /<svg\b/i,
    `<svg data-sunairum-math-w="${size.w.toFixed(1)}" data-sunairum-math-h="${size.h.toFixed(1)}"`,
  );
  process.stdout.write(fragment);
}

main().catch((err) => {
  process.stderr.write(String(err) + "\n");
  process.exit(1);
});
