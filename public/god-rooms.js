/* ═══════════════════════════════════════════════════════════════════
   GOD ROOMS — Three.js 3D interactive scenes for AsgardMade Pantheon
   6 gods, 6 themed rooms, fully animated. Mouse-drag to orbit.
═══════════════════════════════════════════════════════════════════ */

const GodRooms = (() => {
  'use strict';

  let _renderer = null, _animId = null, _dragYaw = 0;

  // ── Material & geometry helpers ─────────────────────────────────

  function mat(color, emissive = 0x000000, emissiveIntensity = 0, opts = {}) {
    return new THREE.MeshToonMaterial({ color, emissive, emissiveIntensity, ...opts });
  }
  function mmat(color, metalness = 0.6, roughness = 0.3) {
    return new THREE.MeshStandardMaterial({ color, metalness, roughness });
  }
  function mesh(geo, mtl) {
    const m = new THREE.Mesh(geo, mtl); m.castShadow = true; m.receiveShadow = true; return m;
  }
  function box(w, h, d, color, em, ei, opts) {
    return mesh(new THREE.BoxGeometry(w, h, d), mat(color, em, ei, opts));
  }
  function sph(r, color, em, ei, opts) {
    return mesh(new THREE.SphereGeometry(r, 20, 14), mat(color, em, ei, opts));
  }
  function cyl(rt, rb, h, color, segs = 12, em, ei) {
    return mesh(new THREE.CylinderGeometry(rt, rb, h, segs), mat(color, em, ei));
  }
  function cone(r, h, color, em, ei) {
    return mesh(new THREE.ConeGeometry(r, h, 12), mat(color, em, ei));
  }
  function tor(r, tube, color, em, ei, segs = 24) {
    return mesh(new THREE.TorusGeometry(r, tube, 10, segs), mat(color, em, ei));
  }
  function disk(r, color, em, ei) {
    return mesh(new THREE.CircleGeometry(r, 24), mat(color, em, ei));
  }
  function grp(...children) {
    const g = new THREE.Group(); children.forEach(c => g.add(c)); return g;
  }
  function ptLight(scene, color, intensity, x, y, z, dist = 7) {
    const l = new THREE.PointLight(color, intensity, dist); l.position.set(x, y, z); scene.add(l); return l;
  }

  // ── Base room (floor + back wall + left wall) ───────────────────

  function makeRoom(scene, { floor = 0x1c1c2e, wall = 0x111128, trim = null } = {}) {
    const f = box(8, 0.18, 7, floor); f.position.y = 0.09; f.receiveShadow = true; scene.add(f);
    const bw = box(8, 5.5, 0.14, wall); bw.position.set(0, 2.84, -3.5); scene.add(bw);
    const lw = box(0.14, 5.5, 7, wall); lw.position.set(-4, 2.84, 0); scene.add(lw);
    if (trim) {
      const t1 = box(8.1, 0.08, 0.1, trim, trim, 0.4); t1.position.set(0, 5.1, -3.44); scene.add(t1);
      const t2 = box(0.1, 0.08, 7.1, trim, trim, 0.4); t2.position.set(-3.94, 5.1, 0); scene.add(t2);
    }
  }

  // ── Base character (chunky cartoon proportions) ─────────────────

  function makeChar({ body = 0x336699, headCol = null, armCol = null, legCol = null, skinCol = 0xd4956a } = {}) {
    const hc = headCol ?? body, ac = armCol ?? body, lc = legCol ?? body;
    const g = new THREE.Group();

    // Torso — chunky cylinder
    const torso = cyl(0.35, 0.42, 0.72, body, 14); torso.position.y = 1.02; g.add(torso);

    // Head — large sphere
    const skull = sph(0.32, skinCol); skull.position.y = 1.66; g.add(skull);

    // Arms
    const lArm = cyl(0.1, 0.1, 0.56, ac, 10); lArm.position.set(-0.5, 1.04, 0); lArm.rotation.z = 0.25; g.add(lArm);
    const rArm = cyl(0.1, 0.1, 0.56, ac, 10); rArm.position.set(0.5, 1.04, 0); rArm.rotation.z = -0.25; g.add(rArm);

    // Hands
    const lHand = sph(0.115, ac); lHand.position.set(-0.64, 0.75, 0); g.add(lHand);
    const rHand = sph(0.115, ac); rHand.position.set(0.64, 0.75, 0); g.add(rHand);

    // Legs
    const lLeg = cyl(0.13, 0.11, 0.52, lc, 10); lLeg.position.set(-0.19, 0.56, 0); g.add(lLeg);
    const rLeg = cyl(0.13, 0.11, 0.52, lc, 10); rLeg.position.set(0.19, 0.56, 0); g.add(rLeg);

    // Feet
    const lFoot = box(0.22, 0.1, 0.3, lc); lFoot.position.set(-0.19, 0.25, 0.06); g.add(lFoot);
    const rFoot = box(0.22, 0.1, 0.3, lc); rFoot.position.set(0.19, 0.25, 0.06); g.add(rFoot);

    // Eyes (white sclera)
    const eyeL = sph(0.078, 0xffffff); eyeL.position.set(-0.11, 1.69, 0.28); g.add(eyeL);
    const eyeR = sph(0.078, 0xffffff); eyeR.position.set(0.11, 1.69, 0.28); g.add(eyeR);

    // Pupils
    const pupilL = sph(0.04, 0x111111); pupilL.position.set(-0.11, 1.69, 0.315); g.add(pupilL);
    const pupilR = sph(0.04, 0x111111); pupilR.position.set(0.11, 1.69, 0.315); g.add(pupilR);

    // Smile
    const smile = tor(0.09, 0.012, 0x3a2010); smile.position.set(0, 1.585, 0.3);
    smile.rotation.x = Math.PI / 2; smile.rotation.z = Math.PI; g.add(smile);

    g.refs = { torso, skull, lArm, rArm, lHand, rHand, lLeg, rLeg, eyeL, eyeR, pupilL, pupilR, smile };
    return g;
  }

  // ══════════════════════════════════════════════════════════════
  //  ODIN — The Throne Room
  // ══════════════════════════════════════════════════════════════

  function buildODIN(scene) {
    scene.background = new THREE.Color(0x000814);
    scene.fog = new THREE.FogExp2(0x000814, 0.055);

    const amb = new THREE.AmbientLight(0x112244, 0.6); scene.add(amb);
    const dir = new THREE.DirectionalLight(0x99bbff, 1.2); dir.position.set(-3, 7, 5); dir.castShadow = true; scene.add(dir);
    const orbLight1 = ptLight(scene, 0x0077ff, 2.8, -2.5, 2.8, -2.0);
    const orbLight2 = ptLight(scene, 0x0044cc, 2.2, 2.5, 2.8, -2.0);
    const runeGlow  = ptLight(scene, 0x00aaff, 1.5, 0, 1.5, 0.5, 5);

    makeRoom(scene, { floor: 0x12122a, wall: 0x0c0c22, trim: 0xffd700 });

    // Floor rune inlay lines
    for (let i = -3; i <= 3; i++) {
      const l = box(0.025, 0.015, 7, 0x001155, 0x0033aa, 0.8); l.position.set(i * 1.1, 0.195, 0); scene.add(l);
    }
    for (let i = -3; i <= 3; i++) {
      const l = box(8, 0.015, 0.025, 0x001155, 0x0033aa, 0.6); l.position.set(0, 0.195, i * 1.0); scene.add(l);
    }

    // Throne
    const throneSeat = box(1.3, 0.16, 1.1, 0x1a1a3e); throneSeat.position.y = 0.98;
    const throneBack = box(1.3, 2.8, 0.16, 0x1a1a3e); throneBack.position.set(0, 2.3, -0.52);
    const lArmRest   = box(0.16, 0.55, 1.1, 0x252545); lArmRest.position.set(-0.57, 1.24, 0);
    const rArmRest   = box(0.16, 0.55, 1.1, 0x252545); rArmRest.position.set(0.57, 1.24, 0);
    const throneTop  = box(1.34, 0.08, 0.08, 0xffd700, 0xffaa00, 0.5); throneTop.position.set(0, 3.68, -0.52);
    const throne = grp(throneSeat, throneBack, lArmRest, rArmRest, throneTop);
    throne.position.set(0, 0.18, -2.5); scene.add(throne);

    // Side pillars
    [-2.8, 2.8].forEach(x => {
      const base = box(0.28, 3.6, 0.28, 0x111133); base.position.set(x, 1.98, -3.0); scene.add(base);
      const cap  = box(0.38, 0.12, 0.38, 0xffd700, 0xffaa00, 0.3); cap.position.set(x, 3.84, -3.0); scene.add(cap);
    });

    // Floating orbs
    const orbL = sph(0.22, 0x0033aa, 0x0099ff, 3.0); orbL.position.set(-2.5, 2.5, -2.2); scene.add(orbL);
    const orbR = sph(0.22, 0x0022aa, 0x0066ff, 3.0); orbR.position.set(2.5, 2.5, -2.2); scene.add(orbR);

    // Rune map on left wall
    const mapBg = box(1.8, 1.2, 0.06, 0x080820); mapBg.position.set(-3.93, 2.8, 0); scene.add(mapBg);
    [[0,2.6,0.1],[0.3,3.0,0.1],[-0.2,3.3,0.1],[0.15,2.85,0.1],[-0.1,2.5,0.1]].forEach(([z, y, x]) => {
      const d = sph(0.06, 0x00ccff, 0x00ffff, 2.5); d.position.set(-3.88, y, z); scene.add(d);
    });

    // Character
    const char = makeChar({ body: 0x1a3a7e, armCol: 0x1a3a7e, legCol: 0x14305e, skinCol: 0xc8a882 });
    char.position.set(0, 0.18, 0.6);
    scene.add(char);

    // Navy tunic over torso
    const tunic = cyl(0.36, 0.43, 0.74, 0x162d5e, 14); tunic.position.y = 1.02; char.add(tunic);
    // Gold chest stripe
    const stripe = box(0.06, 0.7, 0.44, 0xffd700, 0xffaa00, 0.3); stripe.position.set(0, 1.02, 0.36); char.add(stripe);

    // Cape (dark purple plane)
    const capeMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.95, 1.25), mat(0x3d0f6b, 0x0, 0, { side: THREE.DoubleSide }));
    capeMesh.position.set(0, 1.08, -0.28); char.add(capeMesh);

    // Gold crown
    const crown = tor(0.24, 0.048, 0xffd700, 0xffaa00, 0.4); crown.rotation.x = Math.PI / 2; crown.position.set(0, 1.97, 0); char.add(crown);
    const crownPoint = cone(0.04, 0.14, 0xffd700, 0xffaa00, 0.5); crownPoint.position.set(0, 2.07, 0); char.add(crownPoint);

    // Eye patch over left eye
    const patch = box(0.17, 0.12, 0.03, 0x050505); patch.position.set(-0.11, 1.69, 0.32); char.add(patch);
    char.refs.pupilL.material = mat(0x000000);
    char.refs.eyeL.material   = mat(0x111111);

    // Right eye — glowing cyan
    char.refs.pupilR.material = mat(0x00ddff, 0x00ddff, 3.0);

    // Spear (Gungnir)
    const spearShaft = cyl(0.028, 0.028, 2.2, 0xaaccee, 8); spearShaft.position.y = 0;
    const spearTip   = cone(0.07, 0.28, 0xffffff, 0xaaddff, 1.5); spearTip.position.y = 1.22;
    const spearGuard = box(0.28, 0.05, 0.05, 0xffd700, 0xffaa00, 0.4); spearGuard.position.y = 0.78;
    const spear = grp(spearShaft, spearTip, spearGuard);
    spear.position.set(0.82, 1.22, 0.18); spear.rotation.z = -0.2; char.add(spear);

    // Raven on right shoulder
    const ravenBody = sph(0.1, 0x0a0a0a); ravenBody.position.set(0,0,0);
    const ravenHead = sph(0.068, 0x111111); ravenHead.position.set(0, 0.11, 0.06);
    const ravenBeak = cone(0.025, 0.07, 0x222222); ravenBeak.position.set(0, 0.1, 0.13); ravenBeak.rotation.x = 0.8;
    const raven = grp(ravenBody, ravenHead, ravenBeak);
    raven.position.set(0.46, 1.42, 0.06); char.add(raven);

    const anims = { char, orbL, orbR, orbLight1, orbLight2, runeGlow, spear, raven, capeMesh };

    return function animate(dt, t) {
      char.position.y = 0.18 + Math.sin(t * 1.1) * 0.046;
      spear.rotation.z = -0.2 + Math.sin(t * 0.75) * 0.05;
      capeMesh.rotation.x = Math.sin(t * 0.6) * 0.04;
      orbL.position.y = 2.5 + Math.sin(t * 1.2) * 0.15;
      orbR.position.y = 2.5 + Math.sin(t * 1.2 + 1.3) * 0.15;
      orbLight1.intensity = 2.5 + Math.sin(t * 1.4) * 0.6;
      orbLight2.intensity = 2.0 + Math.sin(t * 1.1 + 0.9) * 0.6;
      runeGlow.intensity  = 1.2 + Math.sin(t * 2.0) * 0.4;
      raven.position.y    = 1.42 + Math.sin(t * 2.8) * 0.03;
      char.refs.pupilR.material.emissiveIntensity = 2.5 + Math.sin(t * 1.8) * 0.5;
    };
  }

  // ══════════════════════════════════════════════════════════════
  //  HEIMDALL — The Observatory
  // ══════════════════════════════════════════════════════════════

  function buildHEIMALL(scene) {
    scene.background = new THREE.Color(0x030011);
    scene.fog = new THREE.FogExp2(0x030011, 0.05);

    const amb = new THREE.AmbientLight(0x110022, 0.5); scene.add(amb);
    const dir = new THREE.DirectionalLight(0xaabbff, 1.0); dir.position.set(-2, 6, 4); dir.castShadow = true; scene.add(dir);
    const purpleL = ptLight(scene, 0x8833ff, 3.0, 0, 3.5, -1.5, 8);
    const cyanL   = ptLight(scene, 0x00ffcc, 1.8, -2, 1.5, 1, 5);
    const starL   = ptLight(scene, 0xffffff, 1.0, 1.5, 3.5, -2.5, 6);

    makeRoom(scene, { floor: 0x060220, wall: 0x040115 });

    // Star field on floor
    for (let i = 0; i < 80; i++) {
      const s = sph(0.012 + Math.random() * 0.022, 0xffffff, 0xaabbff, 1.2 + Math.random());
      s.position.set((Math.random() - 0.5) * 7.5, 0.2, (Math.random() - 0.5) * 6.5);
      scene.add(s);
    }

    // Star portal window (back wall)
    const portalRing = tor(1.05, 0.09, 0x5522cc, 0x9955ff, 2.0); portalRing.position.set(1.0, 3.2, -3.43); scene.add(portalRing);
    const portalInner = disk(0.96, 0x020010); portalInner.position.set(1.0, 3.2, -3.4); scene.add(portalInner);
    for (let i = 0; i < 40; i++) {
      const a = Math.random() * Math.PI * 2, r = Math.random() * 0.88;
      const ps = sph(0.018 + Math.random() * 0.028, 0xffffff, 0xeeeeff, 1.5 + Math.random());
      ps.position.set(1.0 + Math.cos(a) * r, 3.2 + Math.sin(a) * r, -3.38);
      scene.add(ps);
    }
    // Secondary smaller portal
    const portalRing2 = tor(0.55, 0.06, 0x3311aa, 0x7744ff, 1.5); portalRing2.position.set(-2.0, 2.3, -3.43); scene.add(portalRing2);
    const portalInner2 = disk(0.49, 0x010008); portalInner2.position.set(-2.0, 2.3, -3.4); scene.add(portalInner2);

    // Large telescope
    const telBase  = cyl(0.12, 0.15, 0.5, 0x334466, 10); telBase.position.y = 0.25;
    const telArm   = cyl(0.055, 0.055, 0.85, 0x2a3a55, 8); telArm.position.y = 0.42; telArm.rotation.z = -0.7;
    const telBarrel = cyl(0.12, 0.16, 1.5, 0x2a3a55, 10); telBarrel.position.set(0.6, 0.88, 0); telBarrel.rotation.z = -0.7;
    const telLens  = cyl(0.11, 0.11, 0.14, 0x1a2a44, 10); telLens.position.set(1.16, 0.42, 0); telLens.rotation.z = -0.7;
    const telescope = grp(telBase, telArm, telBarrel, telLens);
    telescope.position.set(2.2, 0.18, -1.2);
    scene.add(telescope);

    // Floating data panels
    [[- 2.5, 2.6, -1.0], [-2.5, 1.9, -1.8]].forEach(([x, y, z]) => {
      const panel = box(0.9, 0.6, 0.05, 0x080820, 0x4422aa, 0.3); panel.position.set(x, y, z); scene.add(panel);
      // Upward arrow on panel
      const arrow = box(0.07, 0.35, 0.06, 0x00ff88, 0x00cc66, 1.2); arrow.position.set(x + 0.1, y + 0.04, z + 0.03); scene.add(arrow);
      const arrowTip = cone(0.1, 0.14, 0x00ff88, 0x00ee77, 1.5); arrowTip.position.set(x + 0.1, y + 0.27, z + 0.03); scene.add(arrowTip);
    });

    // Character — ice blue
    const char = makeChar({ body: 0x5ec8e0, armCol: 0xd8f4ff, legCol: 0x5ec8e0, skinCol: 0xddf0f8 });
    char.position.set(0, 0.18, 0.8);
    scene.add(char);

    // Chest armor
    const chest = box(0.72, 0.7, 0.46, 0x4ab8d0); chest.position.set(0, 1.04, 0); chest.receiveShadow = true; char.add(chest);

    // White flowing cape
    const capeMesh = new THREE.Mesh(
      new THREE.PlaneGeometry(1.05, 1.45),
      mat(0xddeeff, 0, 0, { side: THREE.DoubleSide, transparent: true, opacity: 0.88 })
    );
    capeMesh.position.set(0, 1.08, -0.3); char.add(capeMesh);

    // Eyes — glowing bright cyan (far-sighted watcher)
    char.refs.eyeL.material = mat(0x00eeff, 0x00ffff, 3.5);
    char.refs.eyeR.material = mat(0x00eeff, 0x00ffff, 3.5);
    char.refs.pupilL.material = mat(0xffffff, 0xffffff, 2.0);
    char.refs.pupilR.material = mat(0xffffff, 0xffffff, 2.0);

    // Bifrost horn on left shoulder (gold curved arc)
    const horn = tor(0.3, 0.058, 0xffd700, 0xffcc00, 0.5, 16);
    horn.position.set(-0.4, 1.5, 0.08); horn.rotation.x = Math.PI / 2; horn.rotation.z = Math.PI * 0.35; char.add(horn);

    // Telescope in right hand
    const handscope = cyl(0.045, 0.06, 0.48, 0x2a3a55, 8); handscope.position.set(0.64, 0.82, 0.22); handscope.rotation.set(0.4, 0, -0.55); char.add(handscope);

    // Floating magnifier (orbiting)
    const magRing = tor(0.2, 0.035, 0xaaaaff, 0x8888ff, 0.8); magRing.position.set(1.0, 1.8, 0.4); char.add(magRing);

    const anims = { char, purpleL, cyanL, starL, horn, capeMesh, magRing };

    return function animate(dt, t) {
      char.position.y = 0.18 + Math.sin(t * 0.95) * 0.05;
      char.rotation.y = Math.sin(t * 0.28) * 0.14;
      horn.rotation.y = t * 0.6;
      capeMesh.rotation.x = Math.sin(t * 0.55) * 0.05;
      magRing.position.x = 1.0 + Math.cos(t * 1.2) * 0.22;
      magRing.position.z = 0.4 + Math.sin(t * 1.2) * 0.22;
      magRing.rotation.z = t * 1.0;
      purpleL.intensity = 2.8 + Math.sin(t * 1.4) * 0.6;
      cyanL.intensity   = 1.6 + Math.sin(t * 2.0) * 0.5;
      char.refs.eyeL.material.emissiveIntensity = 3.0 + Math.sin(t * 2.2) * 0.5;
      char.refs.eyeR.material.emissiveIntensity = 3.0 + Math.sin(t * 2.2) * 0.5;
    };
  }

  // ══════════════════════════════════════════════════════════════
  //  VULCAN — The Design Studio
  // ══════════════════════════════════════════════════════════════

  function buildVULCAN(scene) {
    scene.background = new THREE.Color(0x111111);
    scene.fog = new THREE.FogExp2(0x111111, 0.04);

    const amb = new THREE.AmbientLight(0x332211, 0.6); scene.add(amb);
    const dir = new THREE.DirectionalLight(0xffeecc, 1.3); dir.position.set(-2, 7, 5); dir.castShadow = true; scene.add(dir);
    const warmL  = ptLight(scene, 0xff9900, 3.5, 0, 4.0, 0.5, 9);
    const coolL  = ptLight(scene, 0x4444ff, 1.0, 3, 1.5, 1.5, 5);
    const fillL  = ptLight(scene, 0xffffff, 0.8, -2, 2, 2, 6);

    makeRoom(scene, { floor: 0xeeeeee, wall: 0xe0e0e0 });

    // Paint splatter circles on floor
    const splats = [
      [0xcc2200, -1.3, 0.7, 0.22], [0x0033cc, 0.9, -0.6, 0.18],
      [0x00aa22, -0.6, -1.3, 0.16], [0xff6600, 1.6, 0.4, 0.2],
      [0xffcc00, -2.0, -0.9, 0.14], [0xaa00cc, 0.5, 1.6, 0.19],
      [0xff0088, -0.3, 0.5, 0.11],  [0x00ccff, 2.2, -1.5, 0.13],
    ];
    splats.forEach(([c, x, z, r]) => {
      const s = new THREE.Mesh(new THREE.CircleGeometry(r, 10), new THREE.MeshBasicMaterial({ color: c }));
      s.rotation.x = -Math.PI / 2; s.position.set(x, 0.2, z); scene.add(s);
    });

    // Easel
    const eLeg1 = cyl(0.035, 0.035, 1.9, 0x9b7a3c, 6); eLeg1.position.set(-0.3, 0.95, -0.1); eLeg1.rotation.z = 0.22;
    const eLeg2 = cyl(0.035, 0.035, 1.9, 0x9b7a3c, 6); eLeg2.position.set(0.3, 0.95, -0.1);  eLeg2.rotation.z = -0.22;
    const eLeg3 = cyl(0.03, 0.03, 1.4, 0x9b7a3c, 6);  eLeg3.position.set(0, 0.7, 0.4);       eLeg3.rotation.x = 0.38;
    const canvas_ = box(1.05, 0.82, 0.04, 0xfafafa); canvas_.position.set(0, 1.38, -0.1);
    // Colorful art on canvas
    const p1 = box(0.28, 0.22, 0.05, 0xff2200); p1.position.set(-0.18, 1.45, -0.06);
    const p2 = box(0.32, 0.18, 0.05, 0x0033ff); p2.position.set(0.12, 1.26, -0.06);
    const p3 = box(0.2, 0.28, 0.05, 0xffcc00);  p3.position.set(0.08, 1.48, -0.06);
    const easel = grp(eLeg1, eLeg2, eLeg3, canvas_, p1, p2, p3);
    easel.position.set(-1.8, 0.18, -1.6); scene.add(easel);

    // Canvas artworks on left wall
    [[-3.92, 3.5, -0.5, 0xff3300], [-3.92, 2.6, -1.5, 0x0044ff], [-3.92, 3.5, -2.3, 0x00aa44]].forEach(([x, y, z, c]) => {
      const frame = box(0.06, 0.7, 0.55, 0xd4a855); frame.position.set(x, y, z); scene.add(frame);
      const art   = box(0.05, 0.6, 0.45, c, c, 0.5); art.position.set(x + 0.01, y, z); scene.add(art);
    });

    // Floating lightbulb
    const bulbSphere = sph(0.26, 0xfffff8, 0xffdd44, 3.0); bulbSphere.position.y = 0;
    const bulbNeck   = cyl(0.09, 0.12, 0.14, 0x999999, 8); bulbNeck.position.y = -0.21;
    const bulbBase   = cyl(0.11, 0.08, 0.1, 0x777777, 8);  bulbBase.position.y = -0.33;
    const bulbWire   = cyl(0.012, 0.012, 0.7, 0x555555, 6); bulbWire.position.y = -0.7;
    const bulb = grp(bulbSphere, bulbNeck, bulbBase, bulbWire);
    bulb.position.set(1.8, 3.6, -1.0); scene.add(bulb);

    // Round color palette on ground
    const palBase = disk(0.42, 0xf8f0e8); palBase.rotation.x = -Math.PI / 2; palBase.position.set(2.2, 0.2, 0.8); scene.add(palBase);
    [[0,0.35,0xff0000],[0.3,0.18,0x0000ff],[-0.28,0.15,0x00cc00],[0.1,-0.3,0xffcc00],[-0.2,-0.25,0xaa00aa]].forEach(([dx,dz,c]) => {
      const blob = disk(0.09, c); blob.rotation.x = -Math.PI / 2; blob.position.set(2.2 + dx, 0.21, 0.8 + dz); scene.add(blob);
    });

    // Character — bright orange
    const char = makeChar({ body: 0xff6600, armCol: 0xcc4400, legCol: 0xcc4400, skinCol: 0xf5a050 });
    char.position.set(0.2, 0.18, 0.7);
    scene.add(char);

    // Chest front plate (slightly darker)
    const chestFront = box(0.5, 0.55, 0.45, 0xdd5500); chestFront.position.set(0, 1.03, 0); char.add(chestFront);

    // Yellow hard hat
    const hatBrim  = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.05, 18), mat(0xffdd00));
    const hatCrown = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.4, 0.26, 18), mat(0xffdd00));
    hatCrown.position.y = 0.155;
    const hatStripe = new THREE.Mesh(new THREE.CylinderGeometry(0.302, 0.302, 0.07, 18), mat(0xff8800, 0xff6600, 0.3));
    hatStripe.position.y = 0.1;
    const hat = grp(hatBrim, hatCrown, hatStripe);
    hat.position.set(0, 1.96, 0); char.add(hat);

    // Goggles pushed up on forehead
    const gL = tor(0.085, 0.025, 0x222222); gL.position.set(-0.1, 1.83, 0.24); gL.rotation.x = Math.PI / 2; char.add(gL);
    const gR = tor(0.085, 0.025, 0x222222); gR.position.set(0.1, 1.83, 0.24); gR.rotation.x = Math.PI / 2; char.add(gR);
    const gBridge = box(0.06, 0.025, 0.025, 0x222222); gBridge.position.set(0, 1.83, 0.26); char.add(gBridge);

    // Paintbrush in right hand
    const brushHandle  = cyl(0.028, 0.028, 0.6, 0xc8852a, 8); brushHandle.position.y = 0;
    const brushFerule  = cyl(0.03, 0.03, 0.07, 0x888888, 8); brushFerule.position.y = 0.33;
    const brushBristle = cyl(0.04, 0.01, 0.15, 0xee8800, 8, 0xff6600, 0.8); brushBristle.position.y = 0.43;
    const brush = grp(brushHandle, brushFerule, brushBristle);
    brush.position.set(0.68, 0.82, 0.28); brush.rotation.set(0.5, 0, -0.5); char.add(brush);

    // Tablet in left hand (glowing screen)
    const tabletBody   = box(0.32, 0.24, 0.035, 0x222222); tabletBody.position.y = 0;
    const tabletScreen = box(0.28, 0.2, 0.04, 0x001133, 0x00aaff, 0.8); tabletScreen.position.y = 0.002;
    const tablet = grp(tabletBody, tabletScreen);
    tablet.position.set(-0.68, 0.8, 0.2); tablet.rotation.set(-0.3, 0.2, 0.5); char.add(tablet);

    // Floating paint sparks
    const sparks = [];
    for (let i = 0; i < 8; i++) {
      const ang = (i / 8) * Math.PI * 2;
      const sk = sph(0.04, [0xff2200,0x00aaff,0xffcc00,0x00cc44,0xaa00ff][i%5], [0xff0000,0x0088ff,0xffaa00,0x00ff44,0x8800ff][i%5], 2.0);
      sk.userData = { ang, dist: 0.7 + Math.random() * 0.4, speed: 0.8 + Math.random() * 0.5, phase: Math.random() * Math.PI * 2 };
      char.add(sk);
      sparks.push(sk);
    }

    const anims = { char, bulb, bulbSphere, warmL, brush, sparks, tablet };

    return function animate(dt, t) {
      char.position.y = 0.18 + Math.sin(t * 1.3) * 0.042;
      bulb.position.y = 3.6 + Math.sin(t * 0.9) * 0.12;
      bulbSphere.material.emissiveIntensity = 2.5 + Math.sin(t * 2.2) * 0.7;
      warmL.intensity = 3.2 + Math.sin(t * 1.8) * 0.8;
      brush.rotation.z = -0.5 + Math.sin(t * 3.5) * 0.12;
      sparks.forEach(sk => {
        const { ang, dist, speed, phase } = sk.userData;
        const a = ang + t * speed;
        sk.position.set(Math.cos(a) * dist, 1.2 + Math.sin(t * 1.5 + phase) * 0.35, Math.sin(a) * dist * 0.5);
        sk.material.emissiveIntensity = 1.5 + Math.sin(t * 3 + phase) * 0.8;
      });
    };
  }

  // ══════════════════════════════════════════════════════════════
  //  LOKI — The Marketplace
  // ══════════════════════════════════════════════════════════════

  function buildLOKI(scene) {
    scene.background = new THREE.Color(0x070010);
    scene.fog = new THREE.FogExp2(0x070010, 0.052);

    const amb = new THREE.AmbientLight(0x0a1a08, 0.55); scene.add(amb);
    const dir = new THREE.DirectionalLight(0xaaffaa, 0.9); dir.position.set(-2, 6, 4); dir.castShadow = true; scene.add(dir);
    const greenL  = ptLight(scene, 0x00cc55, 2.8, -1.5, 2.5, 0, 7);
    const purpleL = ptLight(scene, 0xbb44ff, 1.6, 2.5, 1.5, 1.5, 5);
    const goldL   = ptLight(scene, 0xffcc00, 1.2, 0, 2.8, -2.5, 5);

    makeRoom(scene, { floor: 0x1e1005, wall: 0x0d2210, trim: 0xffd700 });

    // Wood plank floor lines
    for (let i = -3; i <= 3; i++) {
      const plank = box(0.035, 0.012, 7, 0x2a1408, 0x1a0800, 0.2); plank.position.set(i * 1.1, 0.2, 0); scene.add(plank);
    }

    // Gold trim along wall base
    const baseTrim1 = box(8, 0.07, 0.08, 0xffd700, 0xffaa00, 0.3); baseTrim1.position.set(0, 0.22, -3.44); scene.add(baseTrim1);
    const baseTrim2 = box(0.08, 0.07, 7, 0xffd700, 0xffaa00, 0.3); baseTrim2.position.set(-3.94, 0.22, 0); scene.add(baseTrim2);

    // Storefront arch (back wall)
    const shopBg = box(2.4, 1.8, 0.07, 0x0a2a0e); shopBg.position.set(0, 2.7, -3.43); scene.add(shopBg);
    const archTop = tor(0.85, 0.09, 0xffd700, 0xffaa00, 0.5); archTop.position.set(0, 3.32, -3.38); scene.add(archTop);
    // Sign above arch
    const signBg = box(1.8, 0.3, 0.06, 0x0a1a08); signBg.position.set(0, 4.05, -3.41); scene.add(signBg);
    const signGold = box(0.04, 0.24, 0.07, 0xffd700, 0xffcc00, 0.6); [-0.7,-0.4,-0.1,0.2,0.5,0.8].forEach(x => { const s=signGold.clone(); s.position.set(x,4.05,-3.38); scene.add(s); });

    // Product display panels in arch
    [[-0.6, 2.62], [0, 2.62], [0.6, 2.62]].forEach(([x, y]) => {
      const frame  = box(0.42, 0.42, 0.06, 0x152a18); frame.position.set(x, y, -3.4); scene.add(frame);
      const inner  = box(0.35, 0.35, 0.07, 0x0a1a0c, 0x00aa44, 0.3); inner.position.set(x, y, -3.37); scene.add(inner);
    });

    // Floating price tags
    const tags = [];
    for (let i = 0; i < 5; i++) {
      const tag = new THREE.Group();
      const tagBody   = box(0.32, 0.22, 0.04, 0xffdd44); tag.add(tagBody);
      const tagString = cyl(0.012, 0.012, 0.12, 0x888855, 6); tagString.position.y = 0.17; tag.add(tagString);
      const tagHole   = tor(0.022, 0.008, 0x555533); tagHole.position.y = 0.24; tagHole.rotation.x = Math.PI/2; tag.add(tagHole);
      tag.position.set(-1.6 + i * 0.8, 2.1 + Math.sin(i * 1.3) * 0.3, -0.8);
      scene.add(tag);
      tags.push({ mesh: tag, phase: i * 1.1 });
    }

    // Mirror on left wall
    const mirrorFrame = box(0.08, 1.4, 1.0, 0xffd700); mirrorFrame.position.set(-3.93, 2.5, 0.5); scene.add(mirrorFrame);
    const mirrorSurf  = box(0.05, 1.28, 0.88, 0xaaccdd, 0x88aacc, 0.4); mirrorSurf.position.set(-3.9, 2.5, 0.5); scene.add(mirrorSurf);
    const mirrorShine = box(0.04, 0.15, 0.12, 0xffffff, 0xffffff, 1.2); mirrorShine.position.set(-3.88, 2.8, 0.15); scene.add(mirrorShine);

    // Character — deep green trickster
    const char = makeChar({ body: 0x1a6b2f, armCol: 0x111111, legCol: 0x155522, skinCol: 0xc8a872 });
    char.position.set(-0.2, 0.18, 0.8);
    char.rotation.y = 0.2;
    scene.add(char);

    // Green tunic
    const tunic = cyl(0.36, 0.43, 0.74, 0x1a6b2f, 14); tunic.position.y = 1.02; char.add(tunic);

    // Horned helmet
    const helmBase = new THREE.Mesh(new THREE.CylinderGeometry(0.33, 0.36, 0.22, 16), mat(0x1a1a2e));
    helmBase.position.y = 0;
    const mkHorn = (side) => {
      const seg1 = cyl(0.055, 0.038, 0.5, 0x1a1a2e, 8);  seg1.position.y = 0.28;
      const seg2 = cyl(0.038, 0.018, 0.4, 0x1a1a2e, 8);
      seg2.position.set(side * 0.18, 0.62, 0); seg2.rotation.z = side * -0.55;
      const seg3 = cyl(0.018, 0.005, 0.25, 0x1a1a2e, 6);
      seg3.position.set(side * 0.3, 0.88, 0); seg3.rotation.z = side * -0.8;
      return grp(seg1, seg2, seg3);
    };
    const lHorn = mkHorn(-1); lHorn.position.set(-0.3, 0.1, 0);
    const rHorn = mkHorn(1);  rHorn.position.set(0.3, 0.1, 0);
    const helmet = grp(helmBase, lHorn, rHorn);
    helmet.position.set(0, 1.86, 0); char.add(helmet);

    // Dark cape with gold trim
    const capeBody = new THREE.Mesh(new THREE.PlaneGeometry(0.92, 1.2), mat(0x0e3a14, 0, 0, { side: THREE.DoubleSide }));
    capeBody.position.set(0, 1.08, -0.28); char.add(capeBody);
    const capeTrimL = box(0.03, 1.2, 0.02, 0xffd700, 0xffcc00, 0.3); capeTrimL.position.set(-0.46, 1.08, -0.27); char.add(capeTrimL);
    const capeTrimR = capeTrimL.clone(); capeTrimR.position.set(0.46, 1.08, -0.27); char.add(capeTrimR);

    // Gold cards (playing cards fan) in right hand
    const cardColors = [0xffd700, 0xff3333, 0x3333ff, 0x33cc33];
    const cards = cardColors.map((c, i) => {
      const card = box(0.18, 0.24, 0.012, c, c, 0.3);
      card.position.set(0.64 + i * 0.03, 0.82 + i * 0.02, 0.22);
      card.rotation.z = -0.5 + i * 0.12;
      char.add(card);
      return card;
    });

    const anims = { char, tags, greenL, purpleL, cards, helmet };

    return function animate(dt, t) {
      char.position.y = 0.18 + Math.sin(t * 1.05) * 0.045;
      char.rotation.y = 0.2 + Math.sin(t * 0.35) * 0.18;
      tags.forEach(({ mesh, phase }) => {
        mesh.position.y = 2.1 + Math.sin(t * 1.2 + phase) * 0.2;
        mesh.rotation.z = Math.sin(t * 0.7 + phase) * 0.18;
      });
      cards.forEach((c, i) => { c.rotation.z = -0.5 + i * 0.12 + Math.sin(t * 2.0 + i * 0.4) * 0.06; });
      greenL.intensity  = 2.5 + Math.sin(t * 1.6) * 0.6;
      purpleL.intensity = 1.4 + Math.sin(t * 2.1) * 0.4;
    };
  }

  // ══════════════════════════════════════════════════════════════
  //  VAULT — The Treasury
  // ══════════════════════════════════════════════════════════════

  function buildVAULT(scene) {
    scene.background = new THREE.Color(0x010804);
    scene.fog = new THREE.FogExp2(0x010804, 0.05);

    const amb = new THREE.AmbientLight(0x1a1200, 0.55); scene.add(amb);
    const dir = new THREE.DirectionalLight(0xffeebb, 1.2); dir.position.set(-2, 7, 4); dir.castShadow = true; scene.add(dir);
    const goldL = ptLight(scene, 0xffaa00, 4.0, 0, 3.5, -1.0, 8);
    const coinL = ptLight(scene, 0xffd700, 2.0, 0.5, 1.5, 1.0, 5);
    const chandL = ptLight(scene, 0xffffcc, 1.5, 0, 4.8, -1.0, 6);

    makeRoom(scene, { floor: 0x040404, wall: 0x100802, trim: 0xffd700 });

    // Polished floor reflection plane
    const shine = box(7.8, 0.01, 6.8, 0x111111, 0x222200, 0.05); shine.position.y = 0.195; scene.add(shine);

    // Vault door (back wall centerpiece)
    const doorBg   = new THREE.Mesh(new THREE.CircleGeometry(1.05, 32), mat(0x111111)); doorBg.position.set(0, 2.8, -3.42); scene.add(doorBg);
    const outerRing = tor(1.05, 0.08, 0xffd700, 0xffaa00, 0.5); outerRing.position.set(0, 2.8, -3.38); scene.add(outerRing);
    const innerRing = tor(0.65, 0.055, 0xffd700, 0xffcc00, 0.3); innerRing.position.set(0, 2.8, -3.36); scene.add(innerRing);
    const midRing   = tor(0.85, 0.04, 0x888855); midRing.position.set(0, 2.8, -3.37); scene.add(midRing);
    // Spokes
    for (let i = 0; i < 8; i++) {
      const spoke = box(0.05, 1.88, 0.05, 0x333322); spoke.position.set(0, 2.8, -3.39); spoke.rotation.z = (i / 8) * Math.PI; scene.add(spoke);
    }
    // Handle
    const handle = tor(0.22, 0.06, 0x999966); handle.position.set(0.55, 2.8, -3.3); scene.add(handle);

    // Chandelier (ceiling)
    const chandBase = cyl(0.1, 0.1, 0.08, 0xffd700, 8); chandBase.position.set(0, 5.05, -1.0); scene.add(chandBase);
    const chandBar  = box(0.04, 0.04, 1.2, 0xffd700); chandBar.position.set(0, 4.88, -1.0); scene.add(chandBar);
    [-0.45, 0, 0.45].forEach(x => {
      const crystal = cyl(0.025, 0.01, 0.28, 0xaaffff, 6, 0xccffff, 1.0); crystal.position.set(x, 4.65, -1.0); scene.add(crystal);
    });

    // Coin stacks
    const mkStack = (x, z, n) => {
      for (let i = 0; i < n; i++) {
        const coin = new THREE.Mesh(
          new THREE.CylinderGeometry(0.16, 0.16, 0.055, 14),
          mat(0xffd700, 0xffaa00, 0.25)
        );
        coin.position.set(x, 0.22 + i * 0.057, z); scene.add(coin);
      }
    };
    mkStack(-2.2, -1.8, 8); mkStack(-2.6, -1.7, 5); mkStack(-1.8, -2.2, 6);
    mkStack(2.4, -2.0, 7); mkStack(2.0, -1.6, 4);

    // Open ledger
    const ledgerBase  = box(0.65, 0.09, 0.5, 0x1a0c00); ledgerBase.position.set(-2.8, 0.95, -0.8); scene.add(ledgerBase);
    const ledgerPages = box(0.62, 0.07, 0.48, 0xf5e8d0); ledgerPages.position.set(-2.8, 0.97, -0.79); scene.add(ledgerPages);
    // Page lines
    for (let i = 0; i < 5; i++) {
      const line = box(0.52, 0.006, 0.01, 0xaaaaaa); line.position.set(-2.8, 1.0, -0.95 + i * 0.08); scene.add(line);
    }

    // Character — gold/wealth
    const char = makeChar({ body: 0xd4a017, armCol: 0x8b6914, legCol: 0xb88c0f, skinCol: 0xe8c870 });
    char.position.set(0.3, 0.18, 0.7);
    scene.add(char);

    // Gold waistcoat
    const vest = box(0.7, 0.68, 0.44, 0xd4a017); vest.position.set(0, 1.04, 0); char.add(vest);
    const vestFront = box(0.22, 0.64, 0.46, 0xb8880f); vestFront.position.set(0, 1.04, 0); char.add(vestFront);

    // Top hat
    const hatBrim  = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.055, 18), mat(0x0c1a0c));
    const hatBody  = new THREE.Mesh(new THREE.CylinderGeometry(0.27, 0.27, 0.48, 18), mat(0x0c1a0c));
    hatBody.position.y = 0.265;
    const hatBand  = new THREE.Mesh(new THREE.CylinderGeometry(0.273, 0.273, 0.065, 18), mat(0xffd700, 0xffcc00, 0.3));
    hatBand.position.y = 0.055;
    const topHat = grp(hatBrim, hatBody, hatBand);
    topHat.position.set(0, 1.93, 0); char.add(topHat);

    // Monocle
    const monocle     = tor(0.1, 0.022, 0xffd700, 0xffcc00, 0.3); monocle.position.set(0.13, 1.67, 0.3); monocle.rotation.x = Math.PI / 2; char.add(monocle);
    const monocleChain = cyl(0.008, 0.008, 0.18, 0xffd700, 4); monocleChain.position.set(0.22, 1.57, 0.25); monocleChain.rotation.z = 0.6; char.add(monocleChain);

    // Wide grin — replace smile
    char.refs.smile.rotation.z = 0; // normal smile stays

    // Money bag in right hand
    const bagBody   = sph(0.2, 0xffd700, 0xffaa00, 0.2); bagBody.position.y = 0;
    const bagNeck   = cyl(0.06, 0.1, 0.12, 0xcc8800, 8); bagNeck.position.y = 0.22;
    const bagKnot   = sph(0.07, 0xffaa00); bagKnot.position.y = 0.34;
    const bag = grp(bagBody, bagNeck, bagKnot);
    bag.position.set(0.68, 0.75, 0.22); bag.rotation.z = -0.3; char.add(bag);

    // Orbiting gold coins
    const floatCoins = [];
    for (let i = 0; i < 7; i++) {
      const fc = new THREE.Mesh(
        new THREE.CylinderGeometry(0.12, 0.12, 0.034, 14),
        mat(0xffd700, 0xffaa00, 0.6)
      );
      char.add(fc);
      floatCoins.push({ mesh: fc, idx: i });
    }

    const anims = { char, goldL, coinL, floatCoins, outerRing };

    return function animate(dt, t) {
      char.position.y = 0.18 + Math.sin(t * 0.88) * 0.042;
      char.rotation.y = Math.sin(t * 0.22) * 0.1;
      outerRing.rotation.z = t * 0.04;
      floatCoins.forEach(({ mesh, idx }) => {
        const ang = t * 0.7 + (idx / 7) * Math.PI * 2;
        const rx = Math.cos(ang) * 0.85;
        const ry = 1.2 + Math.sin(t * 1.1 + idx) * 0.22;
        const rz = Math.sin(ang) * 0.45;
        mesh.position.set(rx, ry, rz);
        mesh.rotation.y = ang * 2;
        mesh.rotation.z = Math.sin(ang) * 0.5;
        mesh.material.emissiveIntensity = 0.4 + Math.sin(t * 3 + idx) * 0.3;
      });
      goldL.intensity = 3.5 + Math.sin(t * 1.3) * 0.8;
      coinL.intensity = 1.8 + Math.sin(t * 2.0) * 0.5;
    };
  }

  // ══════════════════════════════════════════════════════════════
  //  GUARDIAN — The Operations Hub
  // ══════════════════════════════════════════════════════════════

  function buildGUARDIAN(scene) {
    scene.background = new THREE.Color(0x0d0000);
    scene.fog = new THREE.FogExp2(0x0d0000, 0.055);

    const amb = new THREE.AmbientLight(0x220000, 0.45); scene.add(amb);
    const dir = new THREE.DirectionalLight(0xffbbbb, 1.0); dir.position.set(-2, 6, 4); dir.castShadow = true; scene.add(dir);
    const redL   = ptLight(scene, 0xff2200, 3.5, 0, 3.0, 0.5, 7);
    const whiteL = ptLight(scene, 0xffffff, 1.2, -2.5, 4, 2, 7);
    const accentL = ptLight(scene, 0xff4400, 2.0, 2, 1.5, 1, 5);

    makeRoom(scene, { floor: 0x111111, wall: 0x0a0a0a });

    // Steel floor hex tiles
    for (let r = 0; r < 6; r++) {
      for (let c = 0; c < 7; c++) {
        const hex = new THREE.Mesh(new THREE.CylinderGeometry(0.38, 0.38, 0.02, 6), mat(0x1a1a1a, 0x222222, 0.05));
        hex.rotation.y = Math.PI / 6;
        hex.position.set(-3 + c * 1.1, 0.2, -2.5 + r * 1.0); scene.add(hex);
      }
    }

    // Red warning strips along wall top
    for (let i = -3; i <= 3; i++) {
      const isRed = i % 2 === 0;
      const strip = box(0.9, 0.22, 0.08, isRed ? 0xdd1100 : 0x1a1a1a, isRed ? 0xff1100 : 0x0, isRed ? 1.8 : 0);
      strip.position.set(i * 1.1, 5.08, -3.43); scene.add(strip);
    }
    for (let i = -3; i <= 2; i++) {
      const isRed = i % 2 !== 0;
      const strip = box(0.08, 0.22, 0.9, isRed ? 0xdd1100 : 0x1a1a1a, isRed ? 0xff1100 : 0x0, isRed ? 1.8 : 0);
      strip.position.set(-3.93, 5.08, i * 1.0 + 0.5); scene.add(strip);
    }

    // Status screens on back wall
    const screens = [];
    [[-1.7, 2.8, 0xcc0000], [1.7, 2.8, 0xcc0000]].forEach(([x, y, c]) => {
      const bezel  = box(1.25, 1.0, 0.07, 0x0a0000); bezel.position.set(x, y, -3.42); scene.add(bezel);
      const screen = box(1.15, 0.9, 0.08, 0x0d0000, 0xff1100, 0.15); screen.position.set(x, y, -3.38); scene.add(screen);
      // Dynamic bar chart bars
      const bars = [];
      for (let i = 0; i < 6; i++) {
        const bh = 0.08 + Math.random() * 0.35;
        const bar = box(0.1, bh, 0.06, 0xff3300, 0xff1100, 0.8); bar.position.set(x - 0.46 + i * 0.18, y - 0.3 + bh/2, -3.34); scene.add(bar);
        bars.push({ mesh: bar, phase: i * 0.7, baseX: x - 0.46 + i * 0.18, baseY: y - 0.3 });
      }
      screens.push(bars);
    });

    // Central floor emblem (hexagon with glow ring)
    const emblem = new THREE.Mesh(new THREE.CylinderGeometry(0.62, 0.62, 0.025, 6), mat(0x220000, 0xff2200, 0.5));
    emblem.position.set(0, 0.215, 0.5); scene.add(emblem);
    const emblemRing = tor(0.64, 0.04, 0xff2200, 0xff0000, 1.2); emblemRing.position.set(0, 0.22, 0.5); scene.add(emblemRing);

    // Side console desk (right side)
    const desk = box(1.4, 0.5, 0.7, 0x1a1a1a); desk.position.set(2.5, 0.43, -1.2); scene.add(desk);
    const consoleScreen = box(1.2, 0.4, 0.06, 0x0d0000, 0xff2200, 0.3); consoleScreen.position.set(2.5, 0.88, -1.44); consoleScreen.rotation.x = -0.3; scene.add(consoleScreen);

    // Character — dark red ops commander
    const char = makeChar({ body: 0x8b1a1a, armCol: 0x5a5a6a, legCol: 0x6e1515, skinCol: 0xb87070 });
    char.position.set(-0.2, 0.18, 0.7);
    scene.add(char);

    // Tactical armor torso
    const armor = cyl(0.37, 0.44, 0.76, 0x1a1a2a, 14); armor.position.y = 1.02; char.add(armor);
    const chestPlate = box(0.54, 0.52, 0.46, 0x700e0e); chestPlate.position.set(0, 1.08, 0); char.add(chestPlate);
    // Armor stripes
    [[-0.12, 0.1], [0, 0.1], [0.12, 0.1]].forEach(([x]) => {
      const stripe = box(0.04, 0.42, 0.47, 0x4a0000, 0xff0000, 0.2); stripe.position.set(x, 1.05, 0); char.add(stripe);
    });

    // Silver shoulder plates
    const mkPlate = (side) => {
      const p = box(0.36, 0.16, 0.26, 0x888888, 0xaaaaaa, 0.12);
      p.position.set(side * 0.48, 1.24, 0); char.add(p);
      const trim = box(0.36, 0.04, 0.28, 0xe74c3c, 0xff3333, 0.5); trim.position.set(side * 0.48, 1.14, 0); char.add(trim);
    };
    mkPlate(-1); mkPlate(1);

    // Helmet
    const helmBase = new THREE.Mesh(new THREE.CylinderGeometry(0.31, 0.35, 0.28, 16), mat(0x1a1a2a));
    const helmVisor = box(0.52, 0.1, 0.34, 0x222233); helmVisor.position.set(0, -0.08, 0.1);
    const visorGlow = box(0.48, 0.06, 0.33, 0xff2200, 0xff1100, 1.5); visorGlow.position.set(0, -0.08, 0.13);
    const helmet = grp(helmBase, helmVisor, visorGlow);
    helmet.position.set(0, 1.9, 0); char.add(helmet);

    // Hexagon shield (left arm)
    const shieldFace = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.07, 6), mat(0x2a2a2a));
    shieldFace.rotation.x = Math.PI / 2;
    const shieldRing = new THREE.Mesh(new THREE.TorusGeometry(0.42, 0.045, 6, 6), mat(0xe74c3c, 0xff2200, 0.8));
    const shieldCore = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.09, 6), mat(0xe74c3c, 0xff0000, 1.5));
    shieldCore.rotation.x = Math.PI / 2;
    // Shield cross bars
    const shBar1 = box(0.8, 0.04, 0.04, 0x444444); shBar1.rotation.x = Math.PI / 2;
    const shBar2 = box(0.8, 0.04, 0.04, 0x444444); shBar2.rotation.set(Math.PI/2, Math.PI/3, 0);
    const shield = grp(shieldFace, shieldRing, shieldCore, shBar1, shBar2);
    shield.position.set(-0.78, 1.12, 0.32); shield.rotation.set(0.1, 0.35, 0); char.add(shield);

    // Glowing eyes through visor
    char.refs.eyeL.material = mat(0xff2200, 0xff0000, 3.0);
    char.refs.eyeR.material = mat(0xff2200, 0xff0000, 3.0);
    char.refs.pupilL.material = mat(0xff4400, 0xff2200, 2.0);
    char.refs.pupilR.material = mat(0xff4400, 0xff2200, 2.0);

    const allBars = screens.flat();
    const anims = { char, redL, accentL, emblem, emblemRing, shield, allBars };

    return function animate(dt, t) {
      char.position.y = 0.18 + Math.sin(t * 1.25) * 0.035;
      shield.rotation.y = 0.35 + Math.sin(t * 0.55) * 0.18;
      shield.rotation.z = Math.sin(t * 0.4) * 0.06;
      emblem.material.emissiveIntensity     = 0.4 + Math.abs(Math.sin(t * 1.4)) * 0.5;
      emblemRing.material.emissiveIntensity = 1.0 + Math.abs(Math.sin(t * 1.8)) * 0.8;
      redL.intensity   = 3.0 + Math.sin(t * 2.0) * 1.0;
      accentL.intensity = 1.6 + Math.sin(t * 1.5 + 1.0) * 0.5;
      // Animate screen bars
      allBars.forEach(({ mesh, phase, baseY }) => {
        const newH = 0.08 + 0.35 * (0.5 + 0.5 * Math.abs(Math.sin(t * 1.8 + phase)));
        mesh.scale.y = newH / 0.2;
        mesh.position.y = baseY + (newH * mesh.scale.y) / 2;
        mesh.material.emissiveIntensity = 0.6 + Math.sin(t * 2 + phase) * 0.4;
      });
      char.refs.eyeL.material.emissiveIntensity = 2.5 + Math.sin(t * 2.5) * 0.6;
      char.refs.eyeR.material.emissiveIntensity = 2.5 + Math.sin(t * 2.5) * 0.6;
    };
  }

  // ── Builder dispatch ────────────────────────────────────────────

  const BUILDERS = {
    ODIN: buildODIN, HEIMDALL: buildHEIMALL, VULCAN: buildVULCAN,
    LOKI: buildLOKI, VAULT: buildVAULT, GUARDIAN: buildGUARDIAN
  };

  // ── Public API ──────────────────────────────────────────────────

  function open(name, container) {
    dispose();
    if (!window.THREE) { console.warn('[GodRooms] Three.js not loaded'); return; }
    const builder = BUILDERS[name];
    if (!builder) return;

    container.innerHTML = '';
    const w = container.clientWidth  || 380;
    const h = container.clientHeight || 400;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setSize(w, h);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.1;
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 80);
    camera.position.set(0, 2.4, 5.2);
    camera.lookAt(0, 1.3, 0);

    // Mouse-drag orbit
    _dragYaw = 0;
    let isDragging = false, prevX = 0;
    const onDown = e => { isDragging = true; prevX = e.clientX ?? e.touches?.[0].clientX; };
    const onUp   = () => { isDragging = false; };
    const onMove = e => {
      if (!isDragging) return;
      const x = e.clientX ?? e.touches?.[0].clientX;
      _dragYaw += (x - prevX) * 0.006; prevX = x;
    };
    renderer.domElement.addEventListener('mousedown', onDown);
    renderer.domElement.addEventListener('touchstart', onDown, { passive: true });
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchend', onUp);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('touchmove', onMove, { passive: true });

    const clock = new THREE.Clock();
    const animateFn = builder(scene, clock);

    function loop() {
      _animId = requestAnimationFrame(loop);
      const dt = clock.getDelta();
      const t  = clock.getElapsedTime();
      // Slow auto-rotate + user drag yaw
      const totalYaw = t * 0.07 + _dragYaw;
      const camR = 5.2;
      camera.position.x = Math.sin(totalYaw) * camR;
      camera.position.z = Math.cos(totalYaw) * camR;
      camera.lookAt(0, 1.3, 0);
      animateFn(dt, t);
      renderer.render(scene, camera);
    }
    loop();
    _renderer = renderer;
  }

  function dispose() {
    if (_animId)    { cancelAnimationFrame(_animId); _animId = null; }
    if (_renderer)  {
      _renderer.dispose();
      if (_renderer.domElement?.parentNode) {
        _renderer.domElement.parentNode.removeChild(_renderer.domElement);
      }
      _renderer = null;
    }
  }

  return { open, dispose };
})();
