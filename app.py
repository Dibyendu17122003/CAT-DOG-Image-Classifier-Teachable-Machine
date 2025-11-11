import gradio as gr
import numpy as np
import tensorflow as tf
from PIL import Image, ImageFilter, ImageOps, ImageEnhance
from statistics import mean
import io, base64, functools
import json
import matplotlib.pyplot as plt

# =========================
# CONFIG
# =========================
CAT_LABEL, DOG_LABEL = "Cat", "Dog"
LABELS = [CAT_LABEL, DOG_LABEL]
EMOJIS = {"Cat": "🐱", "Dog": "🐶"}
UPLOAD_LIMIT = 20


# =========================
# LOAD TFLITE MODEL
# =========================
@functools.lru_cache(maxsize=1)
def load_interpreter():
    interpreter = tf.lite.Interpreter(model_path="model.tflite")
    interpreter.allocate_tensors()
    return interpreter


interpreter = load_interpreter()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()
shape = input_details[0]["shape"]
H, W = int(shape[1]), int(shape[2])


# =========================
# IMAGE ENHANCEMENT (gentle, automatic)
# =========================
def enhance_image(img_pil: Image.Image) -> Image.Image:
    # subtle auto-contrast
    img = ImageOps.autocontrast(img_pil, cutoff=1)
    # tiny sharpness via UnsharpMask
    img = img.filter(ImageFilter.UnsharpMask(radius=1.4, percent=140, threshold=3))
    # slight color pop
    img = ImageEnhance.Color(img).enhance(1.05)
    return img


# =========================
# PREDICT SINGLE IMAGE
# =========================
def predict_single(arr):
    image = Image.fromarray(arr).resize((W, H))
    arr2 = np.array(image, dtype=np.float32) / 255.0
    arr2 = np.expand_dims(arr2, axis=0)

    interpreter.set_tensor(input_details[0]["index"], arr2)
    interpreter.invoke()
    out = interpreter.get_tensor(output_details[0]["index"])[0]

    conf = float(np.max(out)) * 100
    label = LABELS[int(np.argmax(out))]
    return label, round(conf, 2)


# =========================
# PIE CHART BASE64
# =========================
def make_pie(cats, dogs):
    values = [cats, dogs]
    labels = ["Cats", "Dogs"]
    colors = ["#00eaff", "#b200ff"]

    fig, ax = plt.subplots(figsize=(2.1, 2.1))
    ax.pie(values, labels=labels, colors=colors, autopct="%1.0f%%", textprops={"color": "white"})
    ax.set_aspect("equal")
    fig.patch.set_facecolor("none")

    buf = io.BytesIO()
    plt.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"<img class='piechart' src='data:image/png;base64,{b64}'/>"


# =========================
# BUILD IMAGE GRID HTML ✅ (CENTER SINGLE IMAGE)
# + Drag & Drop + Lottie + Blur Backdrop
# =========================
def build_cards_html(results, theme):
    theme_class = "light" if theme == "Light" else "dark"

    # ✅ if only one image, center it
    if len(results) == 1:
        wrapper = "<div class='single-wrap gallery-wrap' id='gallery'>"
    else:
        wrapper = "<div class='grid gallery-wrap' id='gallery'>"

    # Lottie + Confetti CDNs (safe to include multiple times; browser caches)
    cdn_headers = """
    <script src="https://unpkg.com/@lottiefiles/lottie-player@latest/dist/lottie-player.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
    """

    # Drag & Drop script: makes .card draggable & sortable in-place (client only)
    drag_script = """
    <script>
    (function(){
      const grid = document.getElementById('gallery');
      if (!grid) return;
      const cards = grid.querySelectorAll('.card');
      cards.forEach((card, idx)=>{
        card.setAttribute('draggable', 'true');
        card.dataset.index = idx;
        card.addEventListener('dragstart', (e)=>{
          e.dataTransfer.setData('text/plain', idx.toString());
          card.classList.add('dragging');
        });
        card.addEventListener('dragend', ()=>{
          card.classList.remove('dragging');
        });
      });

      grid.addEventListener('dragover', (e)=>{
        e.preventDefault();
        const dragging = grid.querySelector('.dragging');
        const afterElement = getDragAfterElement(grid, e.clientY);
        if (!afterElement) {
          grid.appendChild(dragging);
        } else {
          grid.insertBefore(dragging, afterElement);
        }
      });

      function getDragAfterElement(container, y) {
        const elements = [...container.querySelectorAll('.card:not(.dragging)')];
        return elements.reduce((closest, child)=>{
          const box = child.getBoundingClientRect();
          const offset = y - box.top - box.height / 2;
          if (offset < 0 && offset > closest.offset) {
            return { offset: offset, element: child }
          } else {
            return closest
          }
        }, { offset: Number.NEGATIVE_INFINITY }).element
      }
    })();
    </script>
    """

    html = [f"{cdn_headers}<div class='app {theme_class}'><div class='stars'></div><div class='twinkling'></div>{wrapper}"]

    for r in results:
        # choose lottie based on label
        lottie_src = "https://assets9.lottiefiles.com/private_files/lf30_t26law.json" if r['label'] == "Cat" \
                     else "https://assets9.lottiefiles.com/packages/lf20_qp1q7mct.json"
        html.append(
            f"""
        <div class="card">
            <div class="inner">
                <div class="front">
                    <!-- Blurred background layer (sensitive background blur simulation) -->
                    <img class="blur-bg" src="data:image/png;base64,{r['b64_blur']}">
                    <img class="crop" src="data:image/png;base64,{r['b64']}">
                </div>
                <div class="back fadein">
                    <lottie-player class="pet-lottie" src="{lottie_src}" background="transparent" speed="1" loop autoplay></lottie-player>
                    <p class="lbl">{EMOJIS[r['label']]} {r['label']}</p>
                    <p class="conf">{r['conf']}%</p>
                </div>
            </div>
        </div>
        """
        )

    html.append("</div></div>")
    html.append(drag_script)
    return "".join(html)


