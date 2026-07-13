# © 2025-2026 Tony Gheeraert - Licence MIT (voir LICENSE)
# Module extrait de build_site.py (découpage sans changement fonctionnel).

# -------------------------
# Default assets
# -------------------------

DEFAULT_CSS = """
:root { --max: 1120px; --accent: #005a9c; --header: #2e2a22; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; line-height: 1.45; color: #111; background: #fafafa; }
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
header { background: var(--header); color: #fff; position: sticky; top: 0; z-index: 10; }
.wrap { max-width: var(--max); margin: 0 auto; padding: 14px 16px; }
.brand { display:flex; align-items:center; justify-content: space-between; gap: 12px; }
.brand-left { display:flex; align-items:center; gap: 12px; min-width: 0; }
.brand-logos { display:flex; align-items:center; gap: 10px; }
.brand-logos img { display:block; height: 38px; width: auto; }
.brand-text { min-width: 0; }
.brand-title { font-weight: 760; font-size: 1.55rem; line-height: 1.12; }
.brand-sub { color: rgba(255,255,255,0.90); font-size: 1.10rem; font-style: italic; font-weight : 400; margin-top: 3px; }
.nav { display:flex; gap: 18px; margin-top: 10px; align-items:center; flex-wrap: wrap; border-top: 1px solid rgba(255,255,255,0.12); padding-top: 10px; }
.nav a { color: #fff; opacity: 0.92; font-weight: 520; }
.nav a.active { opacity: 1; text-decoration: underline; text-decoration-color: rgba(255,255,255,0.85); text-underline-offset: 3px; }
main.wrap { padding-top: 18px; padding-bottom: 26px; }
h1, h2, h3 { margin: 0.6rem 0 0.4rem; }
.small { color: #444; font-size: 0.95rem; }
.book-subtitle { font-size: 1.12rem; font-weight: 700; font-style: normal; margin-top: 4px; }
.book-credit { font-size: 1.10rem; font-weight: 450; margin-top: 8px; }
.book-meta { margin-top: 10px; }
.book-meta .meta-line { margin: 6px 0; }
.book-meta .meta-label { font-weight: 0; }
.grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; margin-top: 14px; }
.card { background:#fff; border: 1px solid #e6e6e6; border-radius: 12px; padding: 12px; display:flex; gap: 12px; box-shadow: 0 1px 0 rgba(0,0,0,0.02); }
.collection-desc { 
  margin: 10px 0 10px; 
  text-align: justify; 
  position: relative; 
}
.collection-issn{
  margin-top: -6px;
  margin-bottom: 12px;
  text-align: left;
}

.collection-desc p:first-child { margin-top: 0; }
.cover { width: 76px; height: 110px; flex: 0 0 76px; border-radius: 8px; border: 1px solid #eee; background: #f3f3f3; object-fit: cover; }
.meta { flex: 1; min-width: 0; }
.card .meta a { display: block; }
.card .meta a strong {
  font-size: 1.12rem;
  font-weight: 750;
  line-height: 1.2;
}
.card .book-subtitle {
  font-size: 0.98rem;
  font-weight: 650;
  margin-top: 4px;
}
/* État replié : hauteur fixe + masque dégradé */
.collection-desc.clamped {
  max-height: 220px; /* Hauteur de l'extrait visible (~10 lignes) */
  overflow: hidden;
}
.collection-desc.clamped::after {
  content: "";
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 80px;
  background: linear-gradient(to bottom, transparent, #fafafa); /* Doit correspondre au background body */
  pointer-events: none;
}

/* Le bouton "Lire la suite" */
.desc-toggle {
  display: inline-block;
  background: none;
  border: none;
  padding: 0;
  color: var(--accent);
  cursor: pointer;
  font-size: 0.95rem;
  font-weight: 600;
  margin-bottom: 20px;
  text-decoration: underline;
}
.desc-toggle:hover { text-decoration: none; }
.badges { margin-top: 6px; display:flex; gap: 6px; flex-wrap: wrap; }
.badge { display:inline-block; padding: 2px 8px; border-radius: 999px; border: 1px solid #e1e1e1; font-size: 0.82rem; color:#333; background:#fcfcfc; }
.badge-oa { border-color: var(--accent); font-weight: 650; }
.badges a.badge:hover { text-decoration: none; background:#f3f3f3; }
.social-strip { margin: 10px 0 16px; }
.social-strip-title { margin: 0 0 8px; font-weight: 650; }
.social-links { display:flex; gap: 8px; flex-wrap: wrap; align-items:center; }
.social-badge { display:inline-flex; align-items:center; gap: 8px; padding: 7px 10px; border-radius: 999px; border: 1px solid #e1e1e1; font-size: 0.92rem; color:#333; background:#fcfcfc; }
.social-badge:hover { text-decoration:none; background:#f3f3f3; }
.social-badge img { width: 18px; height: 18px; object-fit: contain; display:block; }
.social-strip{
  margin: 10px 0 18px;
  padding: 12px;
  background:#fff;
  border: 1px solid #e6e6e6;
  border-radius: 12px;
}
.social-strip-title{
  font-weight: 700;
  margin-bottom: 8px;
}
.social-strip .badges{
  margin-top: 0;
}
.toolbar { display:flex; gap: 10px; flex-wrap: wrap; align-items:center; margin: 12px 0; }
input[type="search"], select { padding: 10px 12px; border: 1px solid #cfcfcf; border-radius: 10px; font-size: 1rem; background: #fff; }
input[type="search"] { flex: 1; min-width: 240px; }
.btn { display:inline-block; padding: 10px 12px; border-radius: 10px; border: 1px solid #dedede; background: #fff; color:#111; }
.btn:hover { background:#f3f3f3; text-decoration:none; }
footer { border-top: 1px solid #e5e5e5; background: #fff; }
footer .wrap { color:#666; font-size: 0.9rem; padding-top: 18px; padding-bottom: 18px; }
.footer-grid { display:flex; gap: 18px; align-items:center; justify-content:space-between; flex-wrap:wrap; }
.footer-left { min-width: 260px; }
.footer-left div { margin: 4px 0; }
.footer-right img { height: 56px; width: auto; }
.footer-right a { display:inline-block; }

/* Lightbox (cover) */
.lightbox{
  position: fixed;
  inset: 0;
  display: flex;                 /* ✅ toujours présent */
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 9999;

  opacity: 0;
  visibility: hidden;            /* ✅ caché mais animable */
  pointer-events: none;          /* ✅ pas cliquable quand fermé */
  background: rgba(0,0,0,0.0);

  transition: opacity 320ms ease, background 180ms ease, visibility 0s linear 180ms;
}

.lightbox.open{
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
  background: rgba(0,0,0,0.85);

  transition: opacity 320ms ease, background 180ms ease, visibility 0s;
}

.lightbox img{
  max-width: min(980px, 95vw);
  max-height: 92vh;
  width: auto;
  height: auto;
  border-radius: 12px;
  background: #fff;

  transform: scale(0.96);
  transition: transform 320ms ease;
}

.lightbox.open img{
  transform: scale(1);
}

.lightbox-close{
  position: absolute;
  top: 14px;
  right: 18px;
  font-size: 28px;
  line-height: 1;
  color: #fff;
  cursor: pointer;
  user-select: none;
}

.cover-zoom{ cursor: zoom-in; }

@media (prefers-reduced-motion: reduce){
  .lightbox, .lightbox img { transition: none; }
}

/* Loupe de recherche dans le menu */
.nav-search{
  margin-left: auto;       /* pousse la loupe à droite */
  font-size: 1.15rem;
  opacity: 0.9;
  line-height: 1;
}

.nav-search:hover{
  opacity: 1;
  text-decoration: none;
}

.brand-sub { 
  color: rgba(255,255,255,0.90);
  font-size: 1.10rem;
  font-style: italic;
  font-weight: 400;
  margin-top: 3px;
}

/* Ligne slogan + recherche */
.brand-subrow{
  display:flex;
  align-items:center;
  flex-wrap:wrap;
  gap:12px;
}

/* Le slogan occupe l'espace dispo */
.brand-subtitle-text{
  flex: 1 1 auto;
  min-width: 18ch;     /* évite l’écrasement sur certaines largeurs */
}

/* Le bloc "Rechercher : 🔍" part à droite */
.brand-search-wrap{
  margin-left: auto;   /* <-- la clé */
  padding-left: 24px;  /* <-- espace “respirant” après le slogan */
  white-space: nowrap; /* évite le retour à la ligne au milieu */
  font-style: normal;
}



/* Mobile : réduire le bandeau pour rendre le scroll confortable */
@media (max-width: 720px){
  header .wrap{ padding: 8px 12px; }
  .brand-title{ font-size: 1.15rem; }
  .brand-sub{ font-size: 0.95rem; margin-top: 2px; }
  .brand-logos img{ height: 28px !important; } /* override la hauteur config */

  /* Menu sur 1 ligne, scrollable horizontalement */
  .nav{
    flex-wrap: nowrap;
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    gap: 12px;
    margin-top: 8px;
    padding-top: 8px;
  }

  /* Option : gagner encore + de place */
  /* .brand-subtitle-text{ display:none; } */
}


hr { border:0; border-top:1px solid #e6e6e6; margin: 18px 0; }
.kv { display:grid; grid-template-columns: 150px 1fr; gap: 10px 14px; margin: 14px 0; }
.k { color:#555; }
pre { white-space: pre-wrap; background:#fff; border:1px solid #eee; border-radius: 12px; padding: 12px; }

/* =========================
   Carrousel actualités
   ========================= */

.newsbar{
  background: #fff;
  border-bottom: 1px solid #e6e6e6;
}
.newsbar .wrap{
  padding-top: 10px;
  padding-bottom: 10px;
}
.newsbar-title{
  display:flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.newsbar-title h2{
  font-size: 1.05rem;
  margin: 0;
}
.newsbar-title a{
  font-size: 0.95rem;
  color: var(--accent);
}

/* Le “viewport” du carrousel */
.news-carousel{
  position: relative;
}

/* La piste : on masque tout ce qui dépasse, et on ne scroll plus à la main */
.news-track{
  display:flex;
  overflow: hidden;          /* ✅ une seule visible */
  scroll-behavior: smooth;   /* ✅ animation douce sur scrollTo */
  padding: 0;                /* ✅ pas de marge latérale qui gêne le calcul */
}

/* Une slide = 100% de la largeur */
.news-item{
  flex: 0 0 100%;            /* ✅ 1 item = 100% */
  border: 1px solid #e6e6e6;
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 1px 0 rgba(0,0,0,0.02);
}

/* Le lien couvre toute la slide */
.news-link{
  display:block;
  color: inherit;
}

.news-img{
  width: 100%;
  height: 220px;             /* ✅ hauteur maîtrisée */
  object-fit: cover;
  display:block;
  background:#f3f3f3;
}

@media (max-width: 720px){
  .news-img{ height: 170px; }
}

.news-meta{
  padding: 10px 12px;
}
.news-meta .t{
  font-weight: 750;
  line-height: 1.2;
}
.news-meta .d{
  margin-top: 4px;
  font-size: 0.92rem;
  color: #555;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* Flèches : toujours présentes (desktop + mobile) */
.news-btn{
  position:absolute;
  top: 75px;                 /* ~ milieu de l’image (150px/2) */
  transform: translateY(-50%);
  border: 1px solid #ddd;
  background: rgba(255,255,255,0.92);
  border-radius: 999px;
  width: 36px;
  height: 36px;
  cursor: pointer;
  display:flex;
  align-items:center;
  justify-content:center;
  user-select:none;
  z-index: 2;
}
.news-btn:hover{ background:#fff; }
.news-prev{ left: 8px; }
.news-next{ right: 8px; }

/* Accessibilité : focus visible */
.news-btn:focus{
  outline: 2px solid rgba(0,90,156,0.35);
  outline-offset: 2px;
}

/* Hover cartes Actualités */
.news-card{
  transition: transform 140ms ease, box-shadow 140ms ease, border-color 140ms ease;
}
.news-card:hover{
  transform: translateY(-2px);
  box-shadow: 0 10px 26px rgba(0,0,0,0.08);
  border-color: rgba(0,0,0,0.10);
}
.news-card:hover .news-card-title{
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce){
  .news-card{ transition: none; }
  .news-card:hover{ transform: none; }
}

/* Petites capitales (contenu éditorial : actualités, etc.) */
.small-caps{
  font-variant: small-caps;
  font-variant-caps: small-caps;
}

/* Pagination progressive des grilles de cartes (collections, revues).
   La classe n'est posée que par JS : sans JS, toutes les cartes restent visibles. */
.card-progressive-hidden{ display:none; }
"""

