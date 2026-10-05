#!/usr/bin/env node
/**
 * Render TeX → MathML via MathJax internal MML tree (SerializedMmlVisitor).
 * stdin JSON: { "tex": "...", "display": true, "color": "#0F172A" }
 * stdout: <math xmlns="...">...</math>
 */
import { mathjax } from "mathjax-full/js/mathjax.js";
import { TeX } from "mathjax-full/js/input/tex.js";
import { liteAdaptor } from "mathjax-full/js/adaptors/liteAdaptor.js";
import { RegisterHTMLHandler } from "mathjax-full/js/handlers/html.js";
import { AllPackages } from "mathjax-full/js/input/tex/AllPackages.js";
import { SerializedMmlVisitor } from "mathjax-full/js/core/MmlTree/SerializedMmlVisitor.js";
import { STATE } from "mathjax-full/js/core/MathItem.js";

const adaptor = liteAdaptor();
RegisterHTMLHandler(adaptor);

const tex = new TeX({
  packages: AllPackages.filter((p) => p !== "bussproofs"),
});
// Input-only document — serialize MML before any SVG/CHTML output.
const html = mathjax.document("", { InputJax: tex });
const visitor = new SerializedMmlVisitor();

function scrubMathml(raw, color, display) {
  let out = String(raw || "").trim();
  const start = out.search(/<math\b/i);
  if (start > 0) out = out.slice(start);
  const end = out.search(/<\/math>/i);
  if (end >= 0) out = out.slice(0, end + "</math>".length);

  if (!/\bxmlns=/.test(out)) {
    out = out.replace(
      /<math\b/i,
      '<math xmlns="http://www.w3.org/1998/Math/MathML"',
    );
  }
  if (display) {
    if (/\bdisplay=/.test(out)) {
      out = out.replace(/\bdisplay="[^"]*"/i, 'display="block"');
    } else {
      out = out.replace(/<math\b/i, '<math display="block"');
    }
  }
  if (color && !/\bmathcolor=/.test(out)) {
    out = out.replace(/<math\b/i, `<math mathcolor="${color}"`);
  }
  if (!/data-sunairum-formula-math=/.test(out)) {
    out = out.replace(/<math\b/i, '<math data-sunairum-formula-math="1"');
  }
  out = out.replace(/<annotation\b[^>]*>[\s\S]*?<\/annotation>/gi, "");
  return out.trim();
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

  let mmlNode;
  try {
    mmlNode = html.convert(texSrc, {
      display,
      end: STATE.CONVERT,
    });
  } catch (err) {
    process.stderr.write(`mathjax failed: ${err}\n`);
    process.exit(4);
  }

  let fragment = "";
  try {
    fragment = visitor.visitTree(mmlNode);
  } catch (err) {
    process.stderr.write(`serialize failed: ${err}\n`);
    process.exit(5);
  }
  fragment = scrubMathml(fragment, color, display);
  if (!/<math\b/i.test(fragment)) {
    process.stderr.write("no mathml emitted\n");
    process.exit(6);
  }
  process.stdout.write(fragment);
}

main().catch((err) => {
  process.stderr.write(String(err) + "\n");
  process.exit(1);
});
