import streamlit as st
import numpy as np
import tensorflow as tf
from PIL import Image
import time
from statistics import mean

st.set_page_config(page_title="Cat vs Dog Classifier", page_icon="🐶", layout="centered")

# =========================
# Config
# =========================
UPLOAD_LIMIT = 20
CAT_LABEL, DOG_LABEL = "Cat", "Dog"
EMOJIS = {CAT_LABEL: "🐱", DOG_LABEL: "🐶"}

# =========================
# Styles (Modern + Animations)
# =========================
st.markdown("""
<style>
:root{
  --bg1: #10131a; --bg2:#1a2140; --bg3:#0f121a;
  --glass: rgba(255,255,255,0.08);
  --border: rgba(255,255,255,0.14);
  --text-sub: #bfc6e0;
  --brand: #6a5bff;
  --cat: #4ea1ff;
  --dog: #a06bff;
}
.stApp{ background: linear-gradient(135deg, var(--bg1) 0%, var(--bg2) 40%, var(--bg3) 100%); font-family: 'Inter', system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
h1{ color:#fff; text-align:center; margin-bottom:-6px; }
.sub-text{ color:var(--text-sub); text-align:center; font-size:15px; }

.upload-box{
  background: var(--glass);
  border: 2px dashed rgba(255,255,255,0.25);
  border-radius: 14px;
  padding: 20px;
  text-align: center;
  color: white;
  margin-bottom: 12px;
  backdrop-filter: blur(8px);
  transition: 0.25s;
}
.upload-box:hover{ border-color: var(--brand); box-shadow: 0 0 0 3px rgba(106,91,255,0.15) inset; }

/* Tweak Streamlit's actual dropzone too */
div[data-testid="stFileUploaderDropzone"]{
  border-radius: 14px !important;
  background: rgba(255,255,255,0.04) !important;
  border: 2px dashed rgba(255,255,255,0.25) !important;
  transition: 0.25s;
}
div[data-testid="stFileUploaderDropzone"]:hover{
  border-color: var(--brand) !important;
  box-shadow: 0 0 0 3px rgba(106,91,255,0.15) inset !important;
}

.image-card{
  background: var(--glass);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 12px;
  text-align: center;
  backdrop-filter: blur(10px);
  animation: fadein 0.55s ease-in;
  transition: 0.25s;
}
.image-card:hover{ transform: translateY(-6px); box-shadow: 0 8px 18px rgba(0,0,0,0.35); }
@keyframes fadein{ from{opacity:0; transform: translateY(10px);} to{opacity:1; transform: translateY(0);} }

.image-card img{ border-radius: 12px; width: 100%; height: 180px; object-fit: cover; }

.high-conf-cat{ box-shadow: 0 0 18px var(--cat); border: 1px solid var(--cat); }
.high-conf-dog{ box-shadow: 0 0 18px var(--dog); border: 1px solid var(--dog); }

.result-pill{
  padding: 6px 14px;
  background: rgba(74,144,226,.32);
  border-radius: 50px;
  font-weight: 700;
  color:white;
  display:inline-block;
  margin-top:10px;
  transform-origin: center;
  animation: pop 300ms ease-out;
}
@keyframes pop{
  0%{ transform: scale(0.85); opacity: 0.2; }
  60%{ transform: scale(1.07); opacity: 1; }
  100%{ transform: scale(1.0); }
}

.meta{
  color: var(--text-sub);
  font-size: 12px;
  margin-top: 8px;
}

.stButton>button{
  background: linear-gradient(90deg, #4e8cff, var(--brand));
  color: #fff; border-radius: 10px; padding: 10px 22px; font-size: 16px; border:none;
  transition: 0.25s; box-shadow: 0 0 10px rgba(0,0,0,0.25);
}
.stButton>button:hover{ transform: translateY(-2px); box-shadow: 0 6px 14px rgba(0,0,0,0.35); }

.summary-card{
  background: var(--glass);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 14px;
  color: #fff;
}

.model-card{
  background: rgba(255,255,255,0.06);
  border: 1px dashed rgba(255,255,255,0.24);
  border-radius: 12px;
  padding: 12px;
  color: #fff;
}

.sort-row{
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 12px;
  padding: 10px 12px;
  margin: 6px 0 14px 0;
}

/* Animated ring gauge */
.ring-wrap{
  width: 110px; height: 110px; margin: 8px auto 4px auto; position: relative;
}
.ring{
  transform: rotate(-90deg);
}
.ring text{
  font-family: 'Inter', sans-serif;
  fill: #ffffff;
  font-size: 16px;
  font-weight: 700;
}
.ring .bg{
  stroke: rgba(255,255,255,0.18);
  stroke-width: 10;
}
.ring .meter{
  stroke: var(--brand);
  stroke-width: 10;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.9s ease; /* smooth animation */
}
</style>
""", unsafe_allow_html=True)