# Taille commune des lots de cartes : catalogue général (PAGE_SIZE côté JS)
# et révélation progressive des pages de collections et de revues.
CARD_PAGE_SIZE = 60

DEFAULT_JS = r"""
const PAGE_SIZE = __CARD_PAGE_SIZE__;
let limit = PAGE_SIZE;
let timer = null;

async function loadCatalogue() {
  const res = await fetch("./catalogue.json");
  return await res.json();
}
function esc(s){return String(s||"")
  .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
  .replaceAll('"',"&quot;").replaceAll("'","&#039;");}
function normalize(s){return (s||"").toLowerCase().trim();}

function card(r){
  const cover = r.cover
    ? `<img class="cover"
        src="./covers/${esc(r.cover)}"
        alt=""
        loading="lazy"
        decoding="async"
        fetchpriority="low"
        onerror="this.style.display='none'">`
    : `<div class="cover"></div>`;

  const physical = r.physical ? `<div class="small">${esc(r.physical)}</div>` : "";
  const subtitle = r.subtitle ? `<div class="book-subtitle">${esc(r.subtitle)}</div>` : "";
  const credit = r.credit ? `<div class="book-credit">${esc(r.credit)}</div>` : "";
  const badges = [
    r.collection ? `<span class="badge">${esc(r.collection)}</span>` : "",
    r.format ? `<span class="badge">${esc(r.format)}</span>` : "",
    r.openedition_url ? `<span class="badge badge-oa">Open access</span>` : "",
  ].filter(Boolean).join("");
  const price = r.price ? `<div class="small">Prix : ${esc(r.price)}</div>` : "";
  const avail = r.availability ? `<div class="small">${esc(r.availability)}</div>` : "";
  const excerpt = r.excerpt ? `<div class="small">${esc(r.excerpt)}</div>` : "";

  return `<div class="card">
    ${cover}
    <div class="meta">
      <a href="./livres/${esc(r.slug)}.html"><strong>${esc(r.title)}</strong></a>
      ${subtitle}
      ${credit}
      <div class="badges">${badges}</div>
      ${price}${avail}${physical}
      ${excerpt}
    </div>
  </div>`;
}

function buildOptions(values, placeholder){
  const opts = [`<option value="">${esc(placeholder)}</option>`];
  for(const v of values){ opts.push(`<option value="${esc(v)}">${esc(v)}</option>`); }
  return opts.join("");
}
function uniqueSorted(arr){
  return Array.from(new Set(arr.filter(Boolean))).sort((a,b)=>String(a).localeCompare(String(b), "fr"));
}
function filterRecs(recs, q, col, fmt, year){
  const Q = normalize(q);
  return recs.filter(r=>{
    if(col && r.collection !== col) return false;
    if(fmt && r.format !== fmt) return false;
    if(year && String(r.year) !== String(year)) return false;
    if(!Q) return true;
    const hay = [r.title,r.subtitle,r.credit,r.collection,r.format,r.id13].map(x=>normalize(x)).join(" ");
    return hay.includes(Q);
  });
}

async function main(){
  const recs = await loadCatalogue();
  const q = document.getElementById("q");
  const out = document.getElementById("out");
  const count = document.getElementById("count");
  const selCol = document.getElementById("f_collection");
  const selFmt = document.getElementById("f_format");
  const selYear = document.getElementById("f_year");
  const more = document.getElementById("more");

  const cols = uniqueSorted(recs.map(r=>r.collection));
  const fmts = uniqueSorted(recs.map(r=>r.format));
  const years = uniqueSorted(recs.map(r=>r.year)).reverse();

  selCol.innerHTML = buildOptions(cols, "Toutes les collections");
  selFmt.innerHTML = buildOptions(fmts, "Tous les formats");
  selYear.innerHTML = buildOptions(years, "Toutes les années");

  function render(){
    const filtered = filterRecs(recs, q.value, selCol.value, selFmt.value, selYear.value);
    count.textContent = String(filtered.length);

    const shown = filtered.slice(0, limit);
    out.innerHTML = shown.map(card).join("");

    if(more){
      more.style.display = (filtered.length > limit) ? "inline-block" : "none";
    }
  }

  function scheduleRender(resetLimit){
    if(resetLimit) limit = PAGE_SIZE;
    if(timer) clearTimeout(timer);
    timer = setTimeout(()=>{ timer=null; render(); }, 140);
  }

  [q, selCol, selFmt, selYear].forEach(el=>el.addEventListener("input", ()=>scheduleRender(true)));

  if(more){
    more.addEventListener("click", (e)=>{
      e.preventDefault();
      limit += PAGE_SIZE;
      render();
    });
  }

  render();
}
main();
""".replace("__CARD_PAGE_SIZE__", str(CARD_PAGE_SIZE))

