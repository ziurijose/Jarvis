/* The orb: a particle sphere that stands in for the assistant (the same one as in setup).
   Orb.mood(name) glides it into a mood; everything is time-based, so motion stays smooth at
   any frame rate. */
const Orb = (() => {
  const canvas = document.getElementById('orb');
  const ctx = canvas.getContext('2d');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const N = 1400;
  const pts = [];
  for (let i = 0; i < N; i++) {                       // Fibonacci sphere: even coverage, no clumps
    const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), t = i * 2.399963;
    pts.push({ x: Math.cos(t) * r, y, z: Math.sin(t) * r, seed: Math.random() * 6.283 });
  }
  const MOODS = {
    off:       { energy: 0.03, spread: 0.0, ripple: 0, scale: 0.86, dim: 0.55, spin: 0.25 },
    idle:      { energy: 0.22, spread: 0.0, ripple: 0, scale: 1.00, dim: 1.00, spin: 1.0 },
    listening: { energy: 0.55, spread: 0.04, ripple: 0, scale: 1.06, dim: 1.00, spin: 1.2 },
    thinking:  { energy: 0.45, spread: 0.10, ripple: 0, scale: 0.94, dim: 1.00, spin: 3.2 },
    speaking:  { energy: 0.90, spread: 0.18, ripple: 0, scale: 1.12, dim: 1.00, spin: 1.6 },
  };
  const target = { ...MOODS.idle };
  const now = { ...target };
  let mood = 'idle', w = 0, h = 0, dpr = 1, last = performance.now(), rot = 0, nextPulse = 0;

  function resize() {
    dpr = Math.min(devicePixelRatio || 1, 2);
    w = canvas.clientWidth; h = canvas.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr;
  }
  addEventListener('resize', resize); resize();

  function frame(t) {
    const dt = Math.min((t - last) / 1000, 0.05); last = t;
    for (const k in target) now[k] += (target[k] - now[k]) * (1 - Math.exp(-dt * 3.5));  // critically damped glide
    if ((mood === 'speaking' || mood === 'listening') && t > nextPulse && !reduced) {   // a heartbeat while it talks or hears
      now.ripple = mood === 'speaking' ? 1 : 0.5;
      nextPulse = t + (mood === 'speaking' ? 650 : 1400);
    }
    rot += dt * (reduced ? 0.04 : (0.12 + now.energy * 0.6) * now.spin);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const cx = w * 0.62, cy = h * 0.46, R = Math.min(w, h) * 0.34 * now.scale;
    const cr = Math.cos(rot), sr = Math.sin(rot), tilt = 0.38, ct = Math.cos(tilt), st = Math.sin(tilt);
    const time = t / 1000;

    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 1.4);       // inner glow
    g.addColorStop(0, `rgba(209,254,23,${(0.08 + now.energy * 0.16) * now.dim})`);
    g.addColorStop(1, 'rgba(209,254,23,0)');
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, R * 1.45, 0, 6.283); ctx.fill();

    for (const p of pts) {
      const wave = Math.sin(time * (1.2 + now.energy * 3) + p.y * 5 + p.seed) * (0.012 + now.energy * 0.05)
                 + Math.sin(time * 7 - (p.y + 1) * 6) * now.ripple * 0.07;
      const k = 1 + wave + now.spread * (0.6 + Math.sin(p.seed * 3) * 0.4);
      let x = p.x * cr - p.z * sr, z = p.x * sr + p.z * cr, y = p.y;
      const y2 = y * ct - z * st; z = y * st + z * ct; y = y2;
      const depth = (z + 1) / 2;                          // 0 back .. 1 front
      const px = cx + x * R * k, py = cy + y * R * k;
      const size = 0.6 + depth * 1.7;
      const lime = depth > 0.66 && p.seed < 0.75 + now.energy * 0.6;
      ctx.fillStyle = lime ? `rgba(209,254,23,${(0.6 + depth * 0.4) * now.dim})`
                           : `rgba(247,247,248,${(0.05 + depth * 0.55 * (1 - now.spread * 0.6)) * now.dim})`;
      ctx.fillRect(px - size / 2, py - size / 2, size, size);
    }
    now.ripple *= Math.exp(-dt * 2.2);
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  return {
    mood(name) {
      if (!MOODS[name] || name === mood) return;
      mood = name;
      Object.assign(target, MOODS[name]);
      now.ripple = Math.max(now.ripple, 0.6);              // every change of mood lands with a ripple
    },
  };
})();