# =========================
# Title
# =========================
st.markdown("<h1>🐱🐶 Cat vs Dog Classifier</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-text'>Upload multiple images & get instant predictions — premium UI</p>", unsafe_allow_html=True)

# =========================
# Load Model
# =========================
@st.cache_resource
def load_interpreter():
    interpreter = tf.lite.Interpreter(model_path="model.tflite")
    interpreter.allocate_tensors()
    return interpreter

interpreter = load_interpreter()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()
shape = input_details[0]["shape"]
H = int(shape[1]); W = int(shape[2])
LABELS = [CAT_LABEL, DOG_LABEL]

# =========================
# Helpers
# =========================
def predict(image: Image.Image):
    if image.mode != "RGB":
        image = image.convert("RGB")
    image = image.resize((W, H))
    arr = np.array(image, dtype=np.float32) / 255.0
    arr = np.expand_dims(arr, axis=0)
    interpreter.set_tensor(input_details[0]['index'], arr)
    interpreter.invoke()
    out = interpreter.get_tensor(output_details[0]['index'])
    conf = float(np.max(out))
    idx = int(np.argmax(out))
    return LABELS[idx], conf * 100

def ring_svg(percent: float) -> str:
    """
    Animated circular gauge using SVG.
    """
    # circle geometry
    r = 45
    cx, cy = 55, 55
    circumference = 2 * np.pi * r
    pct = max(0, min(100, percent))
    dash = circumference
    offset = circumference * (1 - pct/100.0)
    # SVG with text centered
    return f"""
    <div class="ring-wrap">
      <svg class="ring" width="110" height="110" viewBox="0 0 110 110">
        <circle class="bg" cx="{cx}" cy="{cy}" r="{r}" fill="none"></circle>
        <circle class="meter" cx="{cx}" cy="{cy}" r="{r}" fill="none"
          stroke-dasharray="{dash:.2f}" stroke-dashoffset="{offset:.2f}">
        </circle>
        <text x="{cx}" y="{cy+6}" text-anchor="middle">{pct:.0f}%</text>
      </svg>
    </div>
    """

# =========================
# Session
# =========================
if "upload_results" not in st.session_state:
    st.session_state.upload_results = []   # list of dicts: {img, label, conf, name}

# =========================
# Upload UI
# =========================
st.markdown("<div class='upload-box'>📤 Drag & drop images or click to browse</div>", unsafe_allow_html=True)
files = st.file_uploader("", type=["png","jpg","jpeg"], accept_multiple_files=True)

# Upload limit
if files and len(files) > UPLOAD_LIMIT:
    st.warning(f"⚠ You selected {len(files)} files. Only the first {UPLOAD_LIMIT} will be processed.")
    files = files[:UPLOAD_LIMIT]

# Buttons row (Predict left, Clear right)
left, right = st.columns([5,1])
with left:
    if files:
        if st.button("Predict Images ✅"):
            with st.spinner("Analyzing images... 🔍"):
                st.session_state.upload_results = []
                time.sleep(0.2)
                for f in files:
                    img = Image.open(f)
                    label, conf = predict(img)
                    name = getattr(f, "name", "image")
                    st.session_state.upload_results.append(
                        {"img": img, "label": label, "conf": conf, "name": name}
                    )
with right:
    if st.button("Clear ❌"):
        st.session_state.upload_results = []
        st.experimental_rerun()