# Révélation progressive des cartes déjà rendues côté Python (collections,
# revues). Sans JS, aucune carte n'est masquée et le bouton reste hidden.
PROGRESSIVE_CARDS_JS = r"""
(function(){
  var SIZE = __CARD_PAGE_SIZE__;
  var grids = document.querySelectorAll(".progressive-card-grid");
  Array.prototype.forEach.call(grids, function(grid, idx){
    if (grid.dataset.progressiveInit) return;
    grid.dataset.progressiveInit = "1";

    var cards = grid.querySelectorAll(".card");
    var actions = grid.nextElementSibling;
    if (actions && !actions.classList.contains("progressive-card-actions")) actions = null;
    var btn = actions ? actions.querySelector(".progressive-card-more") : null;

    if (cards.length <= SIZE || !btn) {
      if (actions) actions.hidden = true;
      return;
    }

    if (!grid.id) grid.id = "progressive-card-grid-" + (idx + 1);
    btn.setAttribute("aria-controls", grid.id);

    var visible = SIZE;
    function apply(){
      Array.prototype.forEach.call(cards, function(card, i){
        card.classList.toggle("card-progressive-hidden", i >= visible);
      });
      var done = visible >= cards.length;
      btn.setAttribute("aria-expanded", done ? "true" : "false");
      btn.hidden = done;
      actions.hidden = done;
    }
    btn.addEventListener("click", function(){ visible += SIZE; apply(); });
    btn.hidden = false;
    apply();
  });
})();
""".replace("__CARD_PAGE_SIZE__", str(CARD_PAGE_SIZE))

