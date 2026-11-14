/* The 3D background: domain-warped noise lit like a glossy, iridescent solid, in the brand palette.
   One shared module for every page that carries it (home, sign in, register, the paid order page). It has no loop of its
   own: fx-scroll.js calls window.fxBg.tick(now) from its single requestAnimationFrame loop and keeps that loop going while
   tick() answers true. Colours are read from the CSS tokens (tokens.css), never written here.
   Quality: render scale min(devicePixelRatio, 1.5) * 0.5 on desktop and 0.35 on phones; one drop of the scale if the
   first 40 frames average slower than 24 fps; nothing is drawn while the tab is hidden (the loop stops). With reduced
   motion, html.fx-lite, or the "bg3d" switch it draws ONE still frame and never animates. If WebGL or the shader fails,
   the canvas stays hidden and the CSS gradient on body::before (always underneath) is what shows. */
(() => {
  "use strict";
  const root = document.documentElement;
  const cv = document.querySelector("canvas[data-bg3d]");
  if (!cv) return;
  const off = ((root.dataset && root.dataset.fxOff) || "").split(/\s+/).indexOf("bg3d") >= 0;
  const reduced = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const css = getComputedStyle(root);
  const token = (name) => css.getPropertyValue(name).trim();
  const num = (name, dflt) => { const v = parseFloat(token(name)); return isFinite(v) ? v : dflt; };
  const rgb = (hex) => { const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex); return m ? [1, 2, 3].map((i) => parseInt(m[i], 16) / 255) : null; };
  const cols = ["--amber", "--harley", "--white", "--sunset", "--violet", "--night"].map((n) => rgb(token(n)));
  if (cols.some((c) => !c)) return;                       // palette tokens missing: keep the CSS gradient
  let gl = null;
  try { gl = cv.getContext("webgl", { antialias: false, alpha: false, powerPreference: "low-power" }); } catch (e) { gl = null; }
  if (!gl) return;                                        // no WebGL: the gradient stays

  const vs = "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}";
  const fs = "precision mediump float;uniform vec2 r;uniform float t,g;uniform vec3 A,H,W,S,V,N;" +
    "float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}" +
    "float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1.,0.)),f.x),mix(h(i+vec2(0.,1.)),h(i+vec2(1.,1.)),f.x),f.y);}" +
    "float fbm(vec2 p){float a=.5,s=0.;for(int i=0;i<4;i++){s+=a*n(p);p=p*2.02+vec2(1.7,9.2);a*=.5;}return s;}" +
    "vec3 ramp(float s){float x=fract(s)*5.;vec3 c=mix(V,S,smoothstep(0.,1.,x));c=mix(c,A,smoothstep(1.,2.,x));c=mix(c,W,smoothstep(2.,2.6,x)*.85);c=mix(c,H,smoothstep(2.6,3.6,x));c=mix(c,V,smoothstep(3.6,5.,x));return c;}" +
    "void main(){vec2 p=(gl_FragCoord.xy-.5*r)/min(r.x,r.y);float T=t*.07;" +
    "vec2 q=vec2(fbm(p*1.5+T),fbm(p*1.5-T+4.));" +
    "float d=length(p-vec2(.42+.04*sin(T*3.),-.02+.03*cos(T*2.)))-.6-.09*q.x;" +
    "float m=smoothstep(.32,-.28,d);" +
    "float v=fbm(p*1.3+q*1.9+vec2(T,-T));" +
    "vec3 c=ramp(v*1.6+q.y*.7+T*.6);" +
    "float rim=pow(clamp(1.-abs(d+.18)*3.2,0.,1.),2.);" +
    "c+=rim*S*.35;" +
    "vec3 col=mix(N,c*g,m*.92);col+=pow(m,6.)*.08*W*g;" +
    "float vg=smoothstep(1.3,.2,length(p));col*=.55+.45*vg;" +
    "gl_FragColor=vec4(col,1.);}";
  const compile = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null; };
  const v = compile(gl.VERTEX_SHADER, vs), f = compile(gl.FRAGMENT_SHADER, fs);
  if (!v || !f) return;
  const pr = gl.createProgram();
  gl.attachShader(pr, v); gl.attachShader(pr, f); gl.linkProgram(pr);
  if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) return;
  gl.useProgram(pr);
  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, "p");
  gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const u = (n) => gl.getUniformLocation(pr, n);
  const uR = u("r"), uT = u("t"), uG = u("g");
  ["A", "H", "W", "S", "V", "N"].forEach((n, i) => gl.uniform3f(u(n), cols[i][0], cols[i][1], cols[i][2]));

  // knobs (fx-tuning.css): --bg-speed multiplies the drift, --bg-brightness is how bright the solid is (0.3 to 1)
  const phone = (window.matchMedia && window.matchMedia("(max-width: 700px)").matches) || Math.min(window.innerWidth, window.innerHeight) < 500;
  let scale = phone ? 0.35 : Math.min(window.devicePixelRatio || 1, 1.5) * 0.5;
  const speed = Math.max(0, num("--bg-speed", 1) * num("--fx-speed", 1));
  const glow = Math.min(1, Math.max(0.3, num("--bg-brightness", 0.75)));
  let t = 0, last = 0, frames = 0, sum = 0, dead = false, still = off || reduced;
  const STILL_T = 11;                                     // the moment the still frame shows

  const size = () => {
    const w = Math.max(2, Math.floor(window.innerWidth * scale)), h = Math.max(2, Math.floor(window.innerHeight * scale));
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; gl.viewport(0, 0, w, h); }
  };
  const draw = () => {
    if (dead) return;
    size();
    gl.uniform2f(uR, cv.width, cv.height); gl.uniform1f(uT, t); gl.uniform1f(uG, glow);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  };
  const freeze = () => { still = true; t = STILL_T; draw(); };

  const onResize = () => draw();
  window.addEventListener("resize", onResize, { passive: true });
  cv.addEventListener("webglcontextlost", (e) => { e.preventDefault(); dead = true; cv.classList.remove("on"); root.classList.remove("bg-gl"); }, false);
  window.addEventListener("pagehide", () => window.removeEventListener("resize", onResize), { once: true });

  t = STILL_T; draw();                                    // first frame at once, so the canvas is never blank
  cv.classList.add("on");
  root.classList.add("bg-gl");                            // the CSS gradient underneath stops drifting while the canvas covers it

  window.fxBg = {
    // called by the one loop in fx-scroll.js on every frame; true asks for another frame
    tick(now) {
      if (dead) return false;
      if (still) return false;
      if (root.classList.contains("fx-lite")) { freeze(); return false; }
      const dt = last ? now - last : 0;
      last = now;
      if (dt > 0 && dt < 250) {
        t += (dt / 1000) * speed;
        if (frames < 40) {                                // adaptive quality: slow start, one drop of the scale
          sum += dt; frames++;
          if (frames === 40 && sum / 40 > 42 && scale > 0.25) scale *= 0.6;
        }
      }
      draw();
      return true;
    },
    stop() { last = 0; },
    get animated() { return !still && !dead; },
  };
  if (still) freeze();
})();