# =========================
# Summary + Options
# =========================
if st.session_state.upload_results:
    # Summary stats
    confs = [r["conf"] for r in st.session_state.upload_results]
    labels = [r["label"] for r in st.session_state.upload_results]
    total = len(confs)
    cats = labels.count(CAT_LABEL)
    dogs = labels.count(DOG_LABEL)
    best_idx = int(np.argmax(confs))
    best_label = labels[best_idx]
    best_conf = confs[best_idx]
    avg_conf = mean(confs) if confs else 0.0

    # Dashboard
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("<div class='summary-card'><b>Total Images</b><br><h3 style='margin:6px 0;'>"
                    f"{total}</h3></div>", unsafe_allow_html=True)
    with c2:
        st.markdown("<div class='summary-card'><b>Cats</b><br><h3 style='margin:6px 0;'>"
                    f"{cats} 🐱</h3></div>", unsafe_allow_html=True)
    with c3:
        st.markdown("<div class='summary-card'><b>Dogs</b><br><h3 style='margin:6px 0;'>"
                    f"{dogs} 🐶</h3></div>", unsafe_allow_html=True)
    with c4:
        st.markdown("<div class='summary-card'><b>Avg Confidence</b><br><h3 style='margin:6px 0;'>"
                    f"{avg_conf:.2f}%</h3></div>", unsafe_allow_html=True)

    # Best result callout
    st.markdown(
        f"<div class='summary-card' style='margin-top:8px;'>"
        f"<b>Highest Confidence</b>: {best_conf:.2f}% ({best_label} {EMOJIS[best_label]})"
        f"</div>", unsafe_allow_html=True
    )

    # Sorting / Filtering row
    with st.container():
        st.markdown("<div class='sort-row'>", unsafe_allow_html=True)
        colsf = st.columns([1.5, 2, 2, 3])
        with colsf[0]:
            st.write("**View Options**")
        with colsf[1]:
            sort_mode = st.selectbox("Sort", ["Default", "Highest confidence"], label_visibility="collapsed")
        with colsf[2]:
            filter_mode = st.selectbox("Filter", ["All", "Only Cats", "Only Dogs"], label_visibility="collapsed")
        with colsf[3]:
            st.caption("Tip: Use ‘Highest confidence’ to surface your best predictions.")
        st.markdown("</div>", unsafe_allow_html=True)

    # Apply sort/filter
    results = list(st.session_state.upload_results)
    if filter_mode == "Only Cats":
        results = [r for r in results if r["label"] == CAT_LABEL]
    elif filter_mode == "Only Dogs":
        results = [r for r in results if r["label"] == DOG_LABEL]

    if sort_mode == "Highest confidence":
        results = sorted(results, key=lambda r: r["conf"], reverse=True)

    # =========================
    # Results Grid
    # =========================
    cols = st.columns(3)
    for i, r in enumerate(results):
        img, label, conf, name = r["img"], r["label"], r["conf"], r["name"]
        glow_class = "high-conf-cat" if (conf > 90 and label == CAT_LABEL) else \
                     "high-conf-dog" if (conf > 90 and label == DOG_LABEL) else ""

        with cols[i % 3]:
            st.markdown(f'<div class="image-card {glow_class}">', unsafe_allow_html=True)
            st.image(img, use_column_width=True)

            # Animated ring gauge (Style 3)
            st.markdown(ring_svg(conf), unsafe_allow_html=True)

            st.markdown(
                f"<span class='result-pill'>{EMOJIS[label]} {label}</span>",
                unsafe_allow_html=True
            )
            st.markdown(f"<div class='meta'>File: {name}</div>", unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

# =========================
# Model Info (collapsible)
# =========================
with st.expander("ℹ️ Model details"):
    st.markdown(
        f"""
<div class="model-card">
<b>Format:</b> TensorFlow Lite<br>
<b>Input size:</b> {W} × {H} (RGB, normalized 0–1)<br>
<b>Labels:</b> {CAT_LABEL}, {DOG_LABEL}<br>
<b>Notes:</b> Inference runs on CPU. Keep images under ~2–3 MB for best responsiveness.<br>
</div>
""",
        unsafe_allow_html=True
    )