NEWS_CAROUSEL_JS = r"""
(async function(){
  const host = document.getElementById("newsbar");
  if(!host) return;

  function esc(s){
    return String(s||"")
      .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
      .replaceAll('"',"&quot;").replaceAll("'","&#039;");
  }

  let data = [];
  try{
    const res = await fetch("./actualites.json");
    data = await res.json();
  }catch(e){ return; }

  if(!Array.isArray(data) || data.length === 0) return;

  const max = 8;
  data = data.slice(0, max);

  const items = data.map((r)=>`
  <div class="news-item">
    <a class="news-link" href="./actualites.html#actu-${esc(r.id || '')}">
      ${r.image ? `<img class="news-img" src="./${esc(r.image)}" alt="" loading="lazy" decoding="async">`
                : `<div class="news-img"></div>`}
      <div class="news-meta">
        <div class="t">${esc(r.title || "")}</div>
        ${r.date ? `<div class="d">${esc(r.date)}</div>` : ``}
        ${r.excerpt ? `<div class="d">${esc(r.excerpt)}</div>` : ``}
      </div>
    </a>
  </div>
`).join("");

  host.innerHTML = `
    <div class="newsbar">
      <div class="wrap">
        <div class="newsbar-title">
          <h2>Actualités</h2>
          <a href="./actualites.html">Tout voir</a>
        </div>

        <div class="news-carousel">
          <div class="news-track" id="newsTrack">${items}</div>
          <button class="news-btn news-prev" id="newsPrev" type="button" title="Précédent" aria-label="Précédent">‹</button>
          <button class="news-btn news-next" id="newsNext" type="button" title="Suivant" aria-label="Suivant">›</button>
        </div>
      </div>
    </div>
  `;

  const track = document.getElementById("newsTrack");
  const prev = document.getElementById("newsPrev");
  const next = document.getElementById("newsNext");

  const n = track ? track.children.length : 0;
  if(!track || n === 0) return;

  let idx = 0;
  let auto = null;
  let resumeTimer = null;

  function slideWidth(){
    // largeur visible du “viewport” (une slide = 100% de ça)
    return track.getBoundingClientRect().width || 1;
  }

  function go(i, smooth=true){
    idx = (i % n + n) % n;
    track.scrollTo({ left: idx * slideWidth(), behavior: smooth ? "smooth" : "auto" });
  }

  function currentIndex(){
    const w = slideWidth();
    return Math.round(track.scrollLeft / w);
  }

  function stopAuto(){
    if(auto){ clearInterval(auto); auto = null; }
    if(resumeTimer){ clearTimeout(resumeTimer); resumeTimer = null; }
  }

  function startAuto(){
    stopAuto();
    auto = setInterval(()=>{ go(currentIndex() + 1, true); }, 5500);
  }

  function pauseThenResume(){
    stopAuto();
    // reprise douce après interaction
    resumeTimer = setTimeout(()=>{ startAuto(); }, 5000);
  }

  prev.addEventListener("click", ()=>{ pauseThenResume(); go(currentIndex() - 1, true); });
  next.addEventListener("click", ()=>{ pauseThenResume(); go(currentIndex() + 1, true); });

  // Interaction utilisateur : pause temporaire
  track.addEventListener("pointerdown", pauseThenResume, {passive:true});
  track.addEventListener("wheel",      pauseThenResume, {passive:true});
  track.addEventListener("touchstart", pauseThenResume, {passive:true});

  // Recalage au resize (sinon on “tombe entre deux”)
  window.addEventListener("resize", ()=>{
    // recale sans animation
    go(currentIndex(), false);
  });

  // Init : on se place sur la première et on lance l’auto
  go(0, false);
  startAuto();
})();
"""

