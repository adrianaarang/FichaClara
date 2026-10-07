/* Modo demo: respuestas falsas con el mismo contrato que la API (src/common/schemas.py).
   Se activa con ?mock=1 en la URL. Sirve para ver y probar la interfaz sin backend. */
(function () {
  const espera = (ms) => new Promise((r) => setTimeout(r, ms));

  let docs = [
    { doc_id: "FT_83208", nombre: "ANTIDOL INFANTIL 32 mg/ml", tipo_documento: "ficha_tecnica", chunks: 40 },
    { doc_id: "FT_74559", nombre: "IBUPROFENO NORMON 600 mg", tipo_documento: "ficha_tecnica", chunks: 52 },
    { doc_id: "FT_07392003", nombre: "CIRCADIN 2 mg", tipo_documento: "ficha_tecnica", chunks: 61 },
    { doc_id: "guia-insulina-5c91efb9", nombre: "guia_insulina.md", tipo_documento: "documento", chunks: 3 },
  ];

  const fuente = (indice, doc_id, nombre, seccion, titulo, pagina, fragmento, score, fecha) => ({
    indice, doc_id, nombre, seccion, titulo_seccion: titulo, pagina, fragmento, score,
    url: doc_id.startsWith("FT_") ? "https://cima.aemps.es/cima/dochtml/ft/" + doc_id.slice(3) + "/FT_" + doc_id.slice(3) + ".html" : null,
    fecha_revision: fecha,
  });

  const casos = [
    {
      claves: /circadin|melatonina/i,
      respuesta: "La semivida de eliminación de la melatonina con **Circadin** es de unas **3,5 a 4 horas** [1]. La absorción es completa en adultos y puede verse reducida hasta un 50 % en personas de edad avanzada [2].",
      fuentes: [
        fuente(1, "FT_07392003", "CIRCADIN 2 mg", "5.2", "Propiedades farmacocinéticas", 6, "Eliminación: la semivida de eliminación (t½) de Circadin es de 3,5 a 4 horas. La excreción urinaria del metabolito 6-sulfatoximelatonina es la principal vía.", 0.91, "Julio 2024"),
        fuente(2, "FT_07392003", "CIRCADIN 2 mg", "5.2", "Propiedades farmacocinéticas", 5, "Absorción: la absorción de melatonina administrada por vía oral es completa en adultos y puede reducirse hasta en un 50 % en las personas de edad avanzada.", 0.84, "Julio 2024"),
      ],
    },
    {
      claves: /paracetamol|antidol/i,
      respuesta: "En adultos, la dosis habitual de paracetamol es de **1 g cada 8 horas** según necesidad [1]. No se debe superar la dosis máxima diaria indicada en la ficha [1].",
      fuentes: [
        fuente(1, "FT_83208", "Paracetamol 1 g", "4.2", "Posología y forma de administración", 3, "La dosis habitual en adultos es de 1 g cada 8 horas según necesidad. No exceder de 3 g al día salvo indicación médica.", 0.93, "Marzo 2023"),
      ],
    },
    {
      claves: /ibuprofeno/i,
      respuesta: "Entre las contraindicaciones del **ibuprofeno** figuran la hipersensibilidad a AINE, la úlcera péptica activa y la insuficiencia cardíaca grave [1].",
      fuentes: [
        fuente(1, "FT_74559", "IBUPROFENO NORMON 600 mg", "4.3", "Contraindicaciones", 4, "Hipersensibilidad al principio activo o a otros AINE. Antecedentes de hemorragia o perforación gastrointestinal relacionados con el uso de AINE. Insuficiencia cardíaca grave.", 0.88, "Enero 2024"),
      ],
    },
  ];

  window.FichaClaraMock = {
    async health() { await espera(250); return { status: "healthy" }; },

    async query(pregunta) {
      await espera(1500 + Math.random() * 900);
      const pii = /\b\d{8}[A-Z]\b/i.test(pregunta);
      const caso = casos.find((c) => c.claves.test(pregunta));
      if (!caso) {
        return {
          respuesta: "No consta en la documentación disponible. Prueba a nombrar el medicamento en tu pregunta.",
          encontrado: false, fuentes: [], aviso_pii: pii, modelo: null,
        };
      }
      return { respuesta: caso.respuesta, encontrado: true, fuentes: caso.fuentes, aviso_pii: pii, modelo: "demo/mock" };
    },

    async listDocuments() { await espera(200); return docs.map((d) => ({ ...d })); },

    async ingest(file) {
      await espera(1800);
      const base = file.name.replace(/\.[^.]+$/, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
      const doc_id = base + "-" + Math.random().toString(16).slice(2, 10);
      const ya = docs.some((d) => d.nombre === file.name);
      docs = docs.filter((d) => d.nombre !== file.name);
      const chunks = 3 + Math.floor(Math.random() * 12);
      docs.push({ doc_id, nombre: file.name, tipo_documento: "documento", chunks });
      return { doc_id, nombre: file.name, tipo_documento: "documento", paginas: 2, chunks, ya_existia: ya };
    },

    async deleteDocument(id) {
      await espera(300);
      const d = docs.find((x) => x.doc_id === id);
      if (!d) { const e = new Error("No hay ningún documento indexado con id " + id); e.status = 404; throw e; }
      docs = docs.filter((x) => x.doc_id !== id);
      return { status: "deleted", document_id: id, chunks_eliminados: d.chunks };
    },
  };
})();
