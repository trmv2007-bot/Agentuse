/* AGENTUSE — SpaceGrid background: perspective grid floor, starfield,
   scan sweep, and action pulses emitted live as the agent works. */
(() => {
  const cv = document.getElementById('bg');
  const ctx = cv.getContext('2d');
  let W = 0, H = 0, DPR = 1;

  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = W * DPR; cv.height = H * DPR;
    cv.style.width = W + 'px'; cv.style.height = H + 'px';
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  window.addEventListener('resize', resize);
  resize();

  // ---- palette (updates with mode) ----
  let accent = { r: 34, g: 211, b: 238 };
  function readAccent() {
    const cs = getComputedStyle(document.body).getPropertyValue('--accent').trim();
    const m = cs.match(/#([0-9a-f]{6})/i);
    if (m) {
      accent = {
        r: parseInt(m[1].slice(0, 2), 16),
        g: parseInt(m[1].slice(2, 4), 16),
        b: parseInt(m[1].slice(4, 6), 16),
      };
    }
  }
  setInterval(readAccent, 800);

  const rgba = (a) => `rgba(${accent.r},${accent.g},${accent.b},${a})`;

  // ---- stars ----
  const stars = Array.from({ length: 170 }, () => ({
    x: Math.random(), y: Math.random() * 0.62,
    z: Math.random() * 0.9 + 0.1,
    tw: Math.random() * Math.PI * 2,
  }));

  // ---- action pulses ----
  const pulses = [];
  window.gridPulse = function gridPulse(label) {
    const targetX = 0.15 + Math.random() * 0.7;
    const targetY = 0.2 + Math.random() * 0.5;
    pulses.push({
      x: W / 2, y: H * 0.34,
      tx: targetX * W, ty: targetY * H,
      t: 0, life: 1, label: label || '',
    });
    if (pulses.length > 26) pulses.shift();
  };

  // ---- horizon grid ----
  const HORIZON = () => H * 0.62;
  let offset = 0;

  function drawGrid(t) {
    const hy = HORIZON();
    const depth = H - hy;
    // horizontal lines scrolling toward viewer
    const rows = 22;
    for (let i = 0; i < rows; i++) {
      const p = ((i + (offset % 1)) / rows);
      const y = hy + Math.pow(p, 2.6) * depth;
      const a = 0.028 + p * 0.16;
      ctx.strokeStyle = rgba(a);
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }
    // vertical converging lines
    const cols = 26;
    for (let i = -cols; i <= cols; i++) {
      const xBottom = W / 2 + i * (W / 10);
      ctx.strokeStyle = rgba(0.05 + Math.abs(i) / cols * 0.05);
      ctx.beginPath(); ctx.moveTo(W / 2 + i * 14, hy); ctx.lineTo(xBottom, H); ctx.stroke();
    }
    // horizon glow line
    const grad = ctx.createLinearGradient(0, hy - 40, 0, hy + 3);
    grad.addColorStop(0, 'rgba(0,0,0,0)');
    grad.addColorStop(1, rgba(0.20));
    ctx.fillStyle = grad;
    ctx.fillRect(0, hy - 40, W, 43);
    ctx.strokeStyle = rgba(0.35);
    ctx.beginPath(); ctx.moveTo(0, hy); ctx.lineTo(W, hy); ctx.stroke();
  }

  function drawStars(t) {
    for (const s of stars) {
      const tw = 0.35 + 0.3 * Math.sin(t * 0.001 * s.z + s.tw);
      ctx.fillStyle = `rgba(200,235,255,${tw * s.z * 0.55})`;
      ctx.fillRect(s.x * W, s.y * H, s.z > 0.75 ? 1.6 : 1, s.z > 0.75 ? 1.6 : 1);
    }
  }

  function drawPulses(dt) {
    for (let i = pulses.length - 1; i >= 0; i--) {
      const p = pulses[i];
      p.t += dt * 1.4;
      if (p.t >= 1) { pulses.splice(i, 1); continue; }
      const ease = 1 - Math.pow(1 - p.t, 3);
      const x = p.x + (p.tx - p.x) * ease;
      const y = p.y + (p.ty - p.y) * ease;
      const a = Math.sin(p.t * Math.PI);
      // trail
      ctx.strokeStyle = rgba(a * 0.5);
      ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(x, y); ctx.stroke();
      // head
      ctx.fillStyle = rgba(a);
      ctx.beginPath(); ctx.arc(x, y, 2.6, 0, Math.PI * 2); ctx.fill();
      // landing ring
      if (p.t > 0.72) {
        const ringA = (p.t - 0.72) / 0.28;
        ctx.strokeStyle = rgba(ringA * 0.7);
        ctx.beginPath(); ctx.arc(p.tx, p.ty, ringA * 26, 0, Math.PI * 2); ctx.stroke();
      }
    }
  }

  // scan sweep band
  let scanY = -0.2;
  function drawScan(dt) {
    scanY += dt * 0.045;
    if (scanY > 1.2) scanY = -0.2;
    const y = scanY * H;
    const g = ctx.createLinearGradient(0, y - 60, 0, y + 60);
    g.addColorStop(0, 'rgba(0,0,0,0)');
    g.addColorStop(0.5, rgba(0.05));
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, y - 60, W, 120);
  }

  let last = performance.now();
  function frame(now) {
    const dt = Math.min((now - last) / 1000, 0.08);
    last = now;
    offset += dt * 0.35;
    ctx.clearRect(0, 0, W, H);
    // base vertical gradient
    const bg = ctx.createLinearGradient(0, 0, 0, H);
    bg.addColorStop(0, '#02040a');
    bg.addColorStop(0.6, '#040a16');
    bg.addColorStop(1, '#02060e');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);

    drawStars(now);
    drawGrid(now);
    drawScan(dt);
    drawPulses(dt);
    if (!document.hidden) requestAnimationFrame(frame);
  }
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) { last = performance.now(); requestAnimationFrame(frame); }
  });
  requestAnimationFrame(frame);
})();
