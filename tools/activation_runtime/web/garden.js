'use strict';
// Fractal research-tree view for the Semantic Gardener. Pure layout/replay functions are
// exported for Node tests; render() builds SVG with DOM APIs only (CSP: no inline styles).
(function (root) {
  const COLORS = { cyan: '#57E0CC', amber: '#F5A623', grey: '#5B6678', pale: '#A9B6C8', violet: '#C7B8FF', ink: '#070A10', text: '#E6EDF5', muted: '#8B98AB' };
  const OP_COLOR = { PROPOSE: COLORS.pale, CHALLENGE: COLORS.amber, TEST: COLORS.cyan, PRUNE: COLORS.grey, REOPEN: COLORS.cyan, SYNTHESIZE: COLORS.violet };
  const VIEW = { w: 1000, h: 760, top: 120, bottom: 690, side: 90 };

  // Branch state as of event `t` (1-based). Evidence status is current: the ledger has no time axis here.
  function computeAt(state, t) {
    const out = {};
    const order = state.order || [];
    const limit = Math.max(0, Math.min(t, order.length));
    for (const name of Object.keys(state.branches)) out[name] = { visible: false, active: true, open: false, reopened: false, events: [], challenges: [], prunedBy: null };
    for (let i = 0; i < limit; i++) {
      const e = state.events[order[i]];
      const b = out[e.branch];
      if (!b) continue;
      if (e.operation === 'PROPOSE' || e.operation === 'SYNTHESIZE') b.visible = true;
      b.events.push(e);
      if (e.operation === 'CHALLENGE') { b.open = true; b.challenges.push(e.event_id); }
      if (e.operation === 'TEST') b.open = false;
      if (e.operation === 'PRUNE') { b.active = false; b.prunedBy = e.event_id; }
      if (e.operation === 'REOPEN') { b.active = true; b.reopened = true; }
    }
    for (const [name, b] of Object.entries(out)) b.status = state.branches[name].evidence_status;
    return out;
  }

  // Depth = longest parent chain. Leaves take sequential slots in creation order (DFS along the
  // first parent); an inner branch sits over its children; a synthesis sits between its parents.
  function layout(state) {
    const names = (state.order || []).map(id => state.events[id])
      .filter(e => e.operation === 'PROPOSE' || e.operation === 'SYNTHESIZE').map(e => e.branch)
      .filter((n, i, a) => a.indexOf(n) === i && state.branches[n]);
    const depth = {};
    const visit = n => {
      if (depth[n] !== undefined) return depth[n];
      const ps = state.branches[n].parents;
      depth[n] = ps.length ? 1 + Math.max(...ps.map(visit)) : 0;
      return depth[n];
    };
    names.forEach(visit);
    const kids = {};
    names.forEach(n => { kids[n] = []; });
    names.forEach(n => { const p = state.branches[n].parents[0]; if (p !== undefined && state.branches[n].parents.length === 1) kids[p].push(n); });
    const x = {};
    let slot = 0;
    const place = n => {
      if (!kids[n].length) { x[n] = slot++; return; }
      kids[n].forEach(place);
      x[n] = kids[n].reduce((s, k) => s + x[k], 0) / kids[n].length;
    };
    names.filter(n => !state.branches[n].parents.length).forEach(place);
    names.filter(n => state.branches[n].parents.length > 1).forEach(n => {
      const xs = state.branches[n].parents.map(p => x[p] ?? 0);
      const mean = xs.reduce((a, b) => a + b, 0) / xs.length;
      // Parents stacked on one line would hide the merge: step the synthesis aside.
      x[n] = Math.max(...xs) - Math.min(...xs) < 0.01 ? mean + 0.7 : mean;
      kids[n].forEach(place);
    });
    const maxDepth = Math.max(1, ...names.map(n => depth[n]));
    const slots = Math.max(1, ...names.map(n => x[n] ?? 0));
    const pos = {};
    for (const n of names) {
      const xs = slots <= 0 || names.length <= 1 ? VIEW.w / 2 : VIEW.side + (x[n] / slots) * (VIEW.w - 2 * VIEW.side);
      const ys = VIEW.bottom - (depth[n] / maxDepth) * (VIEW.bottom - VIEW.top);
      pos[n] = { x: Math.round(xs * 10) / 10, y: Math.round(ys * 10) / 10, depth: depth[n] };
    }
    return pos;
  }

  function tone(b) {
    if (!b.active) return COLORS.grey;
    if (b.open) return COLORS.amber;
    if (b.status === 'VALIDATED') return '#E9FFFB';
    if (b.status === 'TESTED') return COLORS.cyan;
    if (b.status === 'REFUTED') return COLORS.grey;
    return COLORS.pale;
  }

  function hash(text) { let h = 2166136261; for (let i = 0; i < text.length; i++) { h ^= text.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }

  // Deterministic decorative fractal twigs; seeded by the branch name so they never jump.
  function twigs(name, x, y, leaf, color, opacity) {
    const out = [];
    let seed = hash(name) || 1;
    const rnd = () => { seed = (seed * 1103515245 + 12345) >>> 0; return (seed % 10000) / 10000; };
    const grow = (x0, y0, ang, len, d, o) => {
      if (!d || len < 5) return;
      const x1 = x0 + Math.cos(ang) * len, y1 = y0 + Math.sin(ang) * len;
      out.push({ x1: x0, y1: y0, x2: x1, y2: y1, w: d * 0.45, o, color });
      const spread = 0.4 + rnd() * 0.25;
      grow(x1, y1, ang - spread, len * (0.64 + rnd() * 0.1), d - 1, o * 0.8);
      grow(x1, y1, ang + spread, len * (0.64 + rnd() * 0.1), d - 1, o * 0.8);
    };
    const base = -Math.PI / 2 + (x - VIEW.w / 2) / VIEW.w;
    const len = leaf ? 44 : 24, d = leaf ? 5 : 3;
    grow(x, y, base - 0.35, len, d, opacity);
    grow(x, y, base + 0.35, len, d, opacity);
    return out;
  }

  // Everything the SVG needs, as plain data (also what the tests check).
  function scene(state, t, opts) {
    const o = opts || {};
    const at = computeAt(state, t);
    const pos = layout(state);
    const matches = o.matches ? new Set(o.matches) : null;
    const edges = [], nodes = [], decor = [];
    for (const [name, p] of Object.entries(pos)) {
      const b = at[name];
      if (!b.visible) continue;
      const color = tone(b);
      const dim = matches && !matches.has(name) ? 0.22 : 1;
      const leaf = !Object.keys(pos).some(k => at[k].visible && state.branches[k].parents.includes(name));
      decor.push(...twigs(name, p.x, p.y, leaf, color, (b.active ? 0.55 : 0.22) * dim));
      state.branches[name].parents.forEach((parent, i) => {
        const a = pos[parent];
        if (!a) return;
        const mid = (a.y + p.y) / 2;
        const w = Math.max(2, 9 - p.depth * 2.2);
        edges.push({ from: parent, to: name, d: `M ${a.x} ${a.y} C ${a.x} ${mid}, ${p.x} ${mid + 20}, ${p.x} ${p.y}`, color, w, o: (b.active ? 0.95 : 0.45) * dim,
          dash: !b.active ? '6 8' : (i > 0 ? '2 7' : null), glow: b.active ? 0.28 * dim : 0 });
      });
      const r = p.depth === 0 ? 12 : 9;
      nodes.push({ name, x: p.x, y: p.y, r, color, dim, active: b.active, open: b.open, status: b.status,
        filled: b.active && (b.status === 'TESTED' || b.status === 'VALIDATED'), fresh: o.fresh ? o.fresh.has(name) : false,
        selected: o.selected === name, label: name, meta: !b.active ? 'pruned' : (b.open ? 'open challenge' : (b.reopened ? 'reopened · ' : '') + b.status.toLowerCase()) });
    }
    return { edges, nodes, decor, at, pos };
  }

  const NS = 'http://www.w3.org/2000/svg';
  function el(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) node.setAttribute(k, String(v));
    if (parent) parent.append(node);
    return node;
  }

  function render(svg, state, t, opts) {
    const o = opts || {};
    const s = scene(state, t, o);
    svg.replaceChildren();
    svg.setAttribute('viewBox', `0 0 ${VIEW.w} ${VIEW.h}`);
    const defs = el('defs', {}, svg);
    const f = el('filter', { id: 'garden-glow', x: '-50%', y: '-50%', width: '200%', height: '200%' }, defs);
    el('feGaussianBlur', { stdDeviation: 6 }, f);
    for (const r of [120, 240, 360, 480, 600, 720]) el('circle', { cx: VIEW.w / 2, cy: VIEW.bottom + 12, r, fill: 'none', stroke: '#111925' }, svg);
    for (const d of s.decor) el('line', { x1: d.x1.toFixed(1), y1: d.y1.toFixed(1), x2: d.x2.toFixed(1), y2: d.y2.toFixed(1), stroke: d.color, 'stroke-width': d.w.toFixed(2), opacity: d.o.toFixed(3), 'stroke-linecap': 'round', class: 'twig' }, svg);
    for (const e of s.edges) {
      if (e.glow) el('path', { d: e.d, fill: 'none', stroke: e.color, 'stroke-width': e.w + 6, opacity: e.glow, filter: 'url(#garden-glow)' }, svg);
      el('path', { d: e.d, fill: 'none', stroke: e.color, 'stroke-width': e.w, opacity: e.o, 'stroke-dasharray': e.dash, 'stroke-linecap': 'round', class: o.fresh && o.fresh.has(e.to) ? 'limb grow' : 'limb' }, svg);
    }
    for (const n of s.nodes) {
      const g = el('g', { class: 'node' + (n.fresh ? ' grow' : ''), opacity: n.dim, tabindex: 0, role: 'button', 'aria-label': `${n.name}: ${n.meta}`, 'data-branch': n.name }, svg);
      if (n.active) el('circle', { cx: n.x, cy: n.y, r: n.r + 12, fill: n.color, opacity: 0.35, filter: 'url(#garden-glow)' }, g);
      el('circle', { cx: n.x, cy: n.y, r: n.r + 9, fill: 'none', stroke: n.selected ? COLORS.text : 'transparent', 'stroke-width': 1.5 }, g);
      el('circle', { cx: n.x, cy: n.y, r: n.r, fill: n.filled ? n.color : COLORS.ink, stroke: n.color, 'stroke-width': 2.5, 'stroke-dasharray': n.active ? null : '3 3' }, g);
      const right = n.x < VIEW.w - 260;
      const lx = n.x + (right ? 22 : -22), anchor = right ? 'start' : 'end';
      const label = el('text', { x: lx, y: n.y - 4, fill: COLORS.text, 'font-size': 19, 'font-weight': 600, 'text-anchor': anchor }, g);
      label.textContent = n.label.length > 28 ? n.label.slice(0, 27) + '…' : n.label;
      const meta = el('text', { x: lx, y: n.y + 17, fill: COLORS.muted, 'font-size': 14, 'font-family': 'ui-monospace, monospace', 'text-anchor': anchor }, g);
      meta.textContent = n.meta;
      if (o.onSelect) {
        g.addEventListener('click', () => o.onSelect(n.name));
        g.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); o.onSelect(n.name); } });
      }
    }
    if (!s.nodes.length) {
      const empty = el('text', { x: VIEW.w / 2, y: VIEW.h / 2, fill: COLORS.muted, 'font-size': 16, 'text-anchor': 'middle' }, svg);
      empty.textContent = 'No branches yet at this point in history.';
    }
    svg.setAttribute('aria-label', `Research tree at event ${t}: ${s.nodes.length} branches, ${s.nodes.filter(n => n.open && n.active).length} with open challenges`);
    return s;
  }

  const api = { computeAt, layout, scene, tone, twigs, render, OP_COLOR, COLORS, VIEW };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.Garden = api;
})(typeof window !== 'undefined' ? window : globalThis);
