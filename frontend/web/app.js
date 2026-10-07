/* FichaClara · interfaz. Habla con la API FastAPI (POST /query, /ingest, GET /documents, DELETE /documents/{id}). */
(() => {
  "use strict";

  // ------------------------------------------------------------------ Configuración
  const params = new URLSearchParams(location.search);
  const MOCK = params.get("mock") === "1" || window.FICHACLARA_MOCK === true;
  const API = (params.get("api") || window.FICHACLARA_API || "http://localhost:8000").replace(/\/$/, "");
  const MAX_BYTES = 25 * 1024 * 1024;
  const EXT_OK = /\.(pdf|txt|md)$/i;
  const SIN_ANIMACION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const SUGERENCIAS = [
    "¿Cuál es la semivida de la melatonina del Circadin?",
    "¿Cuál es la dosis de paracetamol en adultos?",
    "¿Qué contraindicaciones tiene el ibuprofeno?",
    "¿Qué dosis de Januvia se usa en insuficiencia renal?",
  ];
  const FRASES_BUSCANDO = [
    "Buscando en las fichas…", "Leyendo la fuente…", "Subrayando lo importante…", "Comprobando las citas…",
  ];
  const FRASES_SUBIENDO = [
    "Leyendo tu documento…", "Troceando en fragmentos…", "Colocándolo en la estantería…",
  ];

  // ------------------------------------------------------------------ Utilidades
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, texto) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (texto != null) n.textContent = texto;
    return n;
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
  const urlSegura = (u) => { try { const x = new URL(u); return /^https?:$/.test(x.protocol) ? x.href : null; } catch { return null; } };

  // ------------------------------------------------------------------ API
  async function http(ruta, opciones = {}, ms = 60000) {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), ms);
    let resp;
    try {
      resp = await fetch(API + ruta, { ...opciones, signal: ctl.signal });
    } catch (e) {
      const err = new Error(e.name === "AbortError" ? "La API tarda demasiado en responder." : "No consigo conectar con la API en " + API + ".");
      err.red = true;
      throw err;
    } finally {
      clearTimeout(t);
    }
    let cuerpo = null;
    try { cuerpo = await resp.json(); } catch { /* sin cuerpo JSON */ }
    if (!resp.ok) {
      let detalle = cuerpo && cuerpo.detail;
      if (Array.isArray(detalle)) detalle = "La petición no es válida (revisa que la pregunta tenga entre 3 y 1000 caracteres).";
      const err = new Error(detalle || "La API respondió con el error " + resp.status + ".");
      err.status = resp.status;
      throw err;
    }
    return cuerpo;
  }

  const api = MOCK ? window.FichaClaraMock : {
    health: () => http("/health", {}, 5000),
    query: (pregunta) => http("/query", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ pregunta }) }, 90000),
    listDocuments: () => http("/documents", {}, 15000),
    ingest: (file) => { const fd = new FormData(); fd.append("file", file); return http("/ingest", { method: "POST", body: fd }, 300000); },
    deleteDocument: (id) => http("/documents/" + encodeURIComponent(id), { method: "DELETE" }, 15000),
  };

  // ------------------------------------------------------------------ Estado
  let docs = [];
  let ocupado = false;
  let ultimoNuevo = null;
  let docsFallo = false;
  let docsFallaron = false;

  const refs = {
    mensajes: $("mensajes"), bienvenida: $("bienvenida"), form: $("form"), pregunta: $("pregunta"),
    enviar: $("enviar"), contador: $("contador"), sugerencias: $("sugerencias"), estado: $("estado"),
    lista: $("lista-docs"), resumen: $("resumen"), buscar: $("buscar-doc"), zona: $("zona-subida"),
    input: $("input-archivo"), zsTitulo: $("zs-titulo"), zsSub: $("zs-sub"), tostadas: $("tostadas"),
    lateral: $("lateral"), velo: $("velo"), menu: $("btn-menu"), cerrar: $("btn-cerrar"),
  };

  // ------------------------------------------------------------------ Tostadas y confeti
  function tostada(texto, tipo = "") {
    const t = el("div", "tostada " + tipo, texto);
    refs.tostadas.appendChild(t);
    setTimeout(() => { t.classList.add("sale"); setTimeout(() => t.remove(), 300); }, 3800);
  }
  function confeti(desde) {
    if (SIN_ANIMACION) return;
    const r = desde.getBoundingClientRect();
    const x0 = r.left + r.width / 2, y0 = r.top + r.height / 2;
    const emojis = ["💊", "✨", "🩵", "⭐", "💊", "🧡"];
    for (let i = 0; i < 16; i++) {
      const c = el("span", "confeti", emojis[i % emojis.length]);
      const ang = (Math.PI * 2 * i) / 16 + Math.random() * 0.4;
      const dist = 70 + Math.random() * 90;
      c.style.left = x0 + "px"; c.style.top = y0 + "px";
      c.style.setProperty("--dx", Math.cos(ang) * dist + "px");
      c.style.setProperty("--dy", Math.sin(ang) * dist - 30 + "px");
      c.style.setProperty("--rot", (Math.random() * 360 - 180) + "deg");
      document.body.appendChild(c);
      setTimeout(() => c.remove(), 1250);
    }
  }

  // ------------------------------------------------------------------ Estado de la API
  async function comprobarApi() {
    const caja = refs.estado, txt = caja.querySelector("b");
    if (MOCK) { caja.className = "estado mock"; txt.textContent = "Modo demo"; return; }
    try {
      await api.health();
      caja.className = "estado ok"; txt.textContent = "API conectada";
      if (docsFallo) cargarDocs(); // la API ha vuelto: reintenta la lista que había fallado
      if (docsFallaron) cargarDocs(); // la API acaba de volver: reintenta la lista de documentos
    } catch {
      caja.className = "estado caido"; txt.textContent = "Sin conexión con la API";
    }
  }

  // ------------------------------------------------------------------ Texto de la respuesta (seguro: se escapa antes de poner HTML)
  function textoAHtml(texto, indicesValidos) {
    const inline = (s) => esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\[(\d+)\]/g, (m, n) => (indicesValidos.has(Number(n)) ? `<button type="button" class="cita" data-n="${n}" aria-label="Ver fuente ${n}">${n}</button>` : ""));
    return texto.trim().split(/\n{2,}/).map((bloque) => {
      const lineas = bloque.split("\n");
      if (lineas.every((l) => /^\s*([-*]|\d+\.)\s+/.test(l))) {
        return "<ul>" + lineas.map((l) => "<li>" + inline(l.replace(/^\s*([-*]|\d+\.)\s+/, "")) + "</li>").join("") + "</ul>";
      }
      return "<p>" + lineas.map(inline).join("<br>") + "</p>";
    }).join("");
  }

  async function escribirPoco(destino, texto, indicesValidos, alCambiar) {
    if (SIN_ANIMACION) { destino.innerHTML = textoAHtml(texto, indicesValidos); return; }
    const trozos = texto.split(/(\s+)/);
    const palabras = trozos.length / 2;
    const paso = Math.max(8, Math.min(32, 2600 / palabras));
    for (let i = 1; i <= trozos.length; i += 2) {
      destino.innerHTML = textoAHtml(trozos.slice(0, i).join(""), indicesValidos);
      alCambiar();
      await esperar(paso);
    }
    destino.innerHTML = textoAHtml(texto, indicesValidos);
  }

  // ------------------------------------------------------------------ Mensajes
  const bajar = () => { refs.mensajes.scrollTop = refs.mensajes.scrollHeight; };
  const avatar = () => {
    const a = el("div", "avatar");
    a.innerHTML = '<svg aria-hidden="true"><use href="#mascota"/></svg>';
    return a;
  };

  function mensajeUsuario(texto) {
    const m = el("div", "msg yo");
    const col = el("div", "burbuja-col");
    col.appendChild(el("div", "burbuja", texto));
    m.appendChild(col);
    refs.mensajes.appendChild(m);
    bajar();
  }

  function indicadorEscribiendo() {
    const m = el("div", "msg ia escribiendo");
    m.appendChild(avatar());
    const col = el("div", "burbuja-col");
    const b = el("div", "burbuja");
    b.innerHTML = '<span class="puntos"><i></i><i></i><i></i></span>';
    const txt = el("span", "estado-txt", FRASES_BUSCANDO[0]);
    b.appendChild(txt);
    col.appendChild(b);
    m.appendChild(col);
    refs.mensajes.appendChild(m);
    bajar();
    let i = 0;
    const timer = setInterval(() => { i = (i + 1) % FRASES_BUSCANDO.length; txt.textContent = FRASES_BUSCANDO[i]; }, 1300);
    return () => { clearInterval(timer); m.remove(); };
  }

  function tarjetaFuente(f, retardo) {
    const card = el("article", "fuente");
    card.dataset.n = f.indice;
    card.style.animationDelay = retardo + "ms";

    const cab = el("button");
    cab.type = "button";
    cab.setAttribute("aria-expanded", "false");
    const num = el("span", "num", String(f.indice));
    const tit = el("span", "tit");
    tit.appendChild(el("b", null, f.nombre));
    const partes = [];
    if (f.seccion) partes.push("Sección " + f.seccion + (f.titulo_seccion ? " · " + f.titulo_seccion : ""));
    partes.push("pág. " + f.pagina);
    tit.appendChild(el("small", null, partes.join(" · ")));
    cab.append(num, tit, el("span", "flecha", "▾"));

    const detalle = el("div", "detalle");
    const caja = el("div");
    const interior = el("div", "interior");
    interior.appendChild(el("blockquote", "fragmento", f.fragmento));
    const meta = el("div", "meta-fuente");
    const pct = Math.max(0, Math.min(1, Number(f.score) || 0));
    const rel = el("span", "relev");
    rel.append("Relevancia ");
    const barra = el("span", "barra-rel");
    const relleno = el("i");
    relleno.style.width = Math.round(pct * 100) + "%";
    barra.appendChild(relleno);
    rel.append(barra, Math.round(pct * 100) + " %");
    meta.appendChild(rel);
    if (f.fecha_revision) meta.appendChild(el("span", null, "· Revisado: " + f.fecha_revision));
    const href = f.url && urlSegura(f.url);
    if (href) {
      const a = el("a", "enlace-fuente", "Abrir fuente ↗");
      a.href = href; a.target = "_blank"; a.rel = "noopener noreferrer";
      meta.appendChild(a);
    }
    interior.appendChild(meta);
    caja.appendChild(interior);
    detalle.appendChild(caja);
    card.append(cab, detalle);

    cab.addEventListener("click", () => {
      const abierta = card.classList.toggle("abierta");
      cab.setAttribute("aria-expanded", String(abierta));
    });
    return card;
  }

  function abrirFuente(contenedor, n) {
    const card = contenedor.querySelector('.fuente[data-n="' + n + '"]');
    if (!card) return;
    card.classList.add("abierta");
    card.querySelector("button").setAttribute("aria-expanded", "true");
    card.classList.remove("resalta"); void card.offsetWidth; card.classList.add("resalta");
    card.scrollIntoView({ behavior: SIN_ANIMACION ? "auto" : "smooth", block: "nearest" });
    setTimeout(() => card.classList.remove("resalta"), 1800);
  }

  async function mensajeRespuesta(r) {
    const m = el("div", "msg ia");
    m.appendChild(avatar());
    const col = el("div", "burbuja-col");
    m.appendChild(col);
    refs.mensajes.appendChild(m);

    if (r.aviso_pii) {
      const aviso = el("div", "aviso-pii");
      aviso.innerHTML = '<span aria-hidden="true">🔒</span><div><b>He tapado datos personales</b> de tu pregunta antes de buscar. Mejor no escribas datos de pacientes.</div>';
      col.appendChild(aviso);
    }

    // La API puede devolver encontrado=true y que el modelo conteste "No consta…" (hay fragmentos, pero no responden).
    const noConsta = !r.encontrado || /^\s*No consta en las fichas técnicas consultadas\.?\s*$/i.test(r.respuesta || "");
    const burbuja = el("div", "burbuja" + (noConsta ? " no-consta" : ""));
    col.appendChild(burbuja);
    const validos = new Set((r.fuentes || []).map((f) => f.indice));

    if (noConsta) {
      burbuja.innerHTML = '<p>🤔 <strong>No lo encuentro en las fichas.</strong></p>' + textoAHtml(r.respuesta || "", validos);
    } else {
      await escribirPoco(burbuja, r.respuesta, validos, bajar);
    }

    burbuja.addEventListener("click", (e) => {
      const c = e.target.closest(".cita");
      if (c) abrirFuente(col, c.dataset.n);
    });

    if (r.fuentes && r.fuentes.length) {
      col.appendChild(el("div", "fuentes-tit", (noConsta ? "📚 Fragmentos consultados (" : "📚 Fuentes (") + r.fuentes.length + ")"));
      const lista = el("div", "fuentes");
      r.fuentes.forEach((f, i) => lista.appendChild(tarjetaFuente(f, i * 90)));
      col.appendChild(lista);
    }
    if (r.modelo) col.appendChild(el("div", "modelo", "Respondido con " + r.modelo));
    bajar();
  }

  function mensajeError(texto) {
    const m = el("div", "msg ia");
    m.appendChild(avatar());
    const col = el("div", "burbuja-col");
    const b = el("div", "burbuja error");
    b.innerHTML = "<p>😿 <strong>Ups, algo ha fallado.</strong></p><p></p>";
    b.lastChild.textContent = texto;
    col.appendChild(b);
    m.appendChild(col);
    refs.mensajes.appendChild(m);
    bajar();
  }

  // ------------------------------------------------------------------ Preguntar
  function fijarOcupado(v) {
    ocupado = v;
    refs.enviar.disabled = v;
    refs.pregunta.disabled = v;
    if (!v) refs.pregunta.focus();
  }

  async function preguntar(texto) {
    texto = texto.trim();
    if (ocupado) return;
    if (texto.length < 3) {
      refs.pregunta.classList.remove("sacude"); void refs.pregunta.offsetWidth; refs.pregunta.classList.add("sacude");
      tostada("Escribe al menos 3 caracteres 🙂");
      return;
    }
    fijarOcupado(true);
    refs.bienvenida.classList.add("oculta");
    mensajeUsuario(texto);
    refs.pregunta.value = ""; autoAjustar();
    const quitar = indicadorEscribiendo();
    try {
      const r = await api.query(texto);
      quitar();
      await mensajeRespuesta(r);
    } catch (e) {
      quitar();
      mensajeError(e.message);
      if (e.red) comprobarApi();
    } finally {
      fijarOcupado(false);
    }
  }

  function autoAjustar() {
    const t = refs.pregunta;
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 140) + "px";
    const n = t.value.length;
    refs.contador.hidden = n < 800;
    refs.contador.textContent = n + "/1000";
  }

  refs.form.addEventListener("submit", (e) => { e.preventDefault(); preguntar(refs.pregunta.value); });
  refs.pregunta.addEventListener("input", autoAjustar);
  refs.pregunta.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); refs.form.requestSubmit(); }
  });
  SUGERENCIAS.forEach((s, i) => {
    const b = el("button", "sug", s);
    b.type = "button";
    b.style.animationDelay = 200 + i * 90 + "ms";
    b.addEventListener("click", () => preguntar(s));
    refs.sugerencias.appendChild(b);
  });

  // ------------------------------------------------------------------ Documentos
  function pintarDocs() {
    const total = docs.reduce((a, d) => a + d.chunks, 0);
    refs.resumen.hidden = docs.length === 0;
    refs.resumen.innerHTML = `<span><b>${docs.length}</b>documentos</span><span><b>${total.toLocaleString("es-ES")}</b>fragmentos</span>`;

    const q = refs.buscar.value.trim().toLowerCase();
    const visibles = docs.filter((d) => !q || d.nombre.toLowerCase().includes(q) || d.doc_id.toLowerCase().includes(q));
    refs.lista.replaceChildren();

    if (!visibles.length) {
      const v = el("li", "vacio");
      v.innerHTML = docs.length ? '<span class="emoji">🔎</span>Ningún documento coincide.' : '<span class="emoji">📭</span>Aún no hay documentos.<br>Sube el primero 👆';
      refs.lista.appendChild(v);
      return;
    }
    visibles.forEach((d, i) => {
      const li = el("li", "doc " + (d.tipo_documento === "ficha_tecnica" ? "ficha" : "") + (d.doc_id === ultimoNuevo ? " nuevo" : ""));
      li.style.animationDelay = Math.min(i, 12) * 30 + "ms";
      const ico = el("span", "doc-ico", d.tipo_documento === "ficha_tecnica" ? "💊" : "📄");
      const info = el("div", "doc-info");
      info.appendChild(el("b", null, d.nombre));
      info.appendChild(el("small", null, d.chunks + " fragmentos · " + (d.tipo_documento === "ficha_tecnica" ? "ficha técnica" : "documento")));
      const del = el("button", "doc-borrar", "🗑");
      del.type = "button";
      del.setAttribute("aria-label", "Borrar " + d.nombre);
      let armado = null;
      del.addEventListener("click", async () => {
        if (!armado) {
          del.classList.add("confirmar"); del.textContent = "¿Seguro?";
          armado = setTimeout(() => { del.classList.remove("confirmar"); del.textContent = "🗑"; armado = null; }, 3000);
          return;
        }
        clearTimeout(armado);
        del.disabled = true;
        try {
          const r = await api.deleteDocument(d.doc_id);
          li.classList.add("borrando");
          await esperar(280);
          tostada("Borrado: " + r.chunks_eliminados + " fragmentos eliminados 🧹", "ok");
          await cargarDocs();
        } catch (e) {
          del.disabled = false; del.classList.remove("confirmar"); del.textContent = "🗑"; armado = null;
          tostada(e.message, "mal");
        }
      });
      li.append(ico, info, del);
      refs.lista.appendChild(li);
    });
  }
  refs.buscar.addEventListener("input", pintarDocs);

  async function cargarDocs() {
    try {
      docs = (await api.listDocuments()) || [];
      docsFallo = false;
      docsFallaron = false;
      docs.sort((a, b) => a.nombre.localeCompare(b.nombre, "es"));
      pintarDocs();
    } catch (e) {
      docsFallaron = true;
      refs.resumen.hidden = true;
      refs.lista.replaceChildren();
      const v = el("li", "vacio");
      v.innerHTML = '<span class="emoji">🔌</span>No puedo cargar los documentos.<br>';
      const b = el("button", "sug", "Reintentar");
      b.type = "button";
      b.addEventListener("click", cargarDocs);
      v.appendChild(b);
      refs.lista.appendChild(v);
    }
  }

  // ------------------------------------------------------------------ Subida
  async function subir(file) {
    if (!file) return;
    if (!EXT_OK.test(file.name)) { tostada("Solo se admiten PDF, TXT o MD 📄", "mal"); return; }
    if (file.size > MAX_BYTES) { tostada("El archivo supera los 25 MB", "mal"); return; }
    if (file.size === 0) { tostada("El archivo está vacío", "mal"); return; }

    refs.zona.classList.add("subiendo");
    refs.zsTitulo.textContent = FRASES_SUBIENDO[0];
    refs.zsSub.textContent = file.name;
    let i = 0;
    const timer = setInterval(() => { i = (i + 1) % FRASES_SUBIENDO.length; refs.zsTitulo.textContent = FRASES_SUBIENDO[i]; }, 1400);
    try {
      const r = await api.ingest(file);
      ultimoNuevo = r.doc_id;
      tostada((r.ya_existia ? "Actualizado: " : "¡Listo! ") + r.nombre + " · " + r.paginas + " pág. · " + r.chunks + " fragmentos ✨", "ok");
      confeti(refs.zona);
      await cargarDocs();
    } catch (e) {
      tostada(e.message, "mal");
    } finally {
      clearInterval(timer);
      refs.zona.classList.remove("subiendo");
      refs.zsTitulo.textContent = "Suelta aquí un documento";
      refs.zsSub.textContent = "PDF, TXT o MD · máx. 25 MB";
      refs.input.value = "";
    }
  }
  refs.input.addEventListener("change", () => subir(refs.input.files[0]));
  ["dragenter", "dragover"].forEach((ev) => refs.zona.addEventListener(ev, (e) => { e.preventDefault(); refs.zona.classList.add("arrastrando"); }));
  ["dragleave", "drop"].forEach((ev) => refs.zona.addEventListener(ev, (e) => { e.preventDefault(); refs.zona.classList.remove("arrastrando"); }));
  refs.zona.addEventListener("drop", (e) => subir(e.dataTransfer.files[0]));

  // ------------------------------------------------------------------ Menú lateral (móvil)
  function lateral(abrir) {
    refs.lateral.classList.toggle("abierto", abrir);
    refs.velo.classList.toggle("visible", abrir);
    refs.menu.setAttribute("aria-expanded", String(abrir));
  }
  refs.menu.addEventListener("click", () => lateral(true));
  refs.cerrar.addEventListener("click", () => lateral(false));
  refs.velo.addEventListener("click", () => lateral(false));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") lateral(false); });

  // ------------------------------------------------------------------ Arranque
  comprobarApi();
  setInterval(comprobarApi, 15000);
  cargarDocs();
  refs.pregunta.focus();
})();
