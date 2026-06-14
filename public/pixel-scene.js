/* pixel-scene.js — AsgardMade Pantheon 2D pixel building (pure canvas, no deps) */
const PixelBuilding = (() => {
  'use strict';

  let _canvas = null, _ctx = null, _animId = null, _ro = null;
  let _agents = [];
  let _t = 0;
  let _W = 800;

  const FLOOR_H = 82; // px per floor

  // Floor definitions — top to bottom
  const FLOOR_DEFS = [
    { name:'HEIMDALL', label:'RESEARCH',  bodyCol:'#3db8d8', accentCol:'#00d4ff', roomBg:'#010912', floorCol:'#071828', trim:'#00aacc' },
    { name:'VULCAN',   label:'FORGE',     bodyCol:'#ff6600', accentCol:'#ffaa00', roomBg:'#140400', floorCol:'#280900', trim:'#ff6600' },
    { name:'LOKI',     label:'MARKET',    bodyCol:'#22cc55', accentCol:'#2dff6f', roomBg:'#010a03', floorCol:'#051509', trim:'#00cc44' },
    { name:'VAULT',    label:'TREASURY',  bodyCol:'#d4a017', accentCol:'#ffd700', roomBg:'#090700', floorCol:'#181000', trim:'#ccaa00' },
    { name:'GUARDIAN', label:'SECURITY',  bodyCol:'#cc2222', accentCol:'#ff4444', roomBg:'#090101', floorCol:'#180303', trim:'#cc0000' },
  ];

  // ── helpers ─────────────────────────────────────────────────────────────────
  const $ = id => document.getElementById(id);

  function r(n) { return Math.round(n); }

  function rect(ctx, x, y, w, h, col) {
    ctx.fillStyle = col;
    ctx.fillRect(r(x), r(y), r(w), r(h));
  }

  function strokeRect(ctx, x, y, w, h, col, lw = 1) {
    ctx.strokeStyle = col;
    ctx.lineWidth = lw;
    ctx.strokeRect(r(x) + 0.5, r(y) + 0.5, r(w), r(h));
  }

  function circle(ctx, x, y, rad, col) {
    ctx.beginPath();
    ctx.arc(r(x), r(y), rad, 0, Math.PI * 2);
    ctx.fillStyle = col;
    ctx.fill();
  }

  function glowLine(ctx, x1, y1, x2, y2, col, blur = 4) {
    ctx.save();
    ctx.shadowColor = col; ctx.shadowBlur = blur;
    ctx.strokeStyle = col; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(r(x1), r(y1)); ctx.lineTo(r(x2), r(y2)); ctx.stroke();
    ctx.restore();
  }

  function txt(ctx, s, x, y, col, size = 8, align = 'left') {
    ctx.fillStyle = col;
    ctx.font = `bold ${size}px monospace`;
    ctx.textBaseline = 'top';
    ctx.textAlign = align;
    ctx.fillText(s, r(x), r(y));
    ctx.textAlign = 'left';
  }

  // ── per-agent state ──────────────────────────────────────────────────────────
  function makeAgent(def, idx) {
    return {
      ...def, idx,
      x: 80 + Math.random() * (_W - 160),
      dir: Math.random() < 0.5 ? 1 : -1,
      speed: 26 + Math.random() * 10,
      walkFrame: 0,
      walkTimer: 0,
      pauseTimer: Math.random() * 1.5,
      status: 'idle',
      activity: '',
    };
  }

  // ── character drawing ────────────────────────────────────────────────────────
  function drawChar(ctx, ag, floorBottom) {
    const { x, bodyCol, accentCol, name, dir, walkFrame, status, pauseTimer } = ag;
    const y = floorBottom - 9; // feet position
    const walking = pauseTimer <= 0;
    const S = 2; // pixel scale

    // Shadow
    ctx.save(); ctx.globalAlpha = 0.28;
    ctx.beginPath(); ctx.ellipse(r(x), y + 2, 8, 3, 0, 0, Math.PI * 2);
    ctx.fillStyle = '#000'; ctx.fill();
    ctx.restore();

    // Legs
    const legOff = walking ? (walkFrame % 2 === 0 ? 3 : -3) : 0;
    rect(ctx, x - 4, y - S * 3 + legOff, S, S * 3, '#1a1a2e');
    rect(ctx, x + 1, y - S * 3 - legOff, S, S * 3, '#1a1a2e');
    // Feet
    rect(ctx, x - 5 + (dir > 0 ? 0 : -1) + Math.round(legOff * 0.3), y - S + 1, S * 2, S, '#111');
    rect(ctx, x + 0 + (dir > 0 ? 1 : 0) - Math.round(legOff * 0.3), y - S + 1, S * 2, S, '#111');

    // Body
    rect(ctx, x - 5, y - S * 8, S * 5, S * 4, bodyCol);
    // Body highlight (top edge)
    rect(ctx, x - 5, y - S * 8, S * 5, 1, lighten(bodyCol, 50));

    // Arms (swing opposite legs)
    const armSwing = walking ? (walkFrame % 2 === 0 ? 3 : -3) : 0;
    rect(ctx, x - 7, y - S * 7 + armSwing, S, S * 3, bodyCol);
    rect(ctx, x + 4, y - S * 7 - armSwing, S, S * 3, bodyCol);
    // Hands
    rect(ctx, x - 7, y - S * 5 + armSwing, S, S, '#f5c8a0');
    rect(ctx, x + 4, y - S * 5 - armSwing, S, S, '#f5c8a0');

    // Head
    rect(ctx, x - 4, y - S * 12, S * 4, S * 4, '#f5c8a0');
    // Eyes
    ctx.fillStyle = accentCol;
    const eyeX = dir > 0 ? x + 1 : x - 3;
    ctx.fillRect(r(eyeX), r(y - S * 11), S, S);
    // Eye glow
    ctx.save(); ctx.shadowColor = accentCol; ctx.shadowBlur = 4;
    ctx.fillStyle = accentCol; ctx.fillRect(r(eyeX), r(y - S * 11), S, S);
    ctx.restore();

    // Accessory per agent
    drawAccessory(ctx, ag, x, y, S);

    // Working glow aura
    if (status === 'working' || status === 'active') {
      ctx.save();
      ctx.globalAlpha = 0.12 + 0.06 * Math.sin(_t * 5);
      ctx.fillStyle = accentCol;
      ctx.beginPath(); ctx.arc(r(x), r(y - S * 6), 18, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    }

    // Name tag
    const tagPad = 4, tagH = 12;
    const metrics = ctx.measureText(name);
    ctx.font = 'bold 7px monospace';
    const tagW = r(name.length * 5.5 + tagPad * 2);
    const tagX = r(x - tagW / 2);
    const tagY = r(y - S * 14 - 2);
    ctx.fillStyle = 'rgba(0,0,0,0.82)';
    ctx.fillRect(tagX, tagY, tagW, tagH);
    ctx.strokeStyle = accentCol + 'aa'; ctx.lineWidth = 0.7;
    ctx.strokeRect(tagX + 0.5, tagY + 0.5, tagW, tagH);
    ctx.fillStyle = accentCol;
    ctx.font = 'bold 7px monospace'; ctx.textBaseline = 'top'; ctx.textAlign = 'center';
    ctx.fillText(name, r(x), tagY + 2);
    ctx.textAlign = 'left';

    // Status dot on tag
    const dotCol = { idle: '#334466', active: '#00ff88', working: '#ffcc00', error: '#ff3355', alert: '#ff8800' }[status] || '#334466';
    ctx.save(); ctx.shadowColor = dotCol; ctx.shadowBlur = dotCol !== '#334466' ? 5 : 0;
    circle(ctx, tagX + tagW - 5, tagY + 6, 2.5, dotCol);
    ctx.restore();
  }

  function drawAccessory(ctx, ag, x, y, S) {
    const { name, accentCol } = ag;
    if (name === 'HEIMDALL') {
      // Glowing halo ring
      ctx.save(); ctx.strokeStyle = accentCol; ctx.lineWidth = 1.2;
      ctx.shadowColor = accentCol; ctx.shadowBlur = 6;
      ctx.beginPath(); ctx.arc(r(x), r(y - S * 13), 7, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();
    } else if (name === 'VULCAN') {
      // Hard hat
      rect(ctx, x - 6, y - S * 12, S * 5 + 2, 2, '#ffcc00');
      rect(ctx, x - 3, y - S * 13, S * 3, S, '#ffcc00');
    } else if (name === 'LOKI') {
      // Two horns
      rect(ctx, x - 5, y - S * 13, 2, S * 2, '#1a1a1a');
      rect(ctx, x - 6, y - S * 14, 2, S, '#1a1a1a');
      rect(ctx, x + 2, y - S * 13, 2, S * 2, '#1a1a1a');
      rect(ctx, x + 3, y - S * 14, 2, S, '#1a1a1a');
    } else if (name === 'VAULT') {
      // Top hat
      rect(ctx, x - 6, y - S * 12, S * 5 + 2, 2, '#111');
      rect(ctx, x - 4, y - S * 14, S * 4, S * 2, '#111');
      rect(ctx, x - 4, y - S * 12 + 1, S * 4, 1, accentCol); // gold band
    } else if (name === 'GUARDIAN') {
      // Tactical helmet
      rect(ctx, x - 4, y - S * 13, S * 4, S, '#333');
      rect(ctx, x - 3, y - S * 12, S * 3, S, accentCol + 'cc'); // visor glow
      ctx.save(); ctx.shadowColor = accentCol; ctx.shadowBlur = 5;
      rect(ctx, x - 3, y - S * 12, S * 3, S, accentCol + 'cc');
      ctx.restore();
    }
  }

  function lighten(hex, amt) {
    const n = parseInt(hex.replace('#', ''), 16);
    const r = Math.min(255, (n >> 16) + amt);
    const g = Math.min(255, ((n >> 8) & 0xff) + amt);
    const b = Math.min(255, (n & 0xff) + amt);
    return `rgb(${r},${g},${b})`;
  }

  // ── room drawing ─────────────────────────────────────────────────────────────
  function drawFloor(ctx, ag, W, t) {
    const fy = ag.idx * FLOOR_H;
    const H = FLOOR_H;

    ctx.save();
    ctx.beginPath(); ctx.rect(0, fy, W, H); ctx.clip();

    // BG
    rect(ctx, 0, fy, W, H, ag.roomBg);

    // Subtle scanline
    for (let sy = fy; sy < fy + H; sy += 4) {
      rect(ctx, 0, sy, W, 1, 'rgba(0,0,0,0.12)');
    }

    // Ceiling strip
    rect(ctx, 0, fy, W, 5, ag.floorCol);
    glowLine(ctx, 0, fy + 5, W, fy + 5, ag.trim + '55', 2);

    // Floor strip
    rect(ctx, 0, fy + H - 9, W, 9, ag.floorCol);
    glowLine(ctx, 0, fy + H - 9, W, fy + H - 9, ag.trim + '88', 3);

    // Left pillar
    rect(ctx, 0, fy, 5, H, '#0a0c18');
    rect(ctx, 5, fy, 1, H, ag.trim + '44');

    // Right pillar
    rect(ctx, W - 5, fy, 5, H, '#0a0c18');
    rect(ctx, W - 6, fy, 1, H, ag.trim + '44');

    // Floor label (top-left)
    rect(ctx, 10, fy + 7, 78, 15, 'rgba(0,0,0,0.72)');
    strokeRect(ctx, 10, fy + 7, 78, 15, ag.trim + '66');
    txt(ctx, ag.label, 14, fy + 9, ag.trim, 8);

    // Agent-specific room decorations
    if (ag.name === 'HEIMDALL') drawHeimdallRoom(ctx, ag, W, fy, H, t);
    else if (ag.name === 'VULCAN') drawVulcanRoom(ctx, ag, W, fy, H, t);
    else if (ag.name === 'LOKI') drawLokiRoom(ctx, ag, W, fy, H, t);
    else if (ag.name === 'VAULT') drawVaultRoom(ctx, ag, W, fy, H, t);
    else if (ag.name === 'GUARDIAN') drawGuardianRoom(ctx, ag, W, fy, H, t);

    // Activity text (top-right)
    if (ag.activity) {
      const maxLen = Math.floor((W * 0.45) / 5.5);
      const actTxt = ag.activity.length > maxLen ? ag.activity.slice(0, maxLen) + '…' : ag.activity;
      const aw = actTxt.length * 5.5 + 8;
      rect(ctx, W - aw - 12, fy + 7, aw, 14, 'rgba(0,0,0,0.72)');
      txt(ctx, actTxt, W - 14, fy + 9, ag.accentCol + 'cc', 7, 'right');
    }

    // Draw character
    drawChar(ctx, ag, fy + H - 9);

    ctx.restore();

    // Bottom separator
    glowLine(ctx, 0, fy + H, W, fy + H, ag.trim + '44', 1);
  }

  // HEIMDALL — observatory/research: star map bg, telescope, data panels, bifrost ring
  function drawHeimdallRoom(ctx, ag, W, fy, H, t) {
    const { accentCol } = ag;
    // Stars
    for (let i = 0; i < 25; i++) {
      const sx = 100 + ((i * 139 + 30) % (W - 180));
      const sy = fy + 10 + ((i * 97 + 5) % (H - 24));
      const sa = 0.3 + (i % 3) * 0.2 + 0.15 * Math.sin(t * 0.8 + i);
      ctx.globalAlpha = sa;
      circle(ctx, sx, sy, 0.7 + (i % 2) * 0.5, '#aaddff');
      ctx.globalAlpha = 1;
    }
    // Data panel (left-center)
    rect(ctx, 90, fy + 12, 68, 44, '#020c18');
    strokeRect(ctx, 90, fy + 12, 68, 44, accentCol + '44');
    // Animated data lines
    for (let r2 = 0; r2 < 4; r2++) {
      const lw = 12 + ((Math.floor(t * 6) + r2 * 13) % 48);
      rect(ctx, 93, fy + 17 + r2 * 9, lw, 3, r2 === 0 ? accentCol : accentCol + '55');
      rect(ctx, 93 + lw, fy + 17 + r2 * 9, 4, 3, accentCol + '22');
    }
    txt(ctx, 'DATA', 94, fy + 13, accentCol + '88', 6);
    // Telescope (right area)
    rect(ctx, W - 65, fy + H - 28, 7, 20, '#1a2a44');
    rect(ctx, W - 72, fy + H - 18, 22, 4, '#1a2a44');
    rect(ctx, W - 74, fy + H - 22, 5, 10, accentCol + 'bb');
    // Bifrost ring
    ctx.save();
    ctx.strokeStyle = accentCol + 'aa'; ctx.lineWidth = 2;
    ctx.shadowColor = accentCol; ctx.shadowBlur = 8;
    ctx.beginPath(); ctx.arc(W - 42, fy + H - 36, 12, 0, Math.PI * 2); ctx.stroke();
    ctx.restore();
    // Orbiting dot on bifrost ring
    const ang = t * 1.8;
    ctx.save(); ctx.shadowColor = accentCol; ctx.shadowBlur = 6;
    circle(ctx, W - 42 + Math.cos(ang) * 12, fy + H - 36 + Math.sin(ang) * 12, 2.5, accentCol);
    ctx.restore();
  }

  // VULCAN — forge: easel, floating sparks, palette, design tablet
  function drawVulcanRoom(ctx, ag, W, fy, H, t) {
    const { accentCol } = ag;
    const ex = W * 0.62;
    // Easel legs
    rect(ctx, ex - 14, fy + 14, 2, H - 26, '#442200');
    rect(ctx, ex + 11, fy + 14, 2, H - 26, '#442200');
    // Canvas frame
    rect(ctx, ex - 13, fy + 13, 26, 32, '#1a0900');
    strokeRect(ctx, ex - 13, fy + 13, 26, 32, accentCol + '88');
    // Color blocks (tiny painting)
    const pColors = ['#ff4400', '#ffcc00', '#00aaff', '#ff00aa', '#00ff88', '#ff6600'];
    pColors.forEach((c, i) => rect(ctx, ex - 11 + (i % 3) * 8, fy + 16 + Math.floor(i / 3) * 12, 7, 10, c));
    // Paint palette
    ctx.beginPath(); ctx.ellipse(r(ex - 36), r(fy + H - 20), 16, 8, 0.2, 0, Math.PI * 2);
    ctx.fillStyle = '#221100'; ctx.fill();
    ['#ff4400', '#ffcc00', '#44ff88', '#0088ff', '#ff00aa'].forEach((c, i) => {
      circle(ctx, ex - 44 + i * 8, fy + H - 20, 3, c);
    });
    // Sparks (floating)
    for (let i = 0; i < 6; i++) {
      const sx = ex + Math.sin(t * 2.5 + i * 1.3) * 22;
      const sy = fy + H - 28 - Math.abs(Math.sin(t * 3.2 + i)) * 26;
      const sr = 1.5 + (i % 3) * 0.6;
      ctx.save(); ctx.shadowColor = i % 2 ? '#ffaa00' : '#ff6600'; ctx.shadowBlur = 7;
      circle(ctx, sx, sy, sr, i % 2 ? '#ffcc00' : '#ff6600');
      ctx.restore();
    }
    // Design tablet (left wall)
    rect(ctx, 22, fy + 12, 44, 36, '#0d0600');
    strokeRect(ctx, 22, fy + 12, 44, 36, accentCol + '66');
    txt(ctx, 'DESIGNS', 25, fy + 14, accentCol + '88', 6);
    rect(ctx, 24, fy + 22, 40, 3, accentCol + '55');
    rect(ctx, 24, fy + 28, 28, 3, accentCol + '33');
    rect(ctx, 24, fy + 34, 36, 3, accentCol + '44');
  }

  // LOKI — market: floating price tags, product shelves, SEO bar, store sign
  function drawLokiRoom(ctx, ag, W, fy, H, t) {
    const { accentCol } = ag;
    // Store sign top-center
    rect(ctx, W / 2 - 48, fy + 5, 96, 16, '#0a1a08');
    strokeRect(ctx, W / 2 - 48, fy + 5, 96, 16, accentCol + '66');
    txt(ctx, '◈ ETSY LISTINGS', W / 2, fy + 8, accentCol, 7, 'center');
    // Product shelf
    rect(ctx, W - 90, fy + H - 32, 80, 4, '#221100');
    // Products
    [['#ff4466', 10], [accentCol, 7], ['#44aaff', 9]].forEach(([c, h], i) => {
      rect(ctx, W - 86 + i * 22, fy + H - 32 - h, 14, h, c);
      strokeRect(ctx, W - 86 + i * 22, fy + H - 32 - h, 14, h, c + 'aa', 0.5);
    });
    // Floating price tags
    for (let i = 0; i < 3; i++) {
      const px2 = 100 + i * 95;
      const py = fy + 26 + Math.sin(t * 1.1 + i * 2.1) * 4;
      rect(ctx, px2, py, 52, 16, 'rgba(0,0,0,0.75)');
      strokeRect(ctx, px2, py, 52, 16, accentCol + '99');
      txt(ctx, `$${(24.99 + i * 5).toFixed(2)}`, px2 + 4, py + 4, accentCol, 8);
    }
    // SEO meter (bottom-left)
    rect(ctx, 20, fy + H - 26, 70, 14, '#0a1a08');
    strokeRect(ctx, 20, fy + H - 26, 70, 14, accentCol + '55');
    txt(ctx, 'SEO', 23, fy + H - 24, accentCol + '88', 6);
    const seoW = 28 + Math.floor(Math.sin(t * 0.4) * 12 + 12);
    rect(ctx, 36, fy + H - 22, seoW, 6, accentCol + 'aa');
  }

  // VAULT — treasury: vault door, coin stacks, animated ledger, chandelier
  function drawVaultRoom(ctx, ag, W, fy, H, t) {
    const { accentCol } = ag;
    // Vault door (right)
    const vx = W - 62, vy = fy + 10;
    rect(ctx, vx, vy, 44, 56, '#111008');
    strokeRect(ctx, vx, vy, 44, 56, accentCol + '66');
    // Spinning dial
    ctx.save(); ctx.translate(r(vx + 22), r(vy + 28)); ctx.rotate(t * 0.4);
    ctx.strokeStyle = accentCol; ctx.lineWidth = 1.5;
    ctx.shadowColor = accentCol; ctx.shadowBlur = 6;
    ctx.beginPath(); ctx.arc(0, 0, 14, 0, Math.PI * 2); ctx.stroke();
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(Math.cos(a) * 14, Math.sin(a) * 14); ctx.stroke();
    }
    circle(ctx, 0, 0, 3, accentCol);
    ctx.restore();
    // Coin stacks (center)
    for (let stack = 0; stack < 4; stack++) {
      const sx = W * 0.38 + stack * 26;
      const coinH = 2 + stack;
      for (let c = 0; c < coinH; c++) {
        ctx.save(); ctx.shadowColor = accentCol; ctx.shadowBlur = c === coinH - 1 ? 6 : 0;
        ctx.beginPath(); ctx.ellipse(r(sx), r(fy + H - 15 - c * 5), 10, 4, 0, 0, Math.PI * 2);
        ctx.fillStyle = c === coinH - 1 ? accentCol : '#886600'; ctx.fill();
        ctx.restore();
      }
    }
    // Ledger (left wall)
    rect(ctx, 18, fy + 10, 58, 52, '#100d00');
    strokeRect(ctx, 18, fy + 10, 58, 52, accentCol + '55');
    txt(ctx, 'VAULT P&L', 22, fy + 12, accentCol, 7);
    for (let row = 0; row < 4; row++) {
      rect(ctx, 20, fy + 22 + row * 9, 52, 1, accentCol + '22');
    }
    // Revenue value (animated)
    const dispVal = `$${(Math.abs(Math.sin(t * 0.08)) * 200).toFixed(2)}`;
    txt(ctx, dispVal, 22, fy + 50, '#00ff88', 8);
  }

  // GUARDIAN — security: hex tiles, server racks, shields, red warning strips
  function drawGuardianRoom(ctx, ag, W, fy, H, t) {
    const { accentCol } = ag;
    // Warning strips (ceiling)
    const stripeW = 20;
    for (let sx = 0; sx < W; sx += stripeW * 2) {
      rect(ctx, sx, fy, stripeW, 5, accentCol + '44');
    }
    // Server rack (right)
    rect(ctx, W - 58, fy + 8, 42, 58, '#0d0808');
    strokeRect(ctx, W - 58, fy + 8, 42, 58, accentCol + '55');
    for (let u = 0; u < 5; u++) {
      rect(ctx, W - 56, fy + 11 + u * 11, 38, 9, '#0a0505');
      // LED blink
      const lit = Math.floor(t * 2.5 + u * 0.7) % 3 !== 0;
      ctx.save(); if (lit) { ctx.shadowColor = accentCol; ctx.shadowBlur = 5; }
      circle(ctx, W - 18, fy + 15 + u * 11, 2.5, lit ? accentCol : '#330000');
      ctx.restore();
    }
    // Hex tiles on floor (left-center)
    for (let hi = 0; hi < 7; hi++) {
      const hx = 30 + hi * 18;
      const hrad = 7;
      ctx.beginPath();
      for (let v = 0; v < 6; v++) {
        const a = (v / 6) * Math.PI * 2 - Math.PI / 6;
        const px = hx + Math.cos(a) * hrad;
        const py = fy + H - 14 + Math.sin(a) * 4;
        v === 0 ? ctx.moveTo(r(px), r(py)) : ctx.lineTo(r(px), r(py));
      }
      ctx.closePath();
      ctx.strokeStyle = hi === 3 ? accentCol + 'cc' : accentCol + '33'; ctx.lineWidth = 0.8; ctx.stroke();
    }
    // Shield status panel (left wall)
    rect(ctx, 18, fy + 10, 80, 40, '#0a0505');
    strokeRect(ctx, 18, fy + 10, 80, 40, accentCol + '66');
    txt(ctx, 'SECURITY', 22, fy + 12, accentCol, 7);
    txt(ctx, '● SHIELD: ACTIVE', 22, fy + 22, '#00ff88', 7);
    txt(ctx, '● THREATS: 0', 22, fy + 32, accentCol + 'aa', 7);
    // Rotating radar sweep (bottom-center)
    ctx.save();
    ctx.translate(r(W * 0.5), r(fy + H - 16));
    const sweep = (t * 0.9) % (Math.PI * 2);
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.arc(0, 0, 14, sweep - 0.9, sweep);
    ctx.fillStyle = accentCol + '22'; ctx.fill();
    ctx.beginPath(); ctx.moveTo(0, 0); ctx.lineTo(Math.cos(sweep) * 14, Math.sin(sweep) * 14);
    ctx.strokeStyle = accentCol + 'cc'; ctx.lineWidth = 1.2;
    ctx.shadowColor = accentCol; ctx.shadowBlur = 6; ctx.stroke();
    ctx.strokeStyle = accentCol + '33'; ctx.lineWidth = 0.5;
    [10, 14].forEach(r2 => { ctx.beginPath(); ctx.arc(0, 0, r2, 0, Math.PI * 2); ctx.stroke(); });
    ctx.restore();
  }

  // ── building chrome ──────────────────────────────────────────────────────────
  function drawBuildingChrome(ctx, W, H, t) {
    // Left/right edge columns
    const edgeW = 8;
    rect(ctx, 0, 0, edgeW, H, '#06080f');
    rect(ctx, W - edgeW, 0, edgeW, H, '#06080f');
    // Edge glow
    const el = ctx.createLinearGradient(0, 0, 18, 0);
    el.addColorStop(0, 'rgba(0,180,255,0.18)'); el.addColorStop(1, 'transparent');
    ctx.fillStyle = el; ctx.fillRect(edgeW, 0, 14, H);
    const er = ctx.createLinearGradient(W - 18, 0, W - edgeW, 0);
    er.addColorStop(0, 'transparent'); er.addColorStop(1, 'rgba(0,180,255,0.18)');
    ctx.fillStyle = er; ctx.fillRect(W - 22, 0, 14, H);

    // Top building header
    rect(ctx, 0, 0, W, 5, '#060a14');
    const pulseBright = 0.2 + 0.08 * Math.sin(t * 0.6);
    glowLine(ctx, 8, 5, W - 8, 5, `rgba(0,212,255,${pulseBright})`, 4);
  }

  // ── update ───────────────────────────────────────────────────────────────────
  function update(dt) {
    const MARGIN = 70;
    _agents.forEach(ag => {
      if (ag.pauseTimer > 0) { ag.pauseTimer -= dt; return; }
      ag.walkTimer += dt;
      if (ag.walkTimer > 0.2) { ag.walkTimer = 0; ag.walkFrame++; }
      ag.x += ag.dir * ag.speed * dt;
      if (ag.x > _W - MARGIN) { ag.x = _W - MARGIN; ag.dir = -1; ag.pauseTimer = 0.5 + Math.random(); }
      if (ag.x < MARGIN) { ag.x = MARGIN; ag.dir = 1; ag.pauseTimer = 0.5 + Math.random(); }
    });
  }

  // ── main render ──────────────────────────────────────────────────────────────
  function render() {
    if (!_ctx || !_canvas) return;
    const ctx = _ctx;
    const W = _canvas.width;
    const H = _canvas.height;
    ctx.clearRect(0, 0, W, H);
    rect(ctx, 0, 0, W, H, '#000408');
    _agents.forEach(ag => drawFloor(ctx, ag, W, _t));
    drawBuildingChrome(ctx, W, H, _t);
  }

  // ── click / hover ────────────────────────────────────────────────────────────
  function floorAtY(cy) {
    const idx = Math.floor(cy / FLOOR_H);
    if (idx >= 0 && idx < FLOOR_DEFS.length) return FLOOR_DEFS[idx].name;
    return null;
  }

  function onCanvasClick(e) {
    const rect2 = _canvas.getBoundingClientRect();
    const cy = e.clientY - rect2.top;
    const name = floorAtY(cy);
    if (name && typeof openChat === 'function') openChat(name);
  }

  function onCanvasHover(e) {
    const rect2 = _canvas.getBoundingClientRect();
    const cy = e.clientY - rect2.top;
    _canvas.style.cursor = floorAtY(cy) ? 'pointer' : 'default';
  }

  // ── init / dispose ────────────────────────────────────────────────────────────
  function init(container) {
    dispose();
    _W = container.clientWidth || 800;
    const totalH = FLOOR_DEFS.length * FLOOR_H;
    _canvas = document.createElement('canvas');
    _canvas.width = _W;
    _canvas.height = totalH;
    _canvas.style.cssText = 'display:block;width:100%;image-rendering:pixelated;';
    container.innerHTML = '';
    container.appendChild(_canvas);
    container.style.minHeight = totalH + 'px';
    _ctx = _canvas.getContext('2d');
    _agents = FLOOR_DEFS.map((def, i) => makeAgent(def, i));

    _canvas.addEventListener('click', onCanvasClick);
    _canvas.addEventListener('mousemove', onCanvasHover);

    _ro = new ResizeObserver(() => {
      const nw = container.clientWidth;
      if (nw > 20 && _canvas) {
        _W = nw;
        _canvas.width = nw;
        _agents.forEach(ag => { if (ag.x > nw - 70) ag.x = nw - 70; });
      }
    });
    _ro.observe(container);

    let last = performance.now();
    function loop(now) {
      _animId = requestAnimationFrame(loop);
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now; _t += dt;
      update(dt);
      render();
    }
    _animId = requestAnimationFrame(loop);
  }

  function dispose() {
    cancelAnimationFrame(_animId); _animId = null;
    if (_ro) { _ro.disconnect(); _ro = null; }
    if (_canvas) {
      _canvas.removeEventListener('click', onCanvasClick);
      _canvas.removeEventListener('mousemove', onCanvasHover);
      _canvas.remove(); _canvas = null; _ctx = null;
    }
    _agents = [];
  }

  // ── public API ────────────────────────────────────────────────────────────────
  function setAgentStatus(name, status, activity) {
    const ag = _agents.find(a => a.name === name);
    if (ag) { ag.status = status || 'idle'; ag.activity = activity || ''; }
  }

  return { init, dispose, setAgentStatus };
})();