LIGHTBOX_HTML = r"""
<div id="lightbox" class="lightbox" aria-hidden="true">
  <div class="lightbox-close" id="lightboxClose" title="Fermer">×</div>
  <img id="lightboxImg" alt="">
</div>

<script>
(function(){
  const lb = document.getElementById("lightbox");
  const lbImg = document.getElementById("lightboxImg");
  const lbClose = document.getElementById("lightboxClose");

  let closeTimer = null;

  function open(src){
    if(!src) return;
    if(closeTimer){ clearTimeout(closeTimer); closeTimer = null; }
    lbImg.src = src;
    lb.classList.add("open");
    document.body.style.overflow = "hidden";
  }
  function close(){
  lb.classList.remove("open");
  document.body.style.overflow = "";
  if(closeTimer) clearTimeout(closeTimer);
  closeTimer = setTimeout(()=>{
    lbImg.src = "";
    closeTimer = null;
  }, 330);
  }

  lb.addEventListener("click", (e)=>{ if(e.target === lb) close(); });
  lbClose.addEventListener("click", close);
  document.addEventListener("keydown", (e)=>{ if(e.key === "Escape") close(); });

  document.addEventListener("click", (e)=>{
    const a = e.target.closest("[data-lightbox-src]");
    if(!a) return;
    e.preventDefault();
    open(a.getAttribute("data-lightbox-src"));
  });
})();
</script>
"""


