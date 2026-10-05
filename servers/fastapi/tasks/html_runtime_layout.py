"""Runtime geometry inspection for DeckHTML slides.

CSS flex/grid and font wrapping can only be trusted after Chromium has resolved
the page. This module returns measurements and never rewrites a slide. Runtime
unavailability is a hard failure in the Scene-v2 pipeline.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


_INSPECTION_SCRIPT = r"""
(settings) => {
  const root = document.querySelector('.slide') || document.body.firstElementChild;
  if (!root) return {available: false, error: 'slide_root_missing'};

  const rootRect = root.getBoundingClientRect();
  const css = (el, pseudo) => window.getComputedStyle(el, pseudo || null);
  const num = (value) => Number.parseFloat(value || '0') || 0;
  /**
   * True when this element's line-height positions its text rather than pacing
   * it — a numbered badge, a chip, an icon well: one line inside a box whose
   * height it does not determine.
   *
   * For a single line, line-height buys no vertical room: shrinking it only
   * slides the glyphs up inside a box that did not change. That is what lifted
   * every "01" off the centre of its 28px circle. Only a block of two or more
   * lines gets shorter when its line-height does, so only there is scaling it
   * part of the fix. Declared-vs-used height cannot be read from computed
   * style (`auto` resolves to px), so the line count is the signal.
   */
  const centersTextWithLineHeight = (node, style) => {
    if (!node || !style) return false;
    if (num(style.lineHeight) <= 0) return false;
    if (!String(node.textContent || '').trim()) return false;
    try {
      const range = document.createRange();
      range.selectNodeContents(node);
      const lines = [...range.getClientRects()].filter(
        (rect) => rect.width > 0.5 && rect.height > 0.5,
      );
      // Client rects split per inline box, so collapse them onto their rows.
      const rows = new Set(lines.map((rect) => Math.round(rect.top)));
      return rows.size <= 1;
    } catch {
      return false;
    }
  };
  // Must agree with the exporter's own visibility gate (deckhtml treats
  // opacity <= 0.01 as hidden). When the two disagree, an element the PPTX drops
  // still generates collision findings here, and the repair loop burns its whole
  // pass budget chasing a conflict that no reader will ever see.
  const HIDDEN_OPACITY = 0.01;
  const isVisible = (el) => {
    const style = css(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden'
      && num(style.opacity) > HIDDEN_OPACITY && rect.width > 0.5 && rect.height > 0.5;
  };
  const isDecorative = (el) => Boolean(el.closest('[aria-hidden="true"], [data-pptx-kind="ignore"]'));
  const hasRole = (el) => {
    if (el.hasAttribute('data-layout-role') || el.hasAttribute('data-pptx')
        || el.hasAttribute('data-sunairum-component')) return true;
    const tokens = String(el.className || '').trim().split(/\s+/).filter(Boolean);
    return tokens.some((token) => /(?:card|panel|callout|figure|host|lede|title|caption|footer|takeaway|band|stage|claim|caveat|largest|ranges|vector|column|flow|note|shell|spine|connector|chart|plot|axis|bar|legend|metric|label|table|role|scope|mechanism|intervention|baseline|separator|rail|loop)/i.test(token));
  };
  const isComponent = (el) => {
    if (el.parentElement === root || hasRole(el)) return true;
    // Semantic hosts own their internal table/formula/image DOM. Measuring
    // every injected cell as an authored component creates meaningless peers.
    if (el.closest('[data-pptx]')) return false;
    if (/^(?:H1|H2|H3|H4|H5|H6|P|UL|OL|LI|BLOCKQUOTE|FIGCAPTION)$/.test(el.tagName)) return true;
    // A class-name vocabulary cannot keep up with freely authored markup: the
    // author names its own classes, so coverage became a lottery. A card called
    // ".insight" matched nothing in the list, was never measured, and shipped
    // with its copy overflowing the coloured panel it sat in. Qualify on what an
    // element *is* instead — a box that carries its own text, or paints its own
    // surface — so every authored component is measured whatever it is called.
    const rect = el.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8) return false;
    const style = css(el);
    // An inline run is part of its parent's text flow, not a box of its own. Its
    // ink rectangle is the union of every line fragment it spans, so a wrapped
    // <strong> and the <span> after it in the same sentence always appear to
    // overlap. They are the same paragraph; there is nothing to repair.
    if (style.display === 'inline') return false;
    const ownsText = [...el.childNodes].some(
      (node) => node.nodeType === 3 && String(node.textContent || '').trim()
    );
    if (ownsText) return true;
    return painted(el, style) && rect.width >= 24 && rect.height >= 16;
  };
  const localRect = (rect) => ({
    left: +(rect.left - rootRect.left).toFixed(2),
    top: +(rect.top - rootRect.top).toFixed(2),
    width: +rect.width.toFixed(2),
    height: +rect.height.toFixed(2),
    right: +(rect.right - rootRect.left).toFixed(2),
    bottom: +(rect.bottom - rootRect.top).toFixed(2),
  });
  const rectIntersects = (a, b) => (
    Math.min(a.right, b.right) - Math.max(a.left, b.left) > settings.overlapEpsilon
    && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > settings.overlapEpsilon
  );
  const intersection = (a, b) => ({
    width: +Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)).toFixed(2),
    height: +Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)).toFixed(2),
  });
  // The ink a text element actually paints, which is usually far narrower than
  // its border box: a full-width block whose sentence ends mid-line does not
  // collide with a right-aligned annotation sharing that row, even though the
  // two boxes overlap by hundreds of pixels. Comparing boxes reports overlaps a
  // reader cannot see and sends the repair loop chasing them.
  // Computed once, bottom-up, for the whole tree. Walking every element's whole
  // subtree on demand re-measures the same text once per ancestor and forces a
  // synchronous layout flush on every getClientRects() call — quadratic, and on
  // a dense slide it cost minutes per audit. Each element's ink is its own text
  // plus the union of its children's, so one pass in reverse document order
  // (children before parents) is enough.
  const inkByElement = new Map();
  {
    const everything = [...root.querySelectorAll('*')];
    for (let index = everything.length - 1; index >= 0; index -= 1) {
      const el = everything[index];
      let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
      const merge = (box) => {
        if (!box) return;
        left = Math.min(left, box.left); top = Math.min(top, box.top);
        right = Math.max(right, box.right); bottom = Math.max(bottom, box.bottom);
      };
      for (const node of el.childNodes) {
        if (node.nodeType === 3) {
          if (!String(node.nodeValue || '').trim()) continue;
          const range = document.createRange();
          range.selectNodeContents(node);
          for (const box of range.getClientRects()) {
            if (box.width < 0.5 || box.height < 0.5) continue;
            merge(box);
          }
        } else if (node.nodeType === 1) {
          merge(inkByElement.get(node));
        }
      }
      inkByElement.set(el, Number.isFinite(left) ? {left, top, right, bottom} : null);
    }
  }
  const inkRectFor = (el) => {
    const raw = inkByElement.get(el);
    if (!raw) return null;
    return localRect({
      left: raw.left, top: raw.top, right: raw.right, bottom: raw.bottom,
      width: raw.right - raw.left, height: raw.bottom - raw.top,
    });
  };
  // The box a repair is allowed to move an element inside of.
  //
  // A scene region is not a containment boundary: it holds several cards, so a
  // scene-scoped search happily relocates a card's own ordinal numeral or label
  // 40px upward, into the card above it. To a reader that is not a fixed
  // collision, it is a number attached to the wrong thing. An element's real
  // boundary is its offsetParent — the box its top/left actually resolve
  // against — narrowed to the scene it belongs to.
  // Viewport-space form, for the passes that compare raw getClientRects().
  const viewportContainmentBoxFor = (el, sceneNode) => {
    const sceneBox = sceneNode.getBoundingClientRect();
    const owner = el.offsetParent;
    if (!owner || owner === sceneNode || !sceneNode.contains(owner)) return sceneBox;
    const ownerBox = owner.getBoundingClientRect();
    const left = Math.max(sceneBox.left, ownerBox.left);
    const top = Math.max(sceneBox.top, ownerBox.top);
    const right = Math.min(sceneBox.right, ownerBox.right);
    const bottom = Math.min(sceneBox.bottom, ownerBox.bottom);
    if (right - left < 4 || bottom - top < 4) return sceneBox;
    return {left, top, right, bottom, width: right - left, height: bottom - top};
  };
  const containmentBoxFor = (el, sceneNode) => {
    const sceneBox = localRect(sceneNode.getBoundingClientRect());
    const owner = el.offsetParent;
    if (!owner || owner === sceneNode || !sceneNode.contains(owner)) return sceneBox;
    const ownerBox = localRect(owner.getBoundingClientRect());
    const left = Math.max(sceneBox.left, ownerBox.left);
    const top = Math.max(sceneBox.top, ownerBox.top);
    const right = Math.min(sceneBox.right, ownerBox.right);
    const bottom = Math.min(sceneBox.bottom, ownerBox.bottom);
    // A degenerate intersection means the owner is itself misplaced; repairing
    // the child against an empty box would be arbitrary, so keep the scene.
    if (right - left < 4 || bottom - top < 4) return sceneBox;
    return {left, top, right, bottom, width: +(right - left).toFixed(2), height: +(bottom - top).toFixed(2)};
  };
  // An absolutely positioned child whose ink has left the card it belongs to.
  // A reader does not see "a resolved overlap", they see an ordinal numeral or
  // label attached to the wrong card. This is the direct detector for that, and
  // it also catches a repair pass that pushed an element out to buy clearance.
  const escapedOwner = (el, rect) => {
    const style = css(el);
    if (style.position !== 'absolute' && style.position !== 'fixed') return null;
    const owner = el.offsetParent;
    if (!owner || owner === root || !root.contains(owner)) return null;
    // A Scene region is an abstract lane, and deliberately overrun by badges.
    if (owner.hasAttribute('data-layout-id')) return null;
    // Only a box the audience can tell apart from its surroundings reads as an
    // owner; a bare positioning wrapper has no visible edge to escape from.
    if (!painted(owner, css(owner))) return null;
    const box = owner.getBoundingClientRect();
    const out = {
      top: +Math.max(0, box.top - rect.top).toFixed(2),
      bottom: +Math.max(0, rect.bottom - box.bottom).toFixed(2),
      left: +Math.max(0, box.left - rect.left).toFixed(2),
      right: +Math.max(0, rect.right - box.right).toFixed(2),
    };
    const worst = Math.max(out.top, out.bottom, out.left, out.right);
    // Small overhangs are a deliberate design move (a numeral straddling a card
    // edge). Leaving the owner by more than half the element's own size is not.
    const budget = Math.max(6, Math.min(rect.height, rect.width) * 0.5);
    if (worst <= budget) return null;
    // An owner smaller than the element is an anchor, not a container. A
    // caption set over a 42px connector arrow is positioned *from* the arrow
    // and is wider and taller than it; "pulling it back inside" names a box
    // that could never hold it, which is why the repair below already declines
    // to suggest an offset in this case. Reporting it anyway produced a hard
    // finding nothing could ever clear, and a deck that could not ship.
    // Whether the label leaves its region or lands on other ink are the real
    // questions, and both are measured by their own checks.
    const escapedX = out.left > 0 || out.right > 0;
    const escapedY = out.top > 0 || out.bottom > 0;
    const unfittableX = rect.width > box.width;
    const unfittableY = rect.height > box.height;
    if (
      (!escapedX || unfittableX) && (!escapedY || unfittableY)
      && (unfittableX || unfittableY)
    ) return null;
    // Pull it back inside along whichever axis it escaped, keeping the author's
    // intended corner: an element anchored near the bottom stays near the bottom.
    const currentTop = style.top === 'auto' ? null : num(style.top);
    const currentLeft = style.left === 'auto' ? null : num(style.left);
    let suggestedTop = null;
    if (currentTop !== null && rect.height <= box.height) {
      if (out.top > 0) suggestedTop = +(currentTop + out.top).toFixed(2);
      else if (out.bottom > 0) suggestedTop = +(currentTop - out.bottom).toFixed(2);
    }
    let suggestedLeft = null;
    if (currentLeft !== null && rect.width <= box.width) {
      if (out.left > 0) suggestedLeft = +(currentLeft + out.left).toFixed(2);
      else if (out.right > 0) suggestedLeft = +(currentLeft - out.right).toFixed(2);
    }
    return {
      ...out,
      worst: +worst.toFixed(2),
      ownerSelector: repairSelectorFor(owner),
      targetSelector: repairSelectorFor(el),
      sceneOwner: String(el.closest('[data-layout-id^="scene-"]')?.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
      strategy: (suggestedTop === null && suggestedLeft === null) ? 'manual' : 'set_absolute_top',
      suggestedTop,
      suggestedLeft,
    };
  };
  // The block box a run of text flows inside. Two inline runs that share one are
  // the same paragraph: <strong> followed by <span> in one sentence is not two
  // objects colliding, however their wrapped ink rectangles overlap.
  const nearestBlock = (el) => {
    let node = el;
    while (node && node !== root) {
      const display = css(node).display;
      if (display && display !== 'inline' && display !== 'contents') return node;
      node = node.parentElement;
    }
    return root;
  };
  const componentParent = (el) => {
    let node = el.parentElement;
    while (node && node !== root) {
      if (isComponent(node)) return node;
      node = node.parentElement;
    }
    return root;
  };
  const idFor = (el, index) => {
    if (el.id) return `#${el.id}`;
    const key = el.getAttribute('data-layout-id') || el.getAttribute('data-sunairum-component')
      || el.getAttribute('data-pptx') || el.getAttribute('data-layout-role');
    if (key) return `${el.tagName.toLowerCase()}[${key}]`;
    return `${el.tagName.toLowerCase()}.${String(el.className || '').trim().split(/\s+/).filter(Boolean).slice(0, 2).join('.') || 'node'}:${index}`;
  };
  const repairSelectorFor = (el) => {
    if (el.hasAttribute('data-layout-id')) return `[data-layout-id="${CSS.escape(el.getAttribute('data-layout-id'))}"]`;
    if (el.id) return `#${CSS.escape(el.id)}`;
    const sceneRoot = el.closest('[data-layout-id^="scene-"]');
    const segments = [];
    let node = el;
    while (node && node !== sceneRoot && node !== root) {
      const classes = String(node.className || '').trim().split(/\s+/)
        .filter((x) => /^[A-Za-z_-][A-Za-z0-9_-]*$/.test(x)).slice(0, 3);
      let segment = `${node.tagName.toLowerCase()}${classes.map((name) => `.${CSS.escape(name)}`).join('')}`;
      const parent = node.parentElement;
      if (parent) {
        const peers = [...parent.children].filter((peer) => {
          if (peer.tagName !== node.tagName) return false;
          const peerClasses = String(peer.className || '').trim().split(/\s+/).filter(Boolean);
          return classes.every((name) => peerClasses.includes(name));
        });
        if (peers.length > 1) segment += `:nth-child(${[...parent.children].indexOf(node) + 1})`;
      }
      segments.unshift(segment);
      node = parent;
    }
    return segments.join(' > ') || el.tagName.toLowerCase();
  };
  const gridAncestorFor = (el) => {
    let node = el;
    while (node && node !== root) {
      const style = css(node);
      if (style.display === 'grid') {
        const tracks = String(style.gridTemplateColumns || '').trim().split(/\s+/).filter(Boolean);
        if (tracks.length > 1) {
          const children = [...node.children];
          // A grid container's ::before / ::after generate real grid items, and
          // `children` does not list them. A bullet row written as
          // `grid-template-columns: 24px 1fr` with the dot as ::before then
          // measured as a one-child grid, which collapsed it to a single track
          // and auto-placed the text into an implicit column -- the dot took the
          // 1fr and the sentence got the remainder. Count the generated boxes.
          const generated = ['::before', '::after'].filter((pseudo) => {
            const pseudoStyle = css(node, pseudo);
            if (!pseudoStyle) return false;
            const content = String(pseudoStyle.content || 'none');
            return content !== 'none' && content !== 'normal'
              && pseudoStyle.display !== 'none';
          });
          const leadingGenerated = generated.includes('::before') ? 1 : 0;
          const itemCount = children.length + generated.length;
          const childIndex = children.findIndex((child) => child === el || child.contains(el));
          const directIndex = childIndex < 0 ? -1 : childIndex + leadingGenerated;
          const lengths = children.map((child) => String(child.textContent || '').trim().length);
          if (itemCount === 1) return {node, strategy: 'collapse_empty_track'};
          if (
            leadingGenerated === 0 && directIndex === 0
            && lengths[0] > 24 && lengths[1] > 0 && lengths[0] > lengths[1] * 2
          ) {
            return {node, strategy: 'swap_first_two'};
          }
          // The obvious strategy was missing: widen the starved track. A
          // caption wrapping into 12-character lines sat in a 110px column
          // beside a 376px one, and neither rule above applies — so the
          // finding had a region, an owner and no possible repair. Move a
          // bounded share of the widest sibling's width across; the repair loop
          // only keeps the result if the deck measures better afterwards.
          if (directIndex >= 0 && itemCount >= 2) {
            // Track widths, not child widths: the used values in
            // gridTemplateColumns cover generated items too, and a child's own
            // box can be narrower than the track that holds it.
            const widths = tracks.map((track) => num(track));
            if (widths.some((width) => !Number.isFinite(width) || width <= 0)) {
              node = node.parentElement;
              continue;
            }
            const own = widths[directIndex] || 0;
            let widestIndex = -1;
            let widest = 0;
            widths.forEach((width, index) => {
              if (index !== directIndex && width > widest) {
                widest = width;
                widestIndex = index;
              }
            });
            if (own > 0 && widest >= own * 1.5) {
              return {
                node,
                strategy: 'widen_narrow_track',
                narrowIndex: directIndex,
                donorIndex: widestIndex,
                widths: widths.map((width) => +width.toFixed(2)),
              };
            }
          }
        }
      }
      node = node.parentElement;
    }
    return null;
  };
  /**
   * True when the element paints a surface a reader cannot see through, so
   * anything it covers is hidden rather than merely crossed. Near-opaque counts:
   * text under a 0.94-alpha sheet is not legible either.
   */
  const opaqueSurface = (el, style) => {
    if (['IMG', 'SVG', 'CANVAS', 'VIDEO'].includes(el.tagName)) return true;
    if (num(style.opacity || '1') < 0.9) return false;
    const image = String(style.backgroundImage || 'none');
    if (image !== 'none' && !/gradient/i.test(image)) return true;
    const match = String(style.backgroundColor || '').match(
      /rgba?\(\s*[\d.]+[,\s]+[\d.]+[,\s]+[\d.]+(?:[,\s/]+([\d.]+))?/
    );
    if (!match) return false;
    const alpha = match[1] === undefined ? 1 : Number.parseFloat(match[1]);
    return Number.isFinite(alpha) && alpha >= 0.9;
  };
  const painted = (el, style) => {
    if (['IMG', 'SVG', 'CANVAS', 'VIDEO', 'TABLE'].includes(el.tagName)) return true;
    return style.backgroundColor !== 'rgba(0, 0, 0, 0)'
      && style.backgroundColor !== 'transparent'
      || style.backgroundImage !== 'none'
      || num(style.borderTopWidth) > 0 || num(style.borderRightWidth) > 0
      || style.boxShadow !== 'none';
  };
  const clippedByAncestor = (el, rect) => {
    let node = el.parentElement;
    while (node) {
      const style = css(node);
      if (/(hidden|clip|scroll|auto)/.test(`${style.overflow} ${style.overflowX} ${style.overflowY}`)) {
        const box = node.getBoundingClientRect();
        if (rect.left < box.left - 0.5 || rect.right > box.right + 0.5
            || rect.top < box.top - 0.5 || rect.bottom > box.bottom + 0.5) return true;
      }
      if (node === root) break;
      node = node.parentElement;
    }
    return false;
  };
  const authoredContentOverflow = (el, rect) => {
    let x = 0;
    let y = 0;
    const targets = new Map();
    const remember = (node, box) => {
      const ox = Math.max(0, rect.left - box.left, box.right - rect.right);
      const oy = Math.max(0, rect.top - box.top, box.bottom - rect.bottom);
      if (ox <= 4 && oy <= 4) return;
      const style = css(node);
      targets.set(repairSelectorFor(node), {
        selector: repairSelectorFor(node),
        overflowX: +ox.toFixed(2), overflowY: +oy.toFixed(2),
        fontSize: num(style.fontSize), lineHeight: num(style.lineHeight),
        // Tracking is a ratio to the em, so a font-size repair has to carry it
        // along. A display number authored at 104px with letter-spacing:-5px
        // was shrunk to 14px with the -5px intact, which printed its two
        // digits on top of each other.
        letterSpacing: num(style.letterSpacing),
        // A fixed-size badge centres its glyphs by setting line-height equal to
        // its own content box — that is what makes "01" sit in the middle of a
        // 28px circle. Scaling that line-height with the font (correct for
        // flowing copy, where it is the pitch) moved every number to the top of
        // its circle, so the repair has to know which job it is doing.
        centersWithLineHeight: centersTextWithLineHeight(node, style),
        // Padding is the cheapest room on the slide: giving some back changes
        // no glyph, where shrinking type changes every one of them.
        paddingTop: num(style.paddingTop), paddingBottom: num(style.paddingBottom),
        position: style.position, top: num(style.top), left: num(style.left),
        width: +box.width.toFixed(2), height: +box.height.toFixed(2),
        outsidePlate: box.left < rootRect.left - 0.5 || box.top < rootRect.top - 0.5
          || box.right > rootRect.right + 0.5 || box.bottom > rootRect.bottom + 0.5,
      });
    };
    const descendants = [...el.querySelectorAll('*')].filter((node) =>
      isVisible(node) && !isDecorative(node)
      && !['SCRIPT', 'STYLE', 'META', 'LINK'].includes(node.tagName));
    for (const node of descendants) {
      const box = node.getBoundingClientRect();
      x = Math.max(x, rect.left - box.left, box.right - rect.right);
      y = Math.max(y, rect.top - box.top, box.bottom - rect.bottom);
      remember(node, box);
    }
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let textNode;
    while ((textNode = walker.nextNode())) {
      const parent = textNode.parentElement;
      if (!parent || isDecorative(parent) || !(textNode.nodeValue || '').trim()) continue;
      const range = document.createRange();
      range.selectNodeContents(textNode);
      for (const box of range.getClientRects()) {
        x = Math.max(x, rect.left - box.left, box.right - rect.right);
        y = Math.max(y, rect.top - box.top, box.bottom - rect.bottom);
        remember(parent, box);
      }
    }
    return {x: Math.max(0, +x.toFixed(2)), y: Math.max(0, +y.toFixed(2)), targets: [...targets.values()].slice(0, 8)};
  };
  const unquoteContent = (raw) => {
    const value = String(raw || '').trim();
    if (!value || value === 'none' || value === 'normal' || value === '""') return '';
    return value.replace(/^['"]|['"]$/g, '').replace(/\\A\s?/gi, ' ');
  };
  const opaqueBackground = (value) => {
    const token = String(value || '').trim().toLowerCase();
    if (!token || token === 'transparent' || token === 'rgba(0, 0, 0, 0)') return false;
    const alpha = token.match(/^rgba\([^,]+,[^,]+,[^,]+,\s*([\d.]+)\)$/);
    return !alpha || Number(alpha[1]) > 0.08;
  };
  // A list marker drawn as a painted ::before lives *inside* its element's
  // left padding. Tightening that padding as ordinary spacing walks the marker
  // into the first character of the copy — the bullet ends up printed over the
  // text. Report the gutter each marker needs so repair can shrink everything
  // else and leave this floor alone.
  const markerReserveFor = (node) => {
    let left = 0;
    let top = 0;
    for (const pseudo of ['::before', '::after']) {
      const style = window.getComputedStyle(node, pseudo);
      if (style.content === 'none' || style.display === 'none' || style.visibility === 'hidden') continue;
      if (style.position !== 'absolute') continue;
      const paints = opaqueBackground(style.backgroundColor)
        || style.backgroundImage !== 'none'
        || num(style.borderLeftWidth) > 0
        || Boolean(unquoteContent(style.content));
      if (!paints) continue;
      const width = num(style.width) + num(style.borderLeftWidth) + num(style.borderRightWidth)
        + num(style.paddingLeft) + num(style.paddingRight);
      const height = num(style.height) + num(style.borderTopWidth) + num(style.borderBottomWidth)
        + num(style.paddingTop) + num(style.paddingBottom);
      // Only a small shape anchored at the very start of the line is a bullet.
      // A large ornament, or one parked far into the box, is decoration that sits
      // behind the copy — reserving a gutter for it would push the text right off
      // its own card.
      const anchoredLeft = style.left !== 'auto' && num(style.left) <= 48;
      if (anchoredLeft && width > 0 && width <= 32) {
        left = Math.max(left, num(style.left) + width);
      }
      if (style.top !== 'auto' && height > 0 && height <= 32 && style.left === 'auto'
          && num(style.top) <= 48) {
        top = Math.max(top, num(style.top) + height);
      }
    }
    return {left: +left.toFixed(2), top: +top.toFixed(2)};
  };
  const layoutCandidatesFor = (el) => {
    const found = new Map();
    for (const node of [el, ...el.querySelectorAll('*')]) {
      if (!isVisible(node) || isDecorative(node)) continue;
      const style = css(node);
      if (node !== el && (style.position === 'absolute' || style.position === 'fixed')) continue;
      const reserve = markerReserveFor(node);
      const metrics = {
        paddingTop: num(style.paddingTop), paddingRight: num(style.paddingRight),
        paddingBottom: num(style.paddingBottom), paddingLeft: num(style.paddingLeft),
        marginTop: num(style.marginTop), marginBottom: num(style.marginBottom),
        rowGap: num(style.rowGap), columnGap: num(style.columnGap),
        minHeight: num(style.minHeight),
        reservePaddingLeft: reserve.left, reservePaddingTop: reserve.top,
      };
      if (Math.max(...Object.values(metrics)) < 6) continue;
      const selector = repairSelectorFor(node);
      const current = found.get(selector);
      if (!current || Object.values(metrics).reduce((a, b) => a + b, 0)
          > Object.values(current).filter((v) => typeof v === 'number').reduce((a, b) => a + b, 0)) {
        found.set(selector, {selector, ...metrics});
      }
    }
    return [...found.values()].slice(0, 40);
  };

  // A semantic host the author hid is a dead mirror: the exporter drops it at
  // the same opacity threshold, so nothing downstream consumes it, yet Chromium
  // still paints it faintly over the author's own rendering of the same content
  // (a second, ghostly copy of a formula or table). Report those so the pipeline
  // can switch them off outright instead of shipping doubled ink.
  const deadHosts = [];
  for (const host of root.querySelectorAll('[data-pptx]')) {
    if (!host.firstElementChild) continue;
    const style = css(host);
    const hidden = style.display === 'none' || style.visibility === 'hidden'
      || num(style.opacity) <= HIDDEN_OPACITY;
    if (!hidden || style.display === 'none') continue;
    deadHosts.push({
      selector: repairSelectorFor(host),
      kind: host.getAttribute('data-pptx') || '',
      opacity: style.opacity,
      visibility: style.visibility,
      sceneOwner: String(host.closest('[data-layout-id]')?.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
    });
  }

  const elements = [];
  const elementNodes = [];
  const indexByElement = new Map();
  for (const el of root.querySelectorAll('*')) {
    if (!isVisible(el) || ['SCRIPT', 'STYLE', 'META', 'LINK'].includes(el.tagName)) continue;
    if (!isComponent(el)) continue;
    const style = css(el);
    const rect = el.getBoundingClientRect();
    const box = localRect(rect);
    const authoredOverflow = authoredContentOverflow(el, rect);
    const index = elements.length;
    indexByElement.set(el, index);
    elementNodes.push(el);
    elements.push({
      id: idFor(el, index),
      repairSelector: repairSelectorFor(el),
      role: el.getAttribute('data-layout-role') || el.getAttribute('data-pptx') || '',
      sceneRole: el.closest('[data-layout-role]')?.getAttribute('data-layout-role') || '',
      pptx: el.getAttribute('data-pptx') || '',
      tag: el.tagName.toLowerCase(),
      box,
      parent: null,
      painted: painted(el, style),
      // An opaque surface hides whatever is beneath it across its whole box,
      // not just where its own glyphs land. Without this, an opaque band laid
      // over a paragraph was compared ink-to-ink -- 1.3px of overlap where the
      // two sentences happened to graze -- while the band's background covered
      // 40px of the paragraph and the reader saw a sentence cut in half.
      opaqueSurface: opaqueSurface(el, style),
      position: style.position,
      textual: Boolean(String(el.textContent || '').replace(/\s+/g, ' ').trim()),
      ink: inkRectFor(el),
      escapesOwner: escapedOwner(el, rect),
      typography: {
        fontSize: num(style.fontSize),
        lineHeight: num(style.lineHeight),
        letterSpacing: num(style.letterSpacing),
        centersWithLineHeight: centersTextWithLineHeight(el, style),
      },
      layoutCandidates: layoutCandidatesFor(el),
      overflow: {
        x: style.overflowX,
        y: style.overflowY,
        scrollX: Math.max(0, +(el.scrollWidth - el.clientWidth).toFixed(2)),
        scrollY: Math.max(0, +(el.scrollHeight - el.clientHeight).toFixed(2)),
        contentX: authoredOverflow.x,
        contentY: authoredOverflow.y,
        targets: authoredOverflow.targets,
        clippedByAncestor: clippedByAncestor(el, rect),
      },
      outsidePlate: box.left < -0.5 || box.top < -0.5
        || box.right > rootRect.width + 0.5 || box.bottom > rootRect.height + 0.5,
      pageNumber: el.hasAttribute('data-sunairum-page-number'),
      decorative: isDecorative(el),
      footer: el.hasAttribute('data-sunairum-page-number')
        || /(?:^|\s)footer(?:\s|$)/i.test(el.className || ''),
    });
  }
  for (const [el, index] of indexByElement.entries()) {
    const parent = componentParent(el);
    elements[index].parent = parent === root ? 'slide' : idFor(parent, indexByElement.get(parent) ?? -1);
  }

  const absoluteCollisionRepair = (a, b, aNode, bNode) => {
    const aText = a.textual && !a.pptx;
    const bText = b.textual && !b.pptx;
    let movable = null;
    let obstacle = null;
    let movableNode = null;
    let obstacleNode = null;
    // Text furniture should clear figures/tables, never be painted over them.
    if (aText && b.pptx && a.position === 'absolute') {
      movable = a; obstacle = b; movableNode = aNode; obstacleNode = bNode;
    } else if (bText && a.pptx && b.position === 'absolute') {
      movable = b; obstacle = a; movableNode = bNode; obstacleNode = aNode;
    } else if (a.position === 'absolute' && b.position !== 'absolute') {
      movable = a; obstacle = b; movableNode = aNode; obstacleNode = bNode;
    } else if (b.position === 'absolute' && a.position !== 'absolute') {
      movable = b; obstacle = a; movableNode = bNode; obstacleNode = aNode;
    } else if (a.position === 'absolute' && b.position === 'absolute') {
      // Prefer the smaller textual label/callout over the larger visual plane.
      const aArea = a.box.width * a.box.height;
      const bArea = b.box.width * b.box.height;
      if (aText && (!bText || aArea <= bArea)) {
        movable = a; obstacle = b; movableNode = aNode; obstacleNode = bNode;
      } else if (bText) {
        movable = b; obstacle = a; movableNode = bNode; obstacleNode = aNode;
      }
    }
    if (!movable || !obstacle || !movableNode) return null;
    const sceneNode = movableNode.closest('[data-layout-id^="scene-"]');
    if (!sceneNode) return null;
    const sceneBox = containmentBoxFor(movableNode, sceneNode);
    const gap = 8;
    // Everything the moved element could land on, not merely its component
    // siblings. A band pinned to the bottom of a dark panel was re-anchored to
    // top:0 because the panel's own kicker and heading resolved to a different
    // component parent, so they scored no penalty — and the band came to rest
    // straight on the heading. Anything with copy inside the containment box is
    // an obstacle, whatever the DOM nesting says.
    const movableIndex = elementNodes.indexOf(movableNode);
    const peers = elements.filter((item, index) => {
      if (item === movable || index === movableIndex) return false;
      if (item.footer || item.pageNumber) return false;
      if (!item.textual && !item.painted) return false;
      const node = elementNodes[index];
      if (!node || node.contains(movableNode) || movableNode.contains(node)) return false;
      if (!sceneNode.contains(node)) return false;
      // Only obstacles that actually share the lane the element may move within.
      return item.box.right > sceneBox.left && item.box.left < sceneBox.right;
    });
    const candidates = [
      obstacle.box.bottom + gap,
      obstacle.box.top - movable.box.height - gap,
      sceneBox.top,
      sceneBox.bottom - movable.box.height,
    ];
    for (const peer of peers) {
      candidates.push(peer.box.top - movable.box.height - gap, peer.box.bottom + gap);
    }
    const scoreTop = (top) => {
      if (top < sceneBox.top - 0.5 || top + movable.box.height > sceneBox.bottom + 0.5) return Number.POSITIVE_INFINITY;
      const candidate = {...movable.box, top, bottom: top + movable.box.height};
      let overlapPenalty = 0;
      for (const peer of peers) {
        if (!rectIntersects(candidate, peer.box)) continue;
        const hit = intersection(candidate, peer.box);
        overlapPenalty += hit.width * hit.height * 1000;
      }
      return overlapPenalty + Math.abs(top - movable.box.top);
    };
    const ranked = [...new Set(candidates.map((value) => +value.toFixed(2)))]
      .map((top) => ({top, score: scoreTop(top)}))
      .sort((left, right) => left.score - right.score);
    // Every position lands on copy: the container simply has no lane for this
    // band. Sliding it anyway is what pinned a bottom-anchored range band to
    // top:0, straight over its own panel's heading, and then re-emitted that
    // same no-op every pass. Reserve the lane instead — pad the container by
    // the band's height and restore its bottom anchor — and let the region's
    // type/spacing pass absorb the space.
    const clearTop = ranked.find((entry) => entry.score < 1000);
    if (!clearTop) {
      const container = movableNode.offsetParent;
      if (container && container !== root && sceneNode.contains(container)) {
        const containerStyle = css(container);
        const padBottom = num(containerStyle.paddingBottom);
        // Padding can only reserve a lane in a container that is free to grow,
        // or whose contents shrink to fit. A Scene region is neither: its height
        // is the layout contract, and a paragraph's height comes from its own
        // text, so padding-bottom just moves the edge the copy overflows past.
        // Un-pin the band instead. A summary pinned to the bottom of a panel is
        // a flourish; once the list above has grown into it, letting it sit
        // after that list keeps the reading order and ends the overlap, and the
        // overrun that remains is something the region's own padding and type
        // passes can actually absorb.
        // Can this container actually grow? Padding only reserves a lane when
        // the box has somewhere to expand into. A panel already filling its
        // region to the bottom edge has none -- padding there just pushes its
        // own content past the edge instead -- and neither does the region
        // itself, whose height is the layout contract. Checking only for a
        // region or an inline height missed the commonest case: a panel sized
        // by a stylesheet to fill its lane, which was handed a
        // padding-bottom of 134px it could do nothing with.
        const containerBottom = container.getBoundingClientRect().bottom;
        const contractHeight = container === sceneNode
          || container.hasAttribute('data-layout-id')
          || /\bheight\s*:/i.test(String(container.getAttribute('style') || ''))
          || containerBottom >= sceneBox.bottom - 1;
        if (contractHeight) {
          return {
            sceneOwner: String(sceneNode.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
            targetSelector: repairSelectorFor(movableNode),
            movableSelector: repairSelectorFor(movableNode),
            strategy: 'unpin_band_into_flow',
          };
        }
        return {
          sceneOwner: String(sceneNode.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
          targetSelector: repairSelectorFor(container),
          movableSelector: repairSelectorFor(movableNode),
          strategy: 'reserve_container_bottom',
          suggestedPaddingBottom: +(padBottom + movable.box.height + gap).toFixed(2),
          suggestedBottom: +padBottom.toFixed(2),
        };
      }
    }
    const desiredPageTop = ranked.length && Number.isFinite(ranked[0].score)
      ? ranked[0].top
      : Math.max(sceneBox.top, Math.min(sceneBox.bottom - movable.box.height, movable.box.top));
    const offsetParent = movableNode.offsetParent || sceneNode;
    const offsetBox = offsetParent.getBoundingClientRect();
    const suggestedTop = +(
      num(css(movableNode).top) + desiredPageTop - movable.box.top
    ).toFixed(2);
    const offsetLocal = localRect(offsetBox);
    // A caption cannot be moved above a full-frame semantic host when its
    // positioned parent starts at the host edge. Reserve a caption lane by
    // shortening the host instead; its contain-fit renderer preserves the
    // figure while the authored caption remains in its intended bottom lane.
    if (
      obstacle.pptx && obstacleNode
      && (
        desiredPageTop < offsetLocal.top - 0.5
        || desiredPageTop + movable.box.height > offsetLocal.bottom + 0.5
      )
    ) {
      const parentBox = localRect((movableNode.offsetParent || sceneNode).getBoundingClientRect());
      return {
        sceneOwner: String(sceneNode.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
        targetSelector: repairSelectorFor(obstacleNode),
        strategy: 'reserve_semantic_bottom',
        suggestedBottom: +(Math.max(0, parentBox.bottom - movable.box.top + gap)).toFixed(2),
      };
    }
    return {
      sceneOwner: String(sceneNode.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
      targetSelector: repairSelectorFor(movableNode),
      strategy: 'set_absolute_top',
      suggestedTop,
    };
  };

  const collisions = [];
  // Two text blocks stacked in normal flow share a boundary, and glyph ink
  // crosses it whenever line-height is tighter than the face's natural extent:
  // a 21px serif heading on a 22px line box puts its descenders a few px into
  // the leading of the 15px line beneath. That is ordinary tight typography —
  // the CSS boxes do not intersect and no glyph touches another — but comparing
  // ink rects reported it as a collision on every metric row of a slide, twice
  // over (once as siblings, once as text), and the repair would have pushed the
  // rows apart until the card overflowed.
  // A formula lays its own glyphs out, and the layout is meant to overlap: a
  // sum's limits sit directly under and over the operator, a min's subscript
  // tucks beneath it. It also leaves as one exported object (OMML), so its
  // interior is not subject to the deck's collision rules — measuring it
  // reported "∑ overlaps =" and "min overlaps ∈" as slide defects.
  const withinFormula = (node) => Boolean(
    node && node.closest && (
      node.closest('math')
      || node.closest('[data-pptx="formula"]')
      || node.closest('.katex')
    )
  );
  /**
   * Ink a face legitimately places outside its own line box — the ascender
   * above, the descender below. Capped at a share of the em because a face
   * cannot need more than that: past the cap the leading is pathological, not
   * natural, and the glyphs really are printing over their neighbour.
   */
  const naturalOvershoot = (raw, fontSize) =>
    Math.max(0, Math.min(raw, Math.max(4, (fontSize || 16) * 0.35)));

  const isFlowInkBleed = (a, b) => {
    if (!a.textual || !b.textual) return false;
    // Only for elements the flow stacked; an absolute overlap is a real defect.
    if (a.position === 'absolute' || a.position === 'fixed') return false;
    if (b.position === 'absolute' || b.position === 'fixed') return false;
    const boxOverlap = rectIntersects(a.box, b.box) ? intersection(a.box, b.box) : null;
    // Their layout boxes must be adjacent, not overlapping.
    if (boxOverlap && boxOverlap.height > 1) return false;
    const inkOverlap = intersection(a.ink || a.box, b.ink || b.box);
    if (!inkOverlap) return false;
    // The shared ink is the sum of *both* faces' overshoots, so a single
    // face's em was the wrong yardstick: 0.16em of a 21px `strong` is 3.36px,
    // under the 5px that a 3px descender above a 2px ascender actually needs,
    // and three perfectly stacked rows were reported as collisions.
    const upper = (a.ink || a.box).top <= (b.ink || b.box).top ? a : b;
    const lower = upper === a ? b : a;
    const allowance =
      naturalOvershoot(
        (upper.ink || upper.box).bottom - upper.box.bottom,
        num((upper.typography || {}).fontSize),
      )
      + naturalOvershoot(
        lower.box.top - (lower.ink || lower.box).top,
        num((lower.typography || {}).fontSize),
      );
    return inkOverlap.height <= Math.max(2, allowance) + 1;
  };

  for (let i = 0; i < elements.length; i += 1) {
    for (let j = i + 1; j < elements.length; j += 1) {
      const a = elements[i];
      const b = elements[j];
      const aNode = elementNodes[i];
      const bNode = elementNodes[j];
      const sameParent = a.parent === b.parent;
      const aScene = aNode.closest('[data-layout-id^="scene-"]');
      const bScene = bNode.closest('[data-layout-id^="scene-"]');
      const unrelated = !aNode.contains(bNode) && !bNode.contains(aNode);
      const aToken = String(aNode.className || '');
      const bToken = String(bNode.className || '');
      const chartFurniture = (
        (a.painted && !a.textual && /(?:bar|axis|plot|legend|metric)/i.test(aToken))
        || (b.painted && !b.textual && /(?:bar|axis|plot|legend|metric)/i.test(bToken))
      );
      // Accessibility-hidden artwork still participates in visual QA, but it
      // is checked by the focused decoration-vs-text pass below.  Mixing it
      // into generic component collision repair would move authored copy to
      // accommodate ornamental rules and connector spines.
      if (a.decorative || b.decorative) continue;
      // Authoring frequently nests a caption and its semantic host under
      // different wrappers. Same-parent-only inspection misses table headings
      // painted over headers and chart labels painted over bars. Cross-wrapper
      // checks remain local to one Scene region and ignore ancestor ownership.
      const crossWrapperRisk = unrelated && aScene && aScene === bScene && (
        (a.textual && b.textual)
        || (a.textual && Boolean(b.pptx))
        || (b.textual && Boolean(a.pptx))
        || chartFurniture
      );
      if (!sameParent && !crossWrapperRisk) continue;
      if ((!a.textual && !a.painted) || (!b.textual && !b.painted)) continue;
      // Thin empty rules and connector spines intentionally sit behind a
      // compound process container. Their relationships to actual text/cards
      // are checked separately by decorationCollisions below.
      if ((a.painted && !a.textual && (a.box.height <= 6 || a.box.width <= 6))
          || (b.painted && !b.textual && (b.box.height <= 6 || b.box.width <= 6))) continue;
      // Pipeline footer chrome lives in its own reserved band.
      if (a.footer || b.footer || a.pageNumber || b.pageNumber) continue;
      // Compare what each element paints. A text element's border box routinely
      // spans a whole column while its sentence occupies half a line, so the box
      // test manufactured overlaps between copy and the annotation beside it.
      // Painted (non-text) elements keep their box: their surface *is* their ink.
      // An element that paints an opaque surface is measured by its box even
      // when it also carries text: the surface is what it covers.
      const aHit = (a.textual && a.ink && !a.opaqueSurface) ? a.ink : a.box;
      const bHit = (b.textual && b.ink && !b.opaqueSurface) ? b.ink : b.box;
      if (!rectIntersects(aHit, bHit)) continue;
      if (isFlowInkBleed(a, b)) continue;
      if (withinFormula(aNode) || withinFormula(bNode)) continue;
      const overlap = intersection(aHit, bHit);
      const repair = absoluteCollisionRepair(a, b, aNode, bNode);
      // One of them paints a surface the other's text cannot be read through.
      // Worth naming, because the reader does not lose the same thing in every
      // collision: text under an opaque sheet is gone, while text a few pixels
      // past a boundary is still there to be read.
      //
      // Which one is in front decides it, and paint order is not something to
      // re-derive from position and z-index -- a navy strip *behind* a pale
      // band is opaque and overlaps its text, and reading only the two styles
      // called that an occlusion too. elementFromPoint is the browser's own
      // answer to "what would the reader see here", so ask that.
      const occlusion = (() => {
        if (!((a.opaqueSurface && b.textual) || (b.opaqueSurface && a.textual))) {
          return false;
        }
        const aRect = aNode.getBoundingClientRect();
        const bRect = bNode.getBoundingClientRect();
        const x = (Math.max(aRect.left, bRect.left) + Math.min(aRect.right, bRect.right)) / 2;
        const y = (Math.max(aRect.top, bRect.top) + Math.min(aRect.bottom, bRect.bottom)) / 2;
        const front = document.elementFromPoint(x, y);
        if (!front) return false;
        const covers = (candidate, covered) =>
          candidate.opaqueSurface
          && covered.textual
          && (front === elementNodes[elements.indexOf(candidate)]
            || elementNodes[elements.indexOf(candidate)].contains(front));
        return covers(a, b) || covers(b, a);
      })();
      collisions.push({
        a: a.id, b: b.id, parent: sameParent ? a.parent : 'scene-local',
        scope: sameParent ? 'sibling' : 'cross-wrapper', ...overlap, repair,
        occlusion,
      });
    }
  }

  // Rules are collected here rather than taken from `elements`, because a rule
  // is not a component: `isComponent` requires 8px in both axes, so a 3px-tall
  // accent bar was never measured at all — and this pass, whose whole purpose
  // is to keep thin rules off the copy, could not see a single one. A 78×3px
  // rule was drawn straight through the second line of a note as a result.
  // Shape, not size: any painted decoration far wider than it is tall.
  const rules = [];
  for (const node of root.querySelectorAll('*')) {
    if (!isVisible(node)) continue;
    const style = css(node);
    if (String(node.textContent || '').trim()) continue;
    if (!painted(node, style)) continue;
    const rect = node.getBoundingClientRect();
    // A rule is a thin bar in *either* axis. The test used to demand a wide,
    // short box, so a 6x64px vertical accent bar was invisible to the one pass
    // whose job is keeping rules off the copy — and it printed straight through
    // the first letter of a byline ("Doç" reading as "oç").
    const thin = Math.min(rect.width, rect.height);
    const long = Math.max(rect.width, rect.height);
    if (thin > 6 || long < 24 || long < thin * 4) continue;
    rules.push({
      node,
      id: idFor(node, -1),
      box: localRect(rect),
      vertical: rect.height > rect.width,
    });
  }

  const decorationCollisions = [];
  for (let i = 0; i < rules.length; i += 1) {
    const line = rules[i];
    for (let j = 0; j < elements.length; j += 1) {
      const target = elements[j];
      if (target.decorative || !target.textual || target.footer || target.pageNumber) continue;
      const lineNode = line.node;
      const targetNode = elementNodes[j];
      if (lineNode.contains(targetNode) || targetNode.contains(lineNode)) continue;
      if (lineNode.closest('[data-layout-id]') !== targetNode.closest('[data-layout-id]')) continue;
      const horizontalInkOverlap = Math.max(
        0, Math.min(line.box.right, target.box.right) - Math.max(line.box.left, target.box.left)
      );
      const titleClearance = line.box.top - target.box.bottom;
      const requiredTitleClearance = Math.max(16, target.typography.fontSize * 0.4);
      if (
        target.typography.fontSize >= 32
        && horizontalInkOverlap >= Math.min(120, target.box.width * 0.5)
        && titleClearance >= 0
        && titleClearance < requiredTitleClearance
      ) {
        const needed = requiredTitleClearance - titleClearance;
        const sceneOwnerId = String(
          targetNode.closest('[data-layout-id]')?.getAttribute('data-layout-id') || ''
        ).replace(/^scene-/, '');
        const lineStyle = css(lineNode);
        const currentMarginTop = num(css(targetNode).marginTop);
        // Prefer moving the rule. It carries no content, so pushing it down
        // costs nothing, whereas pulling the title up is only possible if the
        // title has margin to give -- and when it has none, the suggestion is
        // margin-top:0 on an element already at 0: a repair that changes
        // nothing and re-fires on every pass.
        const lineAbsolute = lineStyle.position === 'absolute' || lineStyle.position === 'fixed';
        const lineOffsetParent = lineNode.offsetParent || root;
        const lineOffsetRect = lineOffsetParent.getBoundingClientRect();
        const movedBottom = line.box.bottom + needed;
        const sceneBox = (lineNode.closest('[data-layout-id]') || root).getBoundingClientRect();
        const sceneBottom = localRect(sceneBox).bottom;
        if (lineAbsolute && movedBottom <= sceneBottom - 0.5) {
          decorationCollisions.push({
            line: line.id, target: target.id, width: +horizontalInkOverlap.toFixed(2), height: 0,
            gap: +titleClearance.toFixed(2), requiredGap: +requiredTitleClearance.toFixed(2),
            targetSelector: repairSelectorFor(targetNode),
            sceneOwner: sceneOwnerId,
            strategy: 'move_decoration_absolute',
            ruleSelector: repairSelectorFor(lineNode),
            suggestedTop: +(line.box.top + needed - (localRect(lineOffsetRect).top)).toFixed(2),
          });
          continue;
        }
        if (currentMarginTop - needed < 0) {
          // Neither term can give: the rule is in flow and the title has no
          // margin to surrender. Reported, not silently "repaired".
          decorationCollisions.push({
            line: line.id, target: target.id, width: +horizontalInkOverlap.toFixed(2), height: 0,
            gap: +titleClearance.toFixed(2), requiredGap: +requiredTitleClearance.toFixed(2),
            targetSelector: repairSelectorFor(targetNode),
            sceneOwner: sceneOwnerId,
            strategy: 'report_only',
          });
          continue;
        }
        decorationCollisions.push({
          line: line.id, target: target.id, width: +horizontalInkOverlap.toFixed(2), height: 0,
          gap: +titleClearance.toFixed(2), requiredGap: +requiredTitleClearance.toFixed(2),
          targetSelector: repairSelectorFor(targetNode),
          sceneOwner: sceneOwnerId,
          strategy: 'shift_target_up',
          suggestedMarginTop: +(currentMarginTop - needed).toFixed(2),
        });
        continue;
      }
      if (!rectIntersects(line.box, target.box)) continue;
      // Inside a chart, figure or diagram a line deeper in the box may be a
      // meaningful data mark, so only a rule grazing the top edge is a defect
      // there. Over plain copy there is no such thing: a rule crossing the
      // middle of a paragraph is a rule struck through a sentence, and skipping
      // it left an accent bar drawn across the second line of a note.
      const targetOwnsMarks = Boolean(targetNode.closest('[data-pptx]'));
      if (targetOwnsMarks
          && (line.box.top < target.box.top - 1 || line.box.top > target.box.top + 12)) {
        continue;
      }
      // A vertical bar is *meant* to sit beside copy — a left accent rule is a
      // normal device — so only ink it actually covers is a defect. Comparing
      // boxes would report every padded card whose bar hugs its own edge.
      if (line.vertical) {
        const ink = target.ink || target.box;
        const coveredX = Math.min(line.box.right, ink.right) - Math.max(line.box.left, ink.left);
        const coveredY = Math.min(line.box.bottom, ink.bottom) - Math.max(line.box.top, ink.top);
        if (coveredX <= settings.overlapEpsilon || coveredY <= settings.overlapEpsilon) continue;
      }
      // A rule crossing a paragraph also crosses the card holding it. Report the
      // innermost target: it names the sentence the reader sees struck through,
      // and one defect must not produce two repairs that both shift the copy.
      const innerHit = elements.some((other, index) => (
        index !== j
        && other.textual
        && !other.decorative
        && targetNode.contains(elementNodes[index])
        && elementNodes[index] !== targetNode
        && rectIntersects(line.box, other.box)
      ));
      if (innerHit) continue;
      const overlap = intersection(line.box, target.box);
      // Prefer moving the rule. It carries no content, so relocating or dropping
      // it cannot lose anything; shifting the sentence instead pushes it further
      // out of a region it may already be overflowing, which is why the copy-side
      // repair kept being measured as no improvement and rejected.
      const owner = lineNode.offsetParent || root;
      const ownerBox = localRect(owner.getBoundingClientRect());
      const ruleHeight = line.box.height;
      // The clear band has to be clear of *all* the copy in this owner, not
      // just the line we collided with. Measuring against the one target moved
      // the rule off a note's second line and straight onto the note's label.
      let inkTop = Infinity;
      let inkBottom = -Infinity;
      for (const other of elements) {
        if (other.decorative || !other.textual) continue;
        if (!owner.contains(elementNodes[elements.indexOf(other)])) continue;
        inkTop = Math.min(inkTop, other.box.top);
        inkBottom = Math.max(inkBottom, other.box.bottom);
      }
      const ruleStyle = css(lineNode);
      // Computed style resolves `auto` to a used px value, so the declared
      // anchor is read from the element's own rule, not the cascade.
      const anchoredToBottom = /(?:^|;)\s*bottom\s*:/.test(lineNode.style.cssText || '')
        || (ruleStyle.bottom !== 'auto' && line.box.bottom > (inkBottom + ownerBox.bottom) / 2);
      let ruleStrategy = 'hide_decoration';
      let suggestedRuleBottom = null;
      let suggestedRuleTop = null;
      if (Number.isFinite(inkTop) && ownerBox.bottom - inkBottom - 8 >= ruleHeight + 4) {
        ruleStrategy = anchoredToBottom ? 'set_rule_bottom' : 'set_rule_top';
        suggestedRuleBottom = +(ownerBox.bottom - inkBottom - 8 - ruleHeight).toFixed(2);
        suggestedRuleTop = +(inkBottom - ownerBox.top + 8).toFixed(2);
      } else if (Number.isFinite(inkTop) && inkTop - ownerBox.top - 8 >= ruleHeight + 4) {
        ruleStrategy = anchoredToBottom ? 'set_rule_bottom' : 'set_rule_top';
        suggestedRuleBottom = +(ownerBox.bottom - inkTop + 8).toFixed(2);
        suggestedRuleTop = +(inkTop - ownerBox.top - 8 - ruleHeight).toFixed(2);
      }
      decorationCollisions.push({
        line: line.id, target: target.id, width: overlap.width, height: overlap.height,
        ruleSelector: repairSelectorFor(lineNode),
        ruleStrategy,
        suggestedRuleBottom,
        suggestedRuleTop,
        targetSelector: repairSelectorFor(targetNode),
        sceneOwner: String(targetNode.closest('[data-layout-id]')?.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
        // A vertical bar is cleared sideways, not downwards: moving the copy
        // down leaves it under the same bar. Indent it past the bar instead,
        // which is what the design meant in the first place.
        ...(line.vertical
          ? {
              strategy: 'reserve_left_gutter',
              suggestedPaddingLeft: +(
                num(css(targetNode).paddingLeft)
                + Math.max(6, line.box.right - (target.ink || target.box).left + 8)
              ).toFixed(2),
              currentPaddingLeft: +num(css(targetNode).paddingLeft).toFixed(2),
            }
          : {
              strategy: 'shift_target_down',
              shiftY: +(Math.max(8, line.box.bottom - target.box.top + 8)).toFixed(2),
              currentMarginTop: +num(css(targetNode).marginTop).toFixed(2),
              suggestedMarginTop: +(
                num(css(targetNode).marginTop)
                + Math.max(8, line.box.bottom - target.box.top + 8)
              ).toFixed(2),
            }),
      });
    }
  }

  const wordFragments = [];
  const narrowText = [];
  const textRuns = [];
  const narrowSeen = new Set();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let textNode;
  while ((textNode = walker.nextNode())) {
    const value = textNode.nodeValue || '';
    const parent = textNode.parentElement;
    if (!parent || !isVisible(parent) || isDecorative(parent)) continue;
    if (withinFormula(parent)) continue;
    const parentRect = parent.getBoundingClientRect();
    const parentStyle = css(parent);
    const clean = value.replace(/\s+/g, ' ').trim();
    if (clean) {
      const owner = parent.closest('[data-layout-id^="scene-"]');
      const range = document.createRange();
      range.selectNodeContents(textNode);
      for (const rect of [...range.getClientRects()].filter((r) => r.width > 0.5 && r.height > 0.5)) {
        textRuns.push({
          parent,
          block: nearestBlock(parent),
          selector: repairSelectorFor(parent),
          text: clean.slice(0, 100),
          sceneOwner: owner ? String(owner.getAttribute('data-layout-id') || '').replace(/^scene-/, '') : '',
          box: rect,
          position: css(parent).position,
          // Its own line box and face size, so a bleed across a flow boundary
          // can be told apart from a real overlap.
          fontSize: num(parentStyle.fontSize),
          lineBox: parentRect,
        });
      }
    }
    if (clean.length >= 12 && !narrowSeen.has(parent)) {
      const whole = document.createRange();
      whole.selectNodeContents(textNode);
      const lines = [...whole.getClientRects()].filter((r) => r.width > 0.5 && r.height > 0.5);
      const fontSize = num(parentStyle.fontSize);
      const charsPerLine = clean.length / Math.max(1, lines.length);
      if ((parentRect.width < Math.max(120, fontSize * 7) && lines.length >= 3)
          || (lines.length >= 5 && charsPerLine < 12)) {
        const gridAncestor = gridAncestorFor(parent);
        const sceneRoot = parent.closest('[data-layout-id^="scene-"]');
        narrowSeen.add(parent);
        narrowText.push({
          element: idFor(parent, -1), width: +parentRect.width.toFixed(2),
          fontSize: +fontSize.toFixed(2), lines: lines.length,
          charsPerLine: +charsPerLine.toFixed(1), text: clean.slice(0, 100),
          box: localRect(parentRect),
          sceneOwner: sceneRoot ? String(sceneRoot.getAttribute('data-layout-id') || '').replace(/^scene-/, '') : '',
          gridRepair: gridAncestor ? {
            selector: repairSelectorFor(gridAncestor.node),
            strategy: gridAncestor.strategy,
            directChildren: gridAncestor.node.children.length,
            columns: String(css(gridAncestor.node).gridTemplateColumns || ''),
            ...(gridAncestor.strategy === 'widen_narrow_track'
              ? {
                  narrowIndex: gridAncestor.narrowIndex,
                  donorIndex: gridAncestor.donorIndex,
                  widths: gridAncestor.widths,
                  // Enough for a readable measure, and never more than a third
                  // of the donor: a track that fixes this caption by starving
                  // its neighbour has moved the defect, not removed it.
                  suggestedColumns: (() => {
                    const widths = gridAncestor.widths.slice();
                    const target = 20;
                    const perChar = charsPerLine > 0 ? parentRect.width / charsPerLine : 0;
                    const want = perChar > 0 ? perChar * target - parentRect.width : 0;
                    const donor = widths[gridAncestor.donorIndex] || 0;
                    const move = Math.max(0, Math.min(want, donor * 0.33));
                    if (move < 8) return '';
                    widths[gridAncestor.narrowIndex] += move;
                    widths[gridAncestor.donorIndex] -= move;
                    return widths.map((width) => width.toFixed(2) + 'px').join(' ');
                  })(),
                }
              : {}),
          } : null,
        });
      }
    }
    // Hyphens and punctuation are legal browser line-break opportunities.
    // Measure indivisible letter/number runs so ordinary hyphenation is not
    // confused with the narrow-column, letter-by-letter failure mode.
    const re = /[\p{L}\p{N}_]{3,}/gu;
    let match;
    while ((match = re.exec(value))) {
      // A deliberately styled ::first-letter is painted as a separate glyph
      // fragment by Chromium. Range#getClientRects then returns two rectangles
      // for an intact first word (for example a green "A" in "Aynı"). That is
      // not wrapping and must not trigger destructive region recovery.
      const leading = value.search(/\S/);
      const firstLetter = window.getComputedStyle(parent, '::first-letter');
      const styledFirstLetter = match.index === leading && (
        firstLetter.color !== parentStyle.color
        || firstLetter.backgroundColor !== parentStyle.backgroundColor
        || firstLetter.fontSize !== parentStyle.fontSize
        || firstLetter.fontWeight !== parentStyle.fontWeight
        || firstLetter.fontFamily !== parentStyle.fontFamily
        || firstLetter.letterSpacing !== parentStyle.letterSpacing
      );
      const range = document.createRange();
      range.setStart(textNode, match.index);
      range.setEnd(textNode, match.index + match[0].length);
      const rects = [...range.getClientRects()].filter((r) => r.width > 0.5 && r.height > 0.5);
      if (rects.length > 1 && !styledFirstLetter) {
        wordFragments.push({word: match[0].slice(0, 80), element: idFor(parent, -1), lines: rects.length});
      }
      if (wordFragments.length >= settings.maxWordFragments) break;
    }
    if (wordFragments.length >= settings.maxWordFragments) break;
  }

  // Text living in spans/divs without a semantic component class used to be
  // invisible to component-box collision checks. Compare actual glyph-line
  // rectangles so labels, annotations, and diagram furniture cannot stack.
  const textCollisions = [];
  const textCollisionSeen = new Set();
  const horizontalTextRepair = (movable, obstacle) => {
    if (movable.position !== 'absolute' && movable.position !== 'fixed') return null;
    const sceneNode = movable.parent.closest('[data-layout-id^="scene-"]');
    if (!sceneNode) return null;
    // Same containment rule as the vertical repair: a label may only slide
    // within the box it is positioned against. Searching the whole scene lets a
    // card's numeral come to rest in the gutter between two columns.
    // Text-run boxes here are raw viewport rectangles, so the bound must be too.
    const sceneRect = viewportContainmentBoxFor(movable.parent, sceneNode);
    const offsetParent = movable.parent.offsetParent || sceneNode;
    const currentStyle = css(movable.parent);
    const width = movable.box.width;
    const candidates = [
      obstacle.box.right + settings.minLabelGap,
      obstacle.box.left - width - settings.minLabelGap,
      sceneRect.left,
      sceneRect.right - width,
    ];
    const free = candidates
      .filter((left) => left >= sceneRect.left - 0.5 && left + width <= sceneRect.right + 0.5)
      .filter((left) => {
        const rect = {...movable.box, left, right: left + width};
        return !textRuns.some((run) => (
          run !== movable && run !== obstacle && run.sceneOwner === movable.sceneOwner
          && run.parent !== movable.parent && rectIntersects(rect, run.box)
        ));
      })
      .sort((a, b) => Math.abs(a - movable.box.left) - Math.abs(b - movable.box.left))[0];
    if (!Number.isFinite(free)) return null;
    return {
      sceneOwner: movable.sceneOwner,
      targetSelector: movable.selector,
      strategy: 'set_absolute_left',
      suggestedLeft: +(num(currentStyle.left) + free - movable.box.left).toFixed(2),
      offsetParent: repairSelectorFor(offsetParent),
    };
  };
  for (let i = 0; i < textRuns.length; i += 1) {
    for (let j = i + 1; j < textRuns.length; j += 1) {
      const a = textRuns[i];
      const b = textRuns[j];
      if (!a.sceneOwner || a.sceneOwner !== b.sceneOwner) continue;
      if (a.parent === b.parent || a.parent.contains(b.parent) || b.parent.contains(a.parent)) continue;
      if (a.block && a.block === b.block) continue;
      const verticalInkOverlap = Math.min(a.box.bottom, b.box.bottom) - Math.max(a.box.top, b.box.top);
      const horizontalGap = Math.max(
        0,
        Math.max(a.box.left, b.box.left) - Math.min(a.box.right, b.box.right),
      );
      const absolutePair = ['absolute', 'fixed'].includes(a.position)
        && ['absolute', 'fixed'].includes(b.position);
      if (!rectIntersects(a.box, b.box)
          && !(absolutePair && verticalInkOverlap > settings.overlapEpsilon
            && horizontalGap < settings.minLabelGap)) continue;
      // A client rect is glyph ink. Two runs the flow stacked bleed into each
      // other's leading whenever line-height is tighter than the face's natural
      // extent; their line boxes stay adjacent and no glyph touches another.
      if (!absolutePair) {
        const boxGap = Math.max(a.lineBox.top, b.lineBox.top)
          - Math.min(a.lineBox.bottom, b.lineBox.bottom);
        const inkBleed = Math.min(a.box.bottom, b.box.bottom)
          - Math.max(a.box.top, b.box.top);
        // Same correction as isFlowInkBleed: the bleed belongs to two faces, so
        // measure both overshoots instead of taking a fraction of one em.
        const upperRun = a.lineBox.top <= b.lineBox.top ? a : b;
        const lowerRun = upperRun === a ? b : a;
        const allowance =
          naturalOvershoot(upperRun.box.bottom - upperRun.lineBox.bottom, upperRun.fontSize)
          + naturalOvershoot(lowerRun.lineBox.top - lowerRun.box.top, lowerRun.fontSize);
        if (boxGap >= -1 && inkBleed > 0 && inkBleed <= Math.max(2, allowance) + 1) continue;
      }
      const key = [a.selector, b.selector].sort().join('|');
      if (textCollisionSeen.has(key)) continue;
      textCollisionSeen.add(key);
      const aArea = a.box.width * a.box.height;
      const bArea = b.box.width * b.box.height;
      const first = aArea <= bArea ? a : b;
      const second = first === a ? b : a;
      const repair = horizontalTextRepair(first, second) || horizontalTextRepair(second, first);
      const overlap = intersection(a.box, b.box);
      textCollisions.push({
        a: a.selector, b: b.selector, aText: a.text, bText: b.text,
        sceneOwner: a.sceneOwner, width: overlap.width, height: overlap.height,
        gap: +horizontalGap.toFixed(2), requiredGap: settings.minLabelGap,
        repair,
      });
    }
  }

  // Pseudo-elements participate in the authored composition but are absent
  // from querySelectorAll(). Measure textual pseudo furniture explicitly.
  const pseudoIssues = [];
  const pseudoHostDecorationSeen = new Set();
  const measureCanvas = document.createElement('canvas');
  const measureContext = measureCanvas.getContext('2d');
  const pseudoRectFor = (el, pseudoStyle, content) => {
    const origin = el.getBoundingClientRect();
    const padX = num(pseudoStyle.paddingLeft) + num(pseudoStyle.paddingRight)
      + num(pseudoStyle.borderLeftWidth) + num(pseudoStyle.borderRightWidth);
    const padY = num(pseudoStyle.paddingTop) + num(pseudoStyle.paddingBottom)
      + num(pseudoStyle.borderTopWidth) + num(pseudoStyle.borderBottomWidth);
    let width = num(pseudoStyle.width);
    let height = num(pseudoStyle.height);
    if (!width && content) {
      if (measureContext) {
        measureContext.font = pseudoStyle.font || `${pseudoStyle.fontSize} ${pseudoStyle.fontFamily}`;
        width = measureContext.measureText(content).width;
      } else width = content.length * Math.max(6, num(pseudoStyle.fontSize) * 0.55);
    }
    if (!height && content) height = num(pseudoStyle.lineHeight) || num(pseudoStyle.fontSize) * 1.2;
    width += padX;
    height += padY;
    let left = origin.left;
    let top = origin.top;
    if (pseudoStyle.left !== 'auto') left = origin.left + num(pseudoStyle.left);
    else if (pseudoStyle.right !== 'auto') left = origin.right - num(pseudoStyle.right) - width;
    if (pseudoStyle.top !== 'auto') top = origin.top + num(pseudoStyle.top);
    else if (pseudoStyle.bottom !== 'auto') top = origin.bottom - num(pseudoStyle.bottom) - height;
    return {left, top, right: left + width, bottom: top + height, width, height};
  };
  // Graphical pseudo-element ink: `content:""` plus a painted background or
  // border. It has no DOM node, so the element scan above cannot see it, and the
  // textual pseudo pass below discards it for having no content string. That
  // blind spot let a 1x224px connector rule sit straight through three copy
  // bands on a slide that layout QA reported as clean. Measure it against the
  // text it crosses and route it through the existing decoration repair.
  for (const el of root.querySelectorAll('*')) {
    if (!isVisible(el)) continue;
    for (const pseudo of ['::before', '::after']) {
      const style = window.getComputedStyle(el, pseudo);
      if (style.content === 'none' || style.display === 'none' || style.visibility === 'hidden') continue;
      if (unquoteContent(style.content)) continue;
      if (num(style.opacity) <= HIDDEN_OPACITY) continue;
      const paints = opaqueBackground(style.backgroundColor)
        || style.backgroundImage !== 'none'
        || num(style.borderLeftWidth) > 0 || num(style.borderTopWidth) > 0;
      if (!paints) continue;
      const rect = pseudoRectFor(el, style, '');
      if (rect.width <= 0.5 || rect.height <= 0.5) continue;
      // Two shapes are worth checking. A thin rule or spine (a connector drawn
      // across the slide) and a small marker (a list bullet living in the copy's
      // left gutter). A large painted pseudo is a panel or backdrop, which is
      // meant to sit behind copy.
      const thin = Math.min(rect.width, rect.height) <= 8;
      const marker = rect.width <= 28 && rect.height <= 28;
      if (!thin && !marker) continue;
      const owner = el.closest('[data-layout-id^="scene-"]');
      if (!owner) continue;
      const sceneOwner = String(owner.getAttribute('data-layout-id') || '').replace(/^scene-/, '');
      for (let index = 0; index < elements.length; index += 1) {
        const target = elements[index];
        if (!target.textual || target.footer || target.pageNumber || target.decorative) continue;
        const targetNode = elementNodes[index];
        // A container's own pseudo painting across its children is the whole
        // point of this check (a connector rule drawn over the copy bands it
        // was meant to sit beside), so descendants are targets, not exclusions.
        if (targetNode === el || targetNode.contains(el)) continue;
        if (targetNode.closest('[data-layout-id^="scene-"]') !== owner) continue;
        // A marker is anchored in its own element's gutter, so its owner's copy
        // is exactly what it must not touch — compare against the text ink
        // rather than the block box, which would report the whole line.
        const localInk = target.ink;
        const targetRect = localInk
          ? {
              left: localInk.left + rootRect.left, right: localInk.right + rootRect.left,
              top: localInk.top + rootRect.top, bottom: localInk.bottom + rootRect.top,
              width: localInk.width, height: localInk.height,
            }
          : targetNode.getBoundingClientRect();
        // A hairline rule is 1px wide, so the shared overlap epsilon (also 1px)
        // could never register it crossing anything. Decoration ink is measured
        // exactly instead.
        const hit = intersection(rect, targetRect);
        // Measure along the rule's own long axis. A 1px horizontal rule drawn
        // through a heading overlaps it by the full run of the rule but only by
        // its own 1px thickness vertically, so a height threshold silently
        // ignored exactly the case this pass exists for: a title underline left
        // at a fixed offset while the title wrapped to three lines and grew past
        // it. A bullet is compact, so both axes stay small there.
        if (hit.width < 0.5 || hit.height < 0.5) continue;
        const reach = marker ? 2 : 6;
        if (Math.max(hit.width, hit.height) < reach) continue;
        decorationCollisions.push({
          line: `${repairSelectorFor(el)}${pseudo}`,
          target: target.id,
          width: hit.width,
          height: hit.height,
          targetSelector: repairSelectorFor(el),
          pseudo,
          sceneOwner,
          strategy: 'hide_pseudo_decoration',
        });
        break;
      }
    }
  }
  // A bullet sits in the text's own gutter, so its offset from the element's
  // left edge is of that order. 48px matches the reserve pass; beyond it the
  // shape is decoration positioned somewhere else in the box.
  const MARKER_GUTTER_MAX_LEFT_PX = 48;
  // A bullet drawn as a painted ::before must stay in the gutter its element's
  // padding reserves for it. When the gutter is narrower than the marker the
  // bullet is printed over the first characters of the copy.
  for (const el of root.querySelectorAll('*')) {
    if (!isVisible(el) || isDecorative(el)) continue;
    const owner = el.closest('[data-layout-id^="scene-"]');
    if (!owner) continue;
    const ink = inkRectFor(el);
    if (!ink) continue;
    for (const pseudo of ['::before', '::after']) {
      const style = window.getComputedStyle(el, pseudo);
      if (style.content === 'none' || style.display === 'none' || style.visibility === 'hidden') continue;
      if (style.position !== 'absolute' || style.left === 'auto') continue;
      if (num(style.opacity) <= HIDDEN_OPACITY) continue;
      const paints = opaqueBackground(style.backgroundColor)
        || style.backgroundImage !== 'none' || num(style.borderLeftWidth) > 0;
      if (!paints) continue;
      const rect = pseudoRectFor(el, style, unquoteContent(style.content));
      // A marker is compact. A long rule that happens to be narrow is a
      // connector or spine, and widening the copy's gutter by its length would
      // destroy the layout — that shape belongs to the decoration pass.
      if (rect.width <= 0.5 || rect.width > 32 || rect.height > 32) continue;
      const elementRect = el.getBoundingClientRect();
      // …and it lives in the gutter the element's padding reserves. A compact
      // ::after pinned to a panel's *right* edge is a corner tick; measuring it
      // as a bullet reported the whole panel width as an overlap (433px) and
      // asked for a padding-left to match, which would have emptied the panel.
      if (num(style.left) > MARKER_GUTTER_MAX_LEFT_PX) continue;
      // A gutter collision is a real intersection, not a 1-D comparison: the
      // marker has to sit on the same rows as the copy it is said to cover.
      const markerTop = rect.top - rootRect.top;
      const markerBottom = rect.bottom - rootRect.top;
      if (markerBottom <= ink.top || markerTop >= ink.top + ink.height) continue;
      const markerRight = +(rect.right - rootRect.left).toFixed(2);
      const overlap = +(markerRight - ink.left).toFixed(2);
      if (overlap <= 0.25) continue;
      const needed = +(markerRight - (elementRect.left - rootRect.left) + 4).toFixed(2);
      pseudoIssues.push({
        type: 'marker_gutter_collision',
        selector: repairSelectorFor(el),
        pseudo,
        content: '',
        sceneOwner: String(owner.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
        box: localRect(rect),
        overlap: {width: overlap, height: +Math.min(rect.height, ink.height).toFixed(2)},
        strategy: 'reserve_marker_gutter',
        suggestedPaddingLeft: Math.max(0, needed),
      });
      break;
    }
  }
  for (const el of root.querySelectorAll('*')) {
    // Decorative hosts can still own textual pseudos (legend captions,
    // temperature labels, axis annotations). The pseudo itself must be
    // measured even when the empty/background host is decorative.
    if (!isVisible(el)) continue;
    for (const pseudo of ['::before', '::after']) {
      const style = window.getComputedStyle(el, pseudo);
      const content = unquoteContent(style.content);
      if (!content || style.display === 'none' || style.visibility === 'hidden') continue;
      const rect = pseudoRectFor(el, style, content);
      if (rect.width <= 0.5 || rect.height <= 0.5) continue;
      const owner = el.closest('[data-layout-id^="scene-"]');
      const sceneOwner = owner
        ? String(owner.getAttribute('data-layout-id') || '').replace(/^scene-/, '') : '';
      const selector = repairSelectorFor(el);
      const box = localRect(rect);
      if (/[→←↗↘↔➜➝➞]/.test(content) && opaqueBackground(style.backgroundColor)) {
        pseudoIssues.push({
          type: 'connector_mask', selector, pseudo, content: content.slice(0, 40),
          sceneOwner, box, strategy: 'transparent_background',
        });
      }
      if (owner === el && String(el.getAttribute('data-layout-role') || '').toLowerCase() === 'title') {
        const headingNodes = [...el.querySelectorAll('h1,h2,h3')].filter(isVisible);
        const anchorNodes = headingNodes.length
          ? headingNodes : [...el.querySelectorAll('p')].filter(isVisible);
        const anchor = anchorNodes
          .map((node) => ({node, box: node.getBoundingClientRect()}))
          .filter((item) => (
            Math.min(rect.right, item.box.right) - Math.max(rect.left, item.box.left) > 8
            && rect.top >= item.box.top
          ))
          .sort((left, right) => right.box.bottom - left.box.bottom)[0];
        if (anchor) {
          const textBox = anchor.box;
          const gap = rect.top - textBox.bottom;
          const currentTop = style.top === 'auto' ? null : num(style.top);
          if (gap < settings.minTextGap - 0.5) {
            // Keep a two-pixel rounding reserve across Chromium and the PPTX
            // integer EMU grid; otherwise an exact 16.00 target can remeasure
            // as 15.999 and trigger an endless no-op repair.
            const needed = settings.minTextGap - gap + 2;
            const suggestedTop = currentTop == null ? null : currentTop + needed;
            pseudoIssues.push({
              type: 'text_proximity', selector, pseudo, content: content.slice(0, 80),
              sceneOwner, box, gap: +gap.toFixed(2), minGap: settings.minTextGap,
              suggestedTop: suggestedTop == null ? null : +suggestedTop.toFixed(2),
              strategy: 'increase_top',
            });
          } else if (gap > settings.maxTextGap + 0.5) {
            const suggestedTop = currentTop == null
              ? null : currentTop - (gap - settings.preferredTextGap);
            pseudoIssues.push({
              type: 'text_separation', selector, pseudo, content: content.slice(0, 80),
              sceneOwner, box, gap: +gap.toFixed(2), maxGap: settings.maxTextGap,
              suggestedTop: suggestedTop == null ? null : +suggestedTop.toFixed(2),
              strategy: 'decrease_top',
            });
          }
        }
      }
      if (style.position === 'absolute' || style.position === 'fixed') {
        const hostRect = el.getBoundingClientRect();
        // Constrain to the element's own positioned parent, not merely to the
        // scene region: a card's ornament must stay in that card.
        const regionRect = owner ? owner.getBoundingClientRect() : rootRect;
        const offsetOwner = el.offsetParent;
        const sceneRect = (offsetOwner && owner && owner.contains(offsetOwner) && offsetOwner !== owner)
          ? (() => {
              const b = offsetOwner.getBoundingClientRect();
              const left = Math.max(regionRect.left, b.left);
              const top = Math.max(regionRect.top, b.top);
              const right = Math.min(regionRect.right, b.right);
              const bottom = Math.min(regionRect.bottom, b.bottom);
              return (right - left < 4 || bottom - top < 4)
                ? regionRect
                : {left, top, right, bottom, width: right - left, height: bottom - top};
            })()
          : regionRect;
        const textCandidates = elements
          .filter((item) => item.textual && (!sceneOwner || item.sceneRole === sceneOwner))
          .map((item) => {
            let node = null;
            try { node = document.querySelector(item.repairSelector); } catch (_) {}
            return {item, node};
          })
          .filter(({node}) => (
            node && node !== el && !node.contains(el) && !el.contains(node) && isVisible(node)
          ));
        const overlapsText = (candidateRect) => textCandidates
          .map(({item, node}) => ({
            item, node,
            overlap: rectIntersects(candidateRect, node.getBoundingClientRect())
              ? intersection(candidateRect, node.getBoundingClientRect())
              : {width: 0, height: 0},
          }))
          .filter(({overlap}) => overlap.width > settings.overlapEpsilon && overlap.height > settings.overlapEpsilon)
          .sort((a, b) => (
            (a.overlap.width * a.overlap.height) - (b.overlap.width * b.overlap.height)
          ));
        const currentHits = overlapsText(rect);
        if (
          !pseudoHostDecorationSeen.has(el)
          && painted(el, css(el))
          && (css(el).position === 'absolute' || css(el).position === 'fixed')
        ) {
          const hostHits = overlapsText(hostRect);
          if (hostHits.length) {
            const offsetParent = el.offsetParent || owner || root;
            const offsetRect = offsetParent.getBoundingClientRect();
            const hostCandidates = [2, 4, 8, 12].map((gap) => ({
              top: hostHits[0].node.getBoundingClientRect().bottom + gap,
            })).concat([2, 4, 8, 12].map((gap) => ({
              top: hostHits[0].node.getBoundingClientRect().top - hostRect.height - gap,
            })));
            const hostFree = hostCandidates.find((candidate) => {
              const candidateRect = {
                left: hostRect.left, top: candidate.top,
                right: hostRect.right, bottom: candidate.top + hostRect.height,
                width: hostRect.width, height: hostRect.height,
              };
              return candidateRect.top >= sceneRect.top - 0.5
                && candidateRect.bottom <= sceneRect.bottom + 0.5
                && overlapsText(candidateRect).length === 0;
            });
            if (hostFree) {
              const hostHit = hostHits[0];
              decorationCollisions.push({
                line: idFor(el, -1), target: hostHit.item.id,
                width: +hostHit.overlap.width.toFixed(2),
                height: +hostHit.overlap.height.toFixed(2),
                targetSelector: repairSelectorFor(el), sceneOwner,
                strategy: 'move_decoration_absolute',
                suggestedTop: +(hostFree.top - offsetRect.top).toFixed(2),
              });
              pseudoHostDecorationSeen.add(el);
            }
          }
        }
        if (currentHits.length) {
          const freeCandidates = [4, 8, 12].map((gap) => ({
            strategy: 'set_top',
            suggestedTop: hostRect.height + gap,
            rect: {
              left: rect.left, top: hostRect.bottom + gap,
              right: rect.right, bottom: hostRect.bottom + gap + rect.height,
              width: rect.width, height: rect.height,
            },
          })).concat([4, 8, 12].map((gap) => ({
            strategy: 'set_top',
            suggestedTop: -rect.height - gap,
            rect: {
              left: rect.left, top: hostRect.top - rect.height - gap,
              right: rect.right, bottom: hostRect.top - gap,
              width: rect.width, height: rect.height,
            },
          })));
          const free = freeCandidates.find((candidate) => (
            candidate.rect.left >= sceneRect.left - 0.5
            && candidate.rect.right <= sceneRect.right + 0.5
            && candidate.rect.top >= sceneRect.top - 0.5
            && candidate.rect.bottom <= sceneRect.bottom + 0.5
            && overlapsText(candidate.rect).length === 0
          ));
          const hit = currentHits[0];
          pseudoIssues.push({
            type: 'pseudo_text_collision', selector, pseudo,
            content: content.slice(0, 80), sceneOwner, box,
            against: hit.item.id,
            overlap: {
              width: +hit.overlap.width.toFixed(2),
              height: +hit.overlap.height.toFixed(2),
            },
            strategy: free ? free.strategy : (
              /[→←↗↘↔➜➝➞]/.test(content)
                || isDecorative(el) || !String(el.textContent || '').trim()
                ? 'hide_pseudo_text' : 'manual_reflow'
            ),
            suggestedTop: free ? +free.suggestedTop.toFixed(2) : null,
          });
        }
      }
    }
  }

  // A circular or pill container holds text inside the shape, not inside its
  // bounding box: a 52px circle only fits a 36.8px square (diameter / sqrt2).
  // Measuring against the box therefore calls a badge "fitting" while its copy
  // visibly crosses the curve. Decorative status is irrelevant here — the text
  // is read either way — so this pass looks at every round container.
  const roundOverflows = [];
  for (const el of root.querySelectorAll('*')) {
    if (!isVisible(el)) continue;
    // Decorative ink is not audience copy, and the authoring contract says so
    // outright. A purely ornamental ring holding a decorative "?" glyph was
    // reported as copy that needs 241px inside a 232px circle — there is no
    // copy to fit and nothing a font-size repair could achieve, which is why
    // the pass kept being emitted and rejected. The ring is still reported once,
    // as ambient decoration, where the judgement belongs to the author.
    if (isDecorative(el)) continue;
    const style = css(el);
    const rect = el.getBoundingClientRect();
    if (rect.width < 12 || rect.height < 12) continue;
    const radius = num(style.borderTopLeftRadius);
    const isPercent = String(style.borderTopLeftRadius || '').includes('%');
    const shortest = Math.min(rect.width, rect.height);
    const round = isPercent ? radius >= 50 : radius >= shortest / 2 - 0.5;
    if (!round) continue;
    const ink = inkRectFor(el);
    if (!ink) continue;
    const border = num(style.borderTopWidth) + num(style.borderBottomWidth);
    const inscribed = Math.max(1, (shortest - border) / Math.SQRT2);
    const needed = Math.max(ink.width, ink.height);
    if (needed <= inscribed + 0.5) continue;
    const fontSize = num(style.fontSize);
    roundOverflows.push({
      selector: repairSelectorFor(el),
      sceneOwner: String(el.closest('[data-layout-id^="scene-"]')?.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
      inkWidth: +ink.width.toFixed(2),
      inkHeight: +ink.height.toFixed(2),
      inscribed: +inscribed.toFixed(2),
      fontSize: +fontSize.toFixed(2),
      lineHeight: +num(style.lineHeight).toFixed(2),
      // Carried so a shrink can keep tracking proportional. Left absolute, a
      // negative letter-spacing crushes the glyphs it was tuned for at the
      // authored size — "61,3%" came out as one blot.
      letterSpacing: +num(style.letterSpacing).toFixed(3),
      centersWithLineHeight: centersTextWithLineHeight(el, style),
      // Shrink type to the shape rather than growing the shape, which would
      // move whatever the badge is anchored between.
      suggestedFontSize: +Math.max(9, fontSize * (inscribed / needed)).toFixed(2),
      strategy: 'shrink_to_inscribed',
    });
  }

  // A table host is a frame sized by the author before the table existed, so a
  // shorter table leaves the panel padded out with dead white space — the
  // reported "table does not fit its canvas" is really the canvas not fitting
  // the table. Figure hosts are deliberately excluded: an image is scaled to
  // fill its frame, so the frame is the design. Report the slack so the host
  // can hug the rows it actually received.
  const hostSlack = [];
  for (const host of root.querySelectorAll('[data-pptx="table"]')) {
    if (!isVisible(host)) continue;
    const table = host.querySelector('table');
    if (!table) continue;
    const hostRect = host.getBoundingClientRect();
    const tableRect = table.getBoundingClientRect();
    const style = css(host);
    const chrome = num(style.paddingTop) + num(style.paddingBottom)
      + num(style.borderTopWidth) + num(style.borderBottomWidth);
    const needed = tableRect.height + chrome;
    const slack = hostRect.height - needed;
    // Ignore rounding; a host is only over-tall when the gap is visible.
    if (slack <= 24) continue;
    hostSlack.push({
      selector: repairSelectorFor(host),
      sceneOwner: String(host.closest('[data-layout-id^="scene-"]')?.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
      hostHeight: +hostRect.height.toFixed(2),
      contentHeight: +needed.toFixed(2),
      slack: +slack.toFixed(2),
      suggestedHeight: +needed.toFixed(2),
      strategy: 'hug_table_content',
    });
  }

  // Legibility. Every other check here measures geometry — boxes, ink, overlap,
  // overflow — and not one of them asks whether the reader can read the words.
  // A full-width sentence laid across a floating dark panel is grey on navy at
  // a contrast ratio of 1.6; a badge numeral is white on near-white at 1.07.
  // Both are invisible, and both passed every geometric gate on this page.
  //
  // The surface is sampled *behind the glyphs* at several points along each
  // line, because a line can begin on a light card and end on a dark one — an
  // element's own `background-color` says nothing about what is under it.
  const parseRgba = (color) => {
    const parts = String(color || '').match(/[\d.]+/g);
    if (!parts || parts.length < 3) return null;
    return {
      r: Number(parts[0]), g: Number(parts[1]), b: Number(parts[2]),
      a: parts.length >= 4 ? Number(parts[3]) : 1,
    };
  };
  const relativeLuminance = (rgb) => {
    if (!rgb) return null;
    const channel = (value) => {
      const v = value / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b);
  };
  /**
   * The colour actually under a point, compositing every translucent layer.
   *
   * Reading a layer's own `background-color` is not enough: a 10%-white veil
   * over a navy panel reports as `rgba(255,255,255,0.1)`, and taken at face
   * value that made white copy on a dark card look like white-on-white. Alpha
   * has to be composited, not merely tested for zero.
   */
  const surfaceBehind = (el, x, y) => {
    const stack = [];
    let owner = null;
    for (const node of document.elementsFromPoint(x, y)) {
      // The element's *own* background is the first layer under its glyphs —
      // a table header's navy fill, a badge's disc. Excluding it made every
      // white-on-navy header read as white-on-white.
      if (el.contains(node) && node !== el) continue;
      const layer = parseRgba(css(node).backgroundColor);
      if (!layer || layer.a === 0) continue;
      if (!owner && node !== el) owner = node;
      stack.push(layer);
      if (layer.a >= 0.999) break;
    }
    let composite = {r: 255, g: 255, b: 255, a: 1};
    for (let index = stack.length - 1; index >= 0; index -= 1) {
      const layer = stack[index];
      composite = {
        r: layer.r * layer.a + composite.r * (1 - layer.a),
        g: layer.g * layer.a + composite.g * (1 - layer.a),
        b: layer.b * layer.a + composite.b * (1 - layer.a),
        a: 1,
      };
    }
    return {rgb: composite, node: owner};
  };
  const textContrast = [];
  {
    const reported = new Set();
    for (const node of root.querySelectorAll('*')) {
      if (!isVisible(node) || isDecorative(node)) continue;
      const ownsText = [...node.childNodes].some(
        (child) => child.nodeType === 3 && String(child.textContent || '').trim()
      );
      if (!ownsText) continue;
      const style = css(node);
      const inkColor = parseRgba(style.color);
      // Text drawn at partial alpha is a deliberate de-emphasis, not a defect.
      if (!inkColor || inkColor.a < 0.9) continue;
      const ink = relativeLuminance(inkColor);
      if (ink === null) continue;
      let range;
      try {
        range = document.createRange();
        range.selectNodeContents(node);
      } catch {
        continue;
      }
      for (const rect of range.getClientRects()) {
        if (rect.width < 4 || rect.height < 4) continue;
        let worst = Infinity;
        let worstSurface = null;
        for (const fraction of [0.05, 0.3, 0.5, 0.7, 0.95]) {
          const surface = surfaceBehind(
            node, rect.left + rect.width * fraction, rect.top + rect.height / 2
          );
          const behind = relativeLuminance(surface.rgb);
          if (behind === null) continue;
          const ratio = (Math.max(ink, behind) + 0.05) / (Math.min(ink, behind) + 0.05);
          if (ratio < worst) {
            worst = ratio;
            worstSurface = surface;
          }
        }
        if (!Number.isFinite(worst) || worst >= settings.minTextContrast) continue;
        // One formula is one defect, not one per glyph: MathML leaves are
        // separate elements and an invisible formula reported 15 times.
        // Attribute to the formula, or to the semantic host that owns it.
        const grouped = node.closest('math, [data-pptx]') || node;
        const selector = repairSelectorFor(grouped);
        if (reported.has(selector)) continue;
        reported.add(selector);
        // Whose surface is it? A card the text lives inside was coloured
        // together with it, so the ink is what to change. A panel the text
        // merely crosses was never meant to be under it, and the honest fix is
        // to stop the text at the panel's edge.
        const owner = worstSurface ? worstSurface.node : null;
        const trespass = Boolean(owner) && !owner.contains(node);
        textContrast.push({
          selector,
          sceneOwner: String(
            node.closest('[data-layout-id]')?.getAttribute('data-layout-id') || ''
          ).replace(/^scene-/, ''),
          ratio: +worst.toFixed(2),
          color: style.color,
          surface: worstSurface
            ? `rgb(${Math.round(worstSurface.rgb.r)}, ${Math.round(worstSurface.rgb.g)}, ${Math.round(worstSurface.rgb.b)})`
            : null,
          text: String(node.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60),
          trespass,
          surfaceSelector: owner ? repairSelectorFor(owner) : null,
          surfaceLeft: owner ? localRect(owner.getBoundingClientRect()).left : null,
          boxLeft: localRect(node.getBoundingClientRect()).left,
          strategy: trespass ? 'stop_text_before_surface' : 'recolour_text_for_surface',
        });
        break;
      }
    }
  }

  // The inverse of hostSlack: a semantic host too *short* for what the pipeline
  // put in it. The author sizes the host before the content exists, so its
  // height is a guess and the content is real — a 56px formula host received
  // math whose ink spans 60px, and the sigma's upper limit was drawn above the
  // band. Upward bleed is invisible to the scroll-extent checks, which only
  // look downward, so it is measured here against the host's own bounds.
  const hostShortfall = [];
  for (const host of root.querySelectorAll('[data-pptx="formula"], [data-pptx="chart"], [data-pptx="figure"]')) {
    if (!isVisible(host)) continue;
    const ink = inkRectFor(host);
    if (!ink) continue;
    const hostRect = host.getBoundingClientRect();
    const localHost = localRect(hostRect);
    const above = localHost.top - ink.top;
    const below = ink.bottom - localHost.bottom;
    const shortfall = Math.max(0, above) + Math.max(0, below);
    // Ink taller than the host is the precondition: a 23px formula centred in
    // a 120px host bleeds a pixel at one edge without the host being short of
    // anything, and reporting that is a false alarm on every roomy host.
    if (ink.height <= localHost.height + 1) continue;
    if (shortfall <= 2) continue;
    hostShortfall.push({
      selector: repairSelectorFor(host),
      kind: String(host.getAttribute('data-pptx') || ''),
      sceneOwner: String(host.closest('[data-layout-id^="scene-"]')?.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
      hostHeight: +hostRect.height.toFixed(2),
      contentHeight: +(ink.bottom - ink.top).toFixed(2),
      above: +Math.max(0, above).toFixed(2),
      below: +Math.max(0, below).toFixed(2),
      suggestedHeight: +(hostRect.height + shortfall).toFixed(2),
      strategy: 'grow_host_to_content',
    });
  }

  // A chart drawn by hand. A quantitative figure has to come from its data —
  // the pipeline has a chart host that carries the numbers and exports a native,
  // editable PPTX chart. What is measured here is the alternative the author
  // reaches for when no host was offered: a coloured bar rotated to an arbitrary
  // angle to fake a trend line. Its geometry answers to nothing, so the lines
  // ran outside their own axes and past the callout beneath them.
  //
  // Rotation is the fingerprint. Decoration does not tilt a thin rule to -18deg;
  // a plotted line does.
  const freehandCharts = [];
  {
    // An axis is the anchor of the fingerprint: a box with a bottom and a left
    // border and nothing on the other two sides is an L, and an L is drawn for
    // exactly one reason. Collected first, because whether a tilted rule is
    // ornament or a plotted line is decided by whether it sits in one.
    const axisBoxes = [];
    for (const node of root.querySelectorAll('*')) {
      if (!isVisible(node)) continue;
      const style = css(node);
      if (!(num(style.borderBottomWidth) > 0 && num(style.borderLeftWidth) > 0
        && num(style.borderTopWidth) === 0 && num(style.borderRightWidth) === 0)) continue;
      axisBoxes.push(node);
    }
    const insideAxis = (node) => axisBoxes.some((axis) => axis.contains(node));

    const byRegion = new Map();
    for (const node of root.querySelectorAll('*')) {
      if (!isVisible(node)) continue;
      if (String(node.textContent || '').trim()) continue;
      // Ornament the author declared as ornament is ornament -- a cover's tilted
      // route lines all carry data-pptx-kind="decoration". But the marker is the
      // author's word, not a fact: the deck that prompted this drew its trend
      // lines inside an aria-hidden decoration wrapper, and calling a plot
      // decoration does not make it one. Inside an axis, the marker is ignored.
      if ((node.closest('[data-pptx-kind="decoration"]') || isDecorative(node)) && !insideAxis(node)) continue;
      const style = css(node);
      if (!painted(node, style)) continue;
      const transform = style.transform;
      if (!transform || transform === 'none') continue;
      const matrix = transform.match(/matrix\(([^)]+)\)/);
      if (!matrix) continue;
      const parts = matrix[1].split(',').map((value) => Number.parseFloat(value.trim()));
      if (parts.length < 4) continue;
      // b or c non-zero means the box is rotated or skewed off-axis.
      const angle = Math.abs(Math.atan2(parts[1], parts[0]) * (180 / Math.PI));
      if (angle < 3 || angle > 87) continue;
      // The element's own box, not the rotated one: getBoundingClientRect
      // returns the axis-aligned bounds *after* rotation, so a 3x300px rule
      // tilted 18deg measures 318x106 and never looks thin. offsetWidth and
      // offsetHeight ignore the transform, which is exactly what is needed to
      // recognise the shape that was rotated.
      const own = {width: node.offsetWidth || 0, height: node.offsetHeight || 0};
      const thin = Math.min(own.width, own.height);
      const long = Math.max(own.width, own.height);
      if (thin > 8 || long < 24) continue;
      const region = node.closest('[data-layout-id]');
      const regionId = String(region?.getAttribute('data-layout-id') || '').replace(/^scene-/, '');
      // A region that owns a real chart host is doing it properly.
      if (region && region.querySelector('[data-pptx="chart"]')) continue;
      if (node.closest('[data-pptx]')) continue;
      const bucket = byRegion.get(regionId) || {region, lines: []};
      bucket.lines.push({selector: repairSelectorFor(node), angle: +angle.toFixed(1)});
      byRegion.set(regionId, bucket);
    }
    // Requiring an axis in the same region alongside the rotated rules is what
    // separates a plot from decorative line art.
    const hasAxis = (region) => axisBoxes.some((axis) => (region || root).contains(axis));
    for (const [regionId, bucket] of byRegion) {
      const lines = bucket.lines;
      if (!lines.length) continue;
      if (!hasAxis(bucket.region)) continue;
      freehandCharts.push({
        sceneOwner: regionId,
        lines: lines.length,
        selectors: lines.map((line) => line.selector).slice(0, 4),
        angles: lines.map((line) => line.angle).slice(0, 4),
        strategy: 'use_chart_host',
      });
    }
  }

  // Ambient geometry: a large round shape that carries no text, indexes nothing
  // and simply sits behind the content. The author contract forbids it — a
  // reader asks what the circle denotes and there is no answer — so it is
  // measured here rather than left to taste.
  // Tracks that leave no room for their own gap. A grid written as
  // `grid-template-columns: 59% 41%` already claims the whole container, so any
  // column-gap pushes the last track out — and shrinking the gap can never fix
  // it, only converge on it: the deck that prompted this had five stacked
  // repairs walking 42px down to 31.2px while the overflow stayed at exactly
  // the remaining gap. The tracks are the term that has to give.
  const gridTrackOverflow = [];
  for (const node of root.querySelectorAll('*')) {
    if (!isVisible(node)) continue;
    const style = css(node);
    if (!/(^|\s)(inline-)?grid$/.test(style.display)) continue;
    const tracks = String(style.gridTemplateColumns || '')
      .split(/\s+/)
      .map((value) => num(value))
      .filter((value) => Number.isFinite(value) && value > 0);
    if (tracks.length < 2) continue;
    const gap = num(style.columnGap) || 0;
    if (gap <= 0) continue;
    const used = tracks.reduce((sum, value) => sum + value, 0) + gap * (tracks.length - 1);
    const available = node.clientWidth;
    if (!available || used <= available + 0.5) continue;
    // Same proportions, expressed as shares of the space that is actually
    // free. fr resolves after gaps are taken out, so the column that used to
    // hang over the edge now ends exactly at it.
    const total = tracks.reduce((sum, value) => sum + value, 0);
    gridTrackOverflow.push({
      selector: repairSelectorFor(node),
      sceneOwner: String(
        node.closest('[data-layout-id]')?.getAttribute('data-layout-id') || ''
      ).replace(/^scene-/, ''),
      overflow: +(used - available).toFixed(2),
      gap: +gap.toFixed(2),
      suggestedColumns: tracks
        .map((value) => `${(value / total * 100).toFixed(3)}fr`)
        .join(' '),
      strategy: 'refit_grid_tracks',
    });
  }

  // One more grid item than there are columns. A bullet row authored as
  // `grid-template-columns: 24px 1fr` with the dot drawn by ::before and a
  // blank <span> left in the markup as a spacer has three items for two
  // tracks, so the sentence wraps onto a second row and lands in the 24px
  // decoration column -- text set nine characters to the line beside a dot.
  // Chromium counts a generated box as a grid item; `children` does not list
  // one, which is why this went unmeasured. The blank span carries nothing, so
  // taking it out of the grid restores the layout the author described.
  const gridItemOverflow = [];
  for (const node of root.querySelectorAll('*')) {
    if (!isVisible(node)) continue;
    const style = css(node);
    if (!/(^|\s)(inline-)?grid$/.test(style.display)) continue;
    if (style.gridTemplateRows && /repeat|,/.test(style.gridTemplateRows)) continue;
    const columns = String(style.gridTemplateColumns || '')
      .trim()
      .split(/\s+/)
      .filter(Boolean).length;
    if (columns < 1) continue;
    const generated = ['::before', '::after'].filter((pseudo) => {
      const pseudoStyle = css(node, pseudo);
      if (!pseudoStyle) return false;
      const content = String(pseudoStyle.content || 'none');
      return content !== 'none' && content !== 'normal' && pseudoStyle.display !== 'none';
    }).length;
    // A grid item is a laid-out, in-flow child. `display:none` children are not
    // items at all -- counting them meant a dropped spacer kept being reported
    // as though it were still taking a track.
    const items = [...node.children].filter((child) => {
      const childStyle = css(child);
      return childStyle.position === 'static' && childStyle.display !== 'none';
    });
    const total = items.length + generated;
    if (total <= columns) continue;
    // Only an item that carries nothing may be dropped: no text, no children,
    // nothing painted. Anything else is content, and content is never the
    // thing that gives way.
    const spare = items.find((child) => {
      if (child.children.length) return false;
      if (String(child.textContent || '').trim()) return false;
      const childStyle = css(child);
      // Size is no guide: an empty span is stretched to whatever track holds
      // it, and the one that caused this was 466px wide. Emptiness is the test.
      return !painted(child, childStyle);
    });
    if (!spare) continue;
    gridItemOverflow.push({
      selector: repairSelectorFor(node),
      spareSelector: repairSelectorFor(spare),
      sceneOwner: String(
        node.closest('[data-layout-id]')?.getAttribute('data-layout-id') || ''
      ).replace(/^scene-/, ''),
      columns,
      items: total,
      strategy: 'drop_empty_grid_item',
    });
  }

  const ambientDecoration = [];
  for (const node of root.querySelectorAll('*')) {
    if (!isVisible(node)) continue;
    if (String(node.textContent || '').trim()) continue;
    const style = css(node);
    const rect = node.getBoundingClientRect();
    if (rect.width < 96 || rect.height < 96) continue;
    // Round: a circle, a ring, an orbit, an arc. A computed radius keeps the
    // author's unit, so `border-radius:50%` arrives as "50%" — read as 50px it
    // failed this test for every shape wider than 125px, which is every shape
    // this check exists to find.
    const declaredRadius = String(style.borderTopLeftRadius || '');
    const shortest = Math.min(rect.width, rect.height);
    const radiusPx = declaredRadius.endsWith('%')
      ? (num(declaredRadius) / 100) * shortest
      : num(declaredRadius);
    if (radiusPx < shortest * 0.4) continue;
    if (!painted(node, style)) continue;
    // A round box that hosts something (a chart, a figure, an avatar) is not
    // ambient; only an empty one with nothing inside it is.
    if (node.querySelector('img,svg,canvas,table,[data-pptx]')) continue;
    if (node.closest('[data-pptx]')) continue;
    ambientDecoration.push({
      selector: repairSelectorFor(node),
      box: localRect(rect),
      diameter: +Math.max(rect.width, rect.height).toFixed(1),
      sceneOwner: String(
        node.closest('[data-layout-id]')?.getAttribute('data-layout-id') || ''
      ).replace(/^scene-/, ''),
      strategy: 'hide_decoration',
    });
  }

  // A content region whose copy runs past its own bottom edge has more in it
  // than it can hold, and the last line ends up flush against the next band.
  // Only content regions: a title or lede region is authored at exactly the
  // lines it carries, so its descenders always reach the edge — measuring the
  // whole deck, 11 of 14 slides had such a region, and a rule that fires on 11
  // of 14 slides teaches the reader to ignore it.
  const CONTENT_REGION_ROLES = new Set([
    'primary', 'secondary', 'table', 'figure', 'chart', 'formula',
  ]);
  const SCENE_LANE_ROLES = new Set(['title', 'lede', 'byline']);
  const regionOverruns = [];
  for (const region of root.querySelectorAll('[data-layout-id^="scene-"]')) {
    const role = String(region.getAttribute('data-layout-role') || '');
    // Reclaiming padding is a content-region move: a title or lede lane is one
    // line tall by contract and has no slack to redistribute. Lifting a
    // contentless decoration out of the flow is not -- a single-line lane is
    // exactly where a hairline accent does the most damage, because the lane
    // has no room to absorb it at all.
    const contentRegion = CONTENT_REGION_ROLES.has(role);
    if (!contentRegion && !SCENE_LANE_ROLES.has(role)) continue;
    const bottom = region.getBoundingClientRect().bottom;
    let deepest = -Infinity;
    let deepestNode = null;
    for (const node of region.querySelectorAll('*')) {
      if (!isVisible(node) || isDecorative(node)) continue;
      const ownsText = [...node.childNodes].some(
        (child) => child.nodeType === 3 && String(child.textContent || '').trim()
      );
      if (!ownsText) continue;
      try {
        const range = document.createRange();
        range.selectNodeContents(node);
        for (const rect of range.getClientRects()) {
          if (rect.width > 0.5 && rect.height > 0.5 && rect.bottom > deepest) {
            deepest = rect.bottom;
            deepestNode = node;
          }
        }
      } catch {
        /* skip */
      }
    }
    if (deepest === -Infinity || !deepestNode) continue;
    const overrun = deepest - bottom;
    if (overrun <= 0.5) continue;
    // Trimming the deepest *text* element's padding rarely helps: the overrun
    // is the whole stack being too tall, and a negative margin on the last
    // block moves what follows it, not the block itself. Walk up to the first
    // ancestor inside the region that actually carries vertical padding — that
    // is the whitespace the stack can give back without touching a glyph.
    // The region itself is a candidate: its box is Scene-owned and immutable,
    // but the padding *inside* it is not part of that contract, and it is
    // usually where the room is — one region carried 23.5px top and 20.7px
    // bottom padding while its copy ran 4.6px past the edge. Excluding it left
    // the walk with no donor at all and the overrun unrepairable.
    let donor = deepestNode;
    let donorStyle = css(donor);
    let padded = false;
    for (let node = deepestNode; node; node = node.parentElement) {
      const nodeStyle = css(node);
      if (num(nodeStyle.paddingTop) + num(nodeStyle.paddingBottom) >= overrun + 12) {
        donor = node;
        donorStyle = nodeStyle;
        padded = true;
        break;
      }
      if (node === region) break;
    }
    if (!padded || !contentRegion) {
      // No padding to give. Before the copy is asked to shrink, look at what
      // else is taking room in the lane: an in-flow decoration -- a hairline
      // accent above a lede, say -- occupies its own height plus its margins
      // while carrying nothing a reader needs. In a lane sized for exactly one
      // line, that hairline *is* the overflow. Taking it out of flow keeps it
      // on the slide, painting exactly where it painted before, and gives the
      // sentence back the room it was pushed out of.
      let lifted = null;
      for (const node of region.children) {
        if (!isVisible(node)) continue;
        if (String(node.textContent || '').trim()) continue;
        const nodeStyle = css(node);
        if (nodeStyle.position !== 'static') continue;
        if (!painted(node, nodeStyle)) continue;
        const nodeRect = node.getBoundingClientRect();
        const regionTop = region.getBoundingClientRect().top;
        const footprint = nodeRect.height
          + num(nodeStyle.marginTop) + num(nodeStyle.marginBottom);
        if (footprint + 0.5 < overrun) continue;
        // Taking the decoration out of flow pulls everything below it *up* by
        // its footprint -- including the sentence it was sitting above. Leaving
        // the rule painted where it was would then lay it across that sentence:
        // the overflow traded for a strikethrough. Only lift when the copy's
        // ink, at the position it will actually occupy afterwards, clears the
        // band the rule will keep painting in.
        let inkTop = Infinity;
        try {
          const range = document.createRange();
          range.selectNodeContents(deepestNode);
          for (const rect of range.getClientRects()) {
            if (rect.width > 0.5 && rect.height > 0.5) inkTop = Math.min(inkTop, rect.top);
          }
        } catch {
          /* skip */
        }
        if (!Number.isFinite(inkTop)) continue;
        if (nodeRect.bottom > inkTop - footprint + 0.5) continue;
        lifted = {
          selector: repairSelectorFor(node),
          top: +(nodeRect.top - regionTop).toFixed(2),
        };
        break;
      }
      if (lifted) {
        regionOverruns.push({
          region: String(region.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
          selector: lifted.selector,
          deepestSelector: repairSelectorFor(deepestNode),
          overrun: +overrun.toFixed(2),
          regionHeight: +region.getBoundingClientRect().height.toFixed(2),
          suggestedTop: lifted.top,
          sceneOwner: String(region.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
          strategy: 'lift_decoration_out_of_flow',
        });
        continue;
      }
    }
    if (!contentRegion) continue;
    regionOverruns.push({
      region: String(region.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
      selector: repairSelectorFor(donor),
      deepestSelector: repairSelectorFor(deepestNode),
      overrun: +overrun.toFixed(2),
      regionHeight: +region.getBoundingClientRect().height.toFixed(2),
      paddingTop: num(donorStyle.paddingTop),
      paddingBottom: num(donorStyle.paddingBottom),
      sceneOwner: String(region.getAttribute('data-layout-id') || '').replace(/^scene-/, ''),
      strategy: 'reclaim_region_overrun',
    });
  }

  return {
    available: true,
    canvas: {width: +rootRect.width.toFixed(2), height: +rootRect.height.toFixed(2)},
    elements,
    ambientDecoration,
    freehandCharts,
    gridTrackOverflow,
    gridItemOverflow,
    textContrast,
    hostShortfall,
    regionOverruns,
    collisions,
    decorationCollisions,
    wordFragments,
    narrowText,
    textCollisions,
    pseudoIssues,
    deadHosts,
    roundOverflows,
    hostSlack,
  };
}
"""


def _inspect_once(doc: str, *, timeout_ms: int = 30_000) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    from tasks.html_constitution import CANVAS_H, CANVAS_W, ensure_slide_root

    doc = ensure_slide_root(doc)
    settings = {
        "overlapEpsilon": 1.0,
        "maxWordFragments": 48,
        "minTextGap": 32.0,
        "maxTextGap": 64.0,
        "preferredTextGap": 40.0,
        "minLabelGap": 16.0,
        # WCAG AA asks 4.5:1 for body copy. This gate is deliberately looser:
        # it is here to catch text that cannot be read at all — grey on navy at
        # 1.6, white on near-white at 1.07 — not to arbitrate design taste.
        "minTextContrast": 3.0,
    }
    with tempfile.TemporaryDirectory(prefix="sunairum_html_layout_") as tmp:
        html_path = Path(tmp) / "slide.html"
        html_path.write_text(doc, encoding="utf-8")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-dev-shm-usage", "--no-sandbox"],
            )
            try:
                page = browser.new_page(viewport={"width": CANVAS_W, "height": CANVAS_H})
                page.goto(html_path.resolve().as_uri(), wait_until="load", timeout=timeout_ms)
                page.wait_for_timeout(50)
                report = page.evaluate(_INSPECTION_SCRIPT, settings)
            finally:
                browser.close()
    return report if isinstance(report, dict) else {"available": False, "error": "invalid_report"}


def _inspect_subprocess(doc: str, *, timeout_ms: int) -> dict[str, Any]:
    """Use a fresh process so Playwright is safe inside a Celery prefork worker."""
    with tempfile.TemporaryDirectory(prefix="sunairum_html_layout_sub_") as tmp:
        input_path = Path(tmp) / "slide.html"
        output_path = Path(tmp) / "report.json"
        # ``inspect.py`` would shadow Python's stdlib inspect module because the
        # script directory is first on sys.path. Playwright imports stdlib
        # inspect while loading sync_api._generated, so use a collision-free name.
        runner = Path(tmp) / "runtime_layout_probe.py"
        input_path.write_text(doc, encoding="utf-8")
        runner.write_text(
            "import json, sys\n"
            "from tasks.html_runtime_layout import _inspect_once\n"
            "doc=open(sys.argv[1], encoding='utf-8').read()\n"
            "result=_inspect_once(doc, timeout_ms=int(sys.argv[3]))\n"
            "open(sys.argv[2], 'w', encoding='utf-8').write(json.dumps(result))\n",
            encoding="utf-8",
        )
        env = dict(os.environ)
        fastapi_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = fastapi_root + os.pathsep + env.get("PYTHONPATH", "")
        completed = subprocess.run(
            [sys.executable, str(runner), str(input_path), str(output_path), str(timeout_ms)],
            check=False,
            capture_output=True,
            text=True,
            timeout=max(60, int(timeout_ms / 1000) + 30),
            env=env,
            cwd=fastapi_root,
        )
        if completed.returncode or not output_path.is_file():
            return {
                "available": False,
                "error": (completed.stderr or completed.stdout or "runtime_inspection_failed")[:4000],
            }
        try:
            return json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {"available": False, "error": f"runtime_report_unreadable: {exc}"}


def inspect_html_layout(doc: str, *, timeout_ms: int = 30_000, force_subprocess: bool = False) -> dict[str, Any]:
    """Return actual Chromium geometry for a rendered slide without mutating it."""
    try:
        from tasks.html_render import _sync_playwright_requires_subprocess

        use_subprocess = force_subprocess or _sync_playwright_requires_subprocess()
    except Exception:  # noqa: BLE001
        use_subprocess = force_subprocess
    try:
        return _inspect_subprocess(doc, timeout_ms=timeout_ms) if use_subprocess else _inspect_once(doc, timeout_ms=timeout_ms)
    except Exception as exc:  # noqa: BLE001
        if not use_subprocess:
            return _inspect_subprocess(doc, timeout_ms=timeout_ms)
        return {"available": False, "error": f"runtime_inspection_failed: {exc}"}