# =========================
# MAIN PROCESSING
# =========================
def process(files, theme):
    if not files:
        return "<p style='color:#888'>Upload images to begin.</p>", "", "[]"

    results = []
    confs = []

    for f in files[:UPLOAD_LIMIT]:
        # Load & enhance image gently
        img = Image.open(f).convert("RGB")
        img = enhance_image(img)

        # For display: sharp 200x200 + blurred backdrop (background blur)
        thumb = img.copy().resize((200, 200))
        blur_bg = thumb.copy().filter(ImageFilter.GaussianBlur(8))

        # Array for prediction
        arr = np.array(img)
        label, conf = predict_single(arr)

        # Encode display images
        buf = io.BytesIO()
        thumb.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        buf2 = io.BytesIO()
        blur_bg.save(buf2, format="PNG")
        b64_blur = base64.b64encode(buf2.getvalue()).decode()

        results.append({"label": label, "conf": conf, "b64": b64, "b64_blur": b64_blur})
        confs.append(conf)

    # Sort as before (highest confidence)
    results.sort(key=lambda x: x["conf"], reverse=True)

    cats = sum(r["label"] == "Cat" for r in results)
    dogs = sum(r["label"] == "Dog" for r in results)
    avg_conf = mean(confs)
    top_conf = results[0]["conf"] if results else 0

    pie = make_pie(cats, dogs)

    # Bars
    bars = "<div class='bars'>"
    for r in results:
        bars += f"""
        <div class='bar-row'>
            <span class='bar-label'>{EMOJIS[r['label']]} {r['label']}</span>
            <div class='bar-outer'><div class='bar-inner' style='width:{r["conf"]}%;'></div></div>
            <span class='bar-num'>{r["conf"]}%</span>
        </div>
        """
    bars += "</div>"

    # ✅ Confetti trigger if strong performance (avg>=90 or top>=95)
    confetti_flag = (avg_conf >= 90.0) or (top_conf >= 95.0)
    confetti_script = f"""
    <script>
    (function(){{
      const ok = {str(confetti_flag).lower()};
      if (ok && window.confetti) {{
        // multiple bursts for celebration
        setTimeout(()=>{{
          confetti({{ particleCount: 80, spread: 70, origin: {{ y: 0.6 }} }});
          confetti({{ particleCount: 60, angle: 60, spread: 55, origin: {{ x: 0 }} }});
          confetti({{ particleCount: 60, angle: 120, spread: 55, origin: {{ x: 1 }} }});
        }}, 250);
      }}
    }})();
    </script>
    """

    # ✅ History (client-side localStorage). Append this run & render list under summary.
    # Saved fields: time (epoch), total, cats, dogs, avg_conf, top label/conf
    history_js = f"""
    <script>
    (function(){{
      const entry = {{
        t: Date.now(),
        total: {len(results)},
        cats: {cats},
        dogs: {dogs},
        avg: {avg_conf:.2f},
        top: "{results[0]['label'] if results else '-'}",
        topc: {top_conf if results else 0}
      }};
      try {{
        const key = 'cd_history';
        const raw = localStorage.getItem(key);
        const arr = raw ? JSON.parse(raw) : [];
        arr.unshift(entry);
        while (arr.length > 10) arr.pop(); // keep last 10
        localStorage.setItem(key, JSON.stringify(arr));

        // render
        const host = document.getElementById('history-box');
        if (host) {{
          host.innerHTML = arr.map((e, i)=>{{
            const d = new Date(e.t);
            const when = d.toLocaleString();
            return `
              <div class="hist-row">
                <div class="hist-left">
                  <span class="hist-dot"></span> <b>#${{i+1}}</b> • ${{when}}
                </div>
                <div class="hist-right">
                  <span>Total: ${{e.total}}</span>
                  <span>Cat: ${{e.cats}}</span>
                  <span>Dog: ${{e.dogs}}</span>
                  <span>Avg: ${{e.avg}}%</span>
                  <span>Top: ${{e.top}} (${ {top_conf} if True else ""})</span>
                </div>
              </div>
            `;
          }}).join('');
        }}
      }} catch(err) {{ console.warn('history err', err); }}
    }})();
    </script>
    """

    summary = f"""
    <div class="summary-card">
        <div class="summary-title">✨ AI Summary</div>

        <div class="summary-stats">
            <p><b>Total Images:</b> {len(results)}</p>
            <p><b>Cats:</b> {cats} 🐱</p>
            <p><b>Dogs:</b> {dogs} 🐶</p>
            <p><b>Average Confidence:</b> {avg_conf:.2f}%</p>
            <p><b>Top Prediction:</b> {results[0]['label']} {EMOJIS[results[0]['label']]} ({results[0]['conf']}%)</p>
        </div>

        <div class="pie-wrap">{pie}</div>
        {bars}

        <!-- History Section (client-side; persists in browser) -->
        <div class="history-card">
          <div class="history-title">🕘 History (Last 10)</div>
          <div id="history-box" class="history-list"></div>
        </div>

        {confetti_script}
        {history_js}
    </div>
    """

    return build_cards_html(results, theme), summary, json.dumps(results)


# =========================
# THEME CHANGE (no re-upload)
# =========================
def rerender(theme, results_json):
    try:
        results = json.loads(results_json)
    except:
        results = []
    return build_cards_html(results, theme)


# =========================
# FUTURISTIC CSS (+ additions for new features)
# =========================
css = """
/* ✅ Single image perfect centering */
.single-wrap{
  width:100%;
  display:flex;
  justify-content:center;
  margin-top:30px;
  position:relative;
  z-index:2;
}

/* ===== GLOBAL ===== */
:root{
  --text:#ffffff;
  --grad-1:#00eaff;
  --grad-2:#b200ff;
  --neon:rgba(0,255,255,0.45);
}
.app.dark{ background:#01020a; color:var(--text); }
.app.light{ background:#f8faff; color:#0b1220; }

/* ===== HEADER ===== */
h1{
  text-align:center;
  font-size:42px;
  font-weight:900;
  background:linear-gradient(90deg,var(--grad-1),var(--grad-2));
  -webkit-background-clip:text;
  color:transparent;
}
.sub{ text-align:center; color:#95a1c2; }

/* ===== STARRY BACKGROUND ===== */
.stars, .twinkling{
  position:fixed; top:0; left:0;
  width:100vw; height:100vh;
  pointer-events:none;
}
.stars{
  background:radial-gradient(2px 2px at 20% 30%, rgba(255,255,255,.6), transparent 60%),
             radial-gradient(1.5px 1.5px at 80% 70%, rgba(255,255,255,.5), transparent 60%),
             radial-gradient(2px 2px at 60% 20%, rgba(255,255,255,.6), transparent 60%),
             radial-gradient(1.5px 1.5px at 30% 80%, rgba(255,255,255,.5), transparent 60%);
  animation: drift 30s linear infinite;
  opacity:.4;
}
.twinkling{
  background:radial-gradient(circle at 10% 10%, rgba(255,255,255,.25) 0 2px, transparent 3px),
             radial-gradient(circle at 50% 60%, rgba(255,255,255,.2) 0 2px, transparent 3px),
             radial-gradient(circle at 90% 30%, rgba(255,255,255,.2) 0 2px, transparent 3px);
  animation: twinkle 3s ease-in-out infinite alternate;
  opacity:.3;
}
@keyframes drift{0%{transform:translateY(0)}100%{transform:translateY(-50px)}}
@keyframes twinkle{0%{opacity:.15}100%{opacity:.5}}

/* ===== IMAGE GRID ===== */
.grid{
  width:100%;
  max-width:1100px;
  margin:25px auto;
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(240px,1fr));
  justify-items:center;
  gap:22px;
  position:relative;
  z-index:2;
}

/* for drag feedback */
.gallery-wrap .card.dragging{
  opacity:.75;
  transform:scale(0.98);
  outline:2px dashed rgba(255,255,255,.25);
}

/* ===== CARD ===== */
.card{
  width:240px;
  height:300px;
  perspective:1000px;
  border-radius:24px;
  overflow:hidden;
  transform-style:preserve-3d;
  transition:transform .25s ease, box-shadow .25s ease;
  cursor:grab;
}
.card:active{ cursor:grabbing; }
.card:hover{
  transform:translateY(-6px) rotateX(5deg) rotateY(-5deg);
  box-shadow:0 18px 40px rgba(0,0,0,.35), 0 0 32px var(--neon);
}

/* ===== FLIP ===== */
.inner{
  width:100%; height:100%;
  border-radius:24px;
  transition:transform .9s;
  transform-style:preserve-3d;
}
.card:hover .inner{ transform:rotateY(180deg); }

.front, .back{
  position:absolute; inset:0;
  width:100%; height:100%;
  border-radius:24px;
  backface-visibility:hidden;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  background:linear-gradient(135deg, rgba(0,255,255,0.15), rgba(255,0,255,0.15));
  border:2px solid rgba(255,255,255,0.12);
  backdrop-filter:blur(10px);
}
.back{
  transform:rotateY(180deg);
  animation:fadein .9s ease forwards;
}
@keyframes fadein{0%{opacity:0; filter:blur(6px)}100%{opacity:1; filter:blur(0)}}

/* ===== IMAGE (sharp) + BACKGROUND BLUR LAYER ===== */
.front{
  position: relative;
}
.blur-bg{
  position:absolute;
  width:220px; height:220px;
  border-radius:20px;
  object-fit:cover;
  filter: blur(12px) brightness(0.9);
  transform: scale(1.02);
  z-index:0;
}
.crop{
  position:relative;
  z-index:1;
  width:200px; height:200px;
  border-radius:18px;
  object-fit:cover;
  border:2px solid rgba(0,255,255,0.4);
  box-shadow:0 0 25px rgba(0,255,255,0.25);
  transition:.25s;
}
.crop:hover{
  transform:scale(1.05);
  box-shadow:0 0 35px rgba(0,255,255,0.4);
}

/* ===== LOTTIE ICON ===== */
.pet-lottie{
  width:80px; height:80px;
  margin-bottom:4px;
}

/* ===== LABELS ===== */
.lbl{ font-size:20px; font-weight:700; }
.conf{ font-size:18px; color:#00eaff; font-weight:600; }

/* ===== SUMMARY CARD (as you had, kept) ===== */
.summary-card{
  width: clamp(300px, 85%, 760px);
  margin: 35px auto;
  padding: 30px 32px;
  border-radius: 28px;
  background: rgba(255,255,255,0.05);
  border: 1.5px solid rgba(255,255,255,0.18);
  backdrop-filter: blur(18px);
  animation: summaryPop 0.7s ease forwards;
  position: relative;
  overflow: hidden;
  transition: 0.35s;
  box-shadow: 0 0 25px rgba(0,255,255,0.12), inset 0 0 40px rgba(255,0,255,0.05);
}
.summary-card:hover{
  transform: translateY(-6px) scale(1.015);
  box-shadow: 0 0 36px rgba(0,255,255,0.35), 0 0 18px rgba(255,0,255,0.15);
}
.summary-card::before{
  content: "";
  position: absolute;
  top: -120%;
  left: -120%;
  width: 350%;
  height: 350%;
  background: radial-gradient(circle, rgba(0,255,255,0.22) 0%, transparent 60%);
  animation: floatGlow 8s linear infinite;
  pointer-events:none;
}
@keyframes floatGlow{
  0%{ transform: translate(0,0) rotate(0deg); }
  100%{ transform: translate(20px,20px) rotate(360deg); }
}
.summary-title{
  font-size: 27px;
  font-weight: 900;
  text-align: center;
  letter-spacing: 1.2px;
  background: linear-gradient(90deg,var(--grad-1),var(--grad-2),#ffffff,var(--grad-2));
  -webkit-background-clip:text;
  color: transparent;
  padding-bottom: 8px;
  animation: fadeSlide .7s ease;
}
.summary-stats{
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}
.summary-stats p{
  font-size: 17px;
  font-weight: 500;
  margin: 0;
  opacity: .92;
  animation: fadeSlide .75s ease;
}
@keyframes fadeSlide{
  0%{ opacity:0; transform: translateY(10px); }
  100%{ opacity:1; transform: translateY(0); }
}

/* PIE */
.pie-wrap{
  width:100%;
  display:flex;
  justify-content:center;
  align-items:center;
  margin: 22px 0;
  position: relative;
}
.pie-wrap::before{
  content:"";
  position:absolute;
  width:180px;
  height:180px;
  border-radius:50%;
  background: radial-gradient(circle, rgba(0,255,255,0.22) 0%, transparent 70%);
  filter: blur(22px);
  z-index:0; opacity:.8;
}
.piechart{
  width:165px; height:165px; border-radius:50%;
  animation: pieLift .8s ease; z-index:2; transition:.28s;
  filter: drop-shadow(0 0 10px rgba(0,255,255,.4));
}
.piechart:hover{
  transform: scale(1.07);
  filter: drop-shadow(0 0 22px rgba(0,255,255,.75));
}
@keyframes pieLift{
  0%{ transform: scale(.8); opacity:0; }
  100%{ transform: scale(1); opacity:1; }
}

/* Bars */
.bars{ margin-top: 14px; }
.bar-row{
  display: flex; align-items: center; gap: 10px; margin: 10px 0;
  animation: barFade .7s ease;
}
@keyframes barFade{
  from{opacity:0; transform: translateX(-10px);}
  to{opacity:1; transform: translateX(0);}
}
.bar-label{ width: 98px; font-weight: 600; }
.bar-outer{
  flex: 1; height: 13px; border-radius: 20px;
  background: rgba(255,255,255,0.15); overflow: hidden; position: relative;
  box-shadow: inset 0 0 8px rgba(0,0,0,0.25);
}
.bar-inner{
  height: 100%;
  border-radius: 20px;
  background: linear-gradient(90deg,#00eaff,#b200ff,#ff00ff);
  animation: fillBar 1.4s ease forwards;
  box-shadow: 0 0 10px rgba(0,255,255,0.5);
}
@keyframes fillBar{ from{width: 0%;} to{width: var(--target);} }
.bar-num{ width: 60px; text-align: right; font-size: 15px; font-weight: 600; opacity: 0.9; }

/* History card (client-side) */
.history-card{
  margin-top:18px; padding:14px 16px;
  border:1px dashed rgba(255,255,255,0.22);
  border-radius:14px; background:rgba(255,255,255,0.05);
}
.history-title{
  font-weight:800; margin-bottom:8px;
  background:linear-gradient(90deg,var(--grad-1),var(--grad-2));
  -webkit-background-clip:text; color:transparent;
}
.history-list{ display:flex; flex-direction:column; gap:6px; }
.hist-row{
  display:flex; justify-content:space-between; gap:10px;
  border-bottom:1px solid rgba(255,255,255,0.08); padding:6px 0;
}
.hist-left{ display:flex; align-items:center; gap:8px; opacity:.95; }
.hist-right{ display:flex; gap:10px; flex-wrap:wrap; font-size:13px; opacity:.9; }
.hist-dot{ width:7px; height:7px; border-radius:50%; background:linear-gradient(90deg,var(--grad-1),var(--grad-2)); display:inline-block; }

/* Animations */
@keyframes summaryPop{
  0%{ opacity:0; transform: translateY(25px) scale(.97); }
  100%{ opacity:1; transform: translateY(0) scale(1); }
}
"""


# =========================
# BUILD UI
# =========================
with gr.Blocks(css=css) as demo:
    gr.HTML("<h1>🐱🐶 Futuristic Cat vs Dog</h1>")
    gr.HTML("<p class='sub'>Flip • 3D Tilt • Glow • Sparkles • Charts • Light/Dark theme</p>")

    theme = gr.Radio(["Dark", "Light"], value="Dark", label="Theme")
    files = gr.Files(label="Upload Images", file_types=["image"], file_count="multiple")
    btn = gr.Button("🚀 Analyze Images", variant="primary")

    gallery = gr.HTML()
    summary = gr.HTML()
    state = gr.State("[]")

    btn.click(process, inputs=[files, theme], outputs=[gallery, summary, state])
    theme.change(rerender, inputs=[theme, state], outputs=[gallery])

demo.launch()
