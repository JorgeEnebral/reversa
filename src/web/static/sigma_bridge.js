/**
 * sigma_bridge.js — puente entre Python/NiceGUI y Sigma.js
 *
 * Este fichero es la única pieza JS del proyecto y actúa como adaptador
 * entre los datos que llegan de Python (vía window.initSigma) y el renderer
 * Sigma.js. No contiene lógica de negocio: los colores, el scope y los
 * filtros se calculan en Python y llegan ya resueltos en el payload.
 *
 * Dependencias (cargadas en graph.py antes de este fichero, como globales):
 *   - graphology.umd.min.js   → global `graphology`
 *   - graphology-library.min.js → global `graphologyLibrary`
 *   - sigma.min.js             → global `Sigma`
 *
 * Protocolo con Python:
 *   Python → JS : window.initSigma(graphData)  [via ui.run_javascript]
 *   JS → Python : window.getLastClick()         [sondeado por sigma_canvas.py]
 */

window._sigmaInstance = null;

/**
 * Almacena el último evento de click del grafo.
 * Se resetea a null tras cada lectura para que _poll_clicks de Python lo
 * consuma exactamente una vez por evento.
 */
window._lastClick = { node: null, edge: null };

/**
 * Inicializa (o reinicializa) el grafo Sigma con los datos proporcionados.
 *
 * Si las librerías aún no han cargado (el script es `defer` pero los vendors
 * son síncronos; puede haber una carrera en conexiones lentas), reintenta
 * tras 100 ms en lugar de fallar silenciosamente.
 *
 * @param {Object} graphData - Payload de Python: { nodes: [...], edges: [...] }
 *   Cada nodo: { id, label, color, kind, attrs }
 *   Cada arista: { src, dst, type, color, attrs }
 * @returns {string} "ok:N nodos / M aristas" o "error:mensaje"
 */
window.initSigma = function (graphData) {
  try {
    // Guardia de carga: los vendors se cargan de forma síncrona, pero si el
    // navegador los sirve en caché puede haber un race con el defer de este script.
    if (
      typeof Sigma === "undefined" ||
      typeof graphology === "undefined" ||
      typeof graphologyLibrary === "undefined"
    ) {
      return setTimeout(function () {
        window.initSigma(graphData);
      }, 100);
    }

    // El UMD de Sigma v2 expone el constructor en Sigma.Sigma, no en Sigma
    // directamente (Sigma es el namespace del módulo, no la clase).
    var SigmaCtor = Sigma.Sigma || Sigma.default || Sigma;

    var container = document.getElementById("sigma-canvas");
    if (!container) return "error:no-container";

    // graphology.Graph con multi:true permite aristas paralelas (una norma puede
    // citar a otra varias veces con distintos textos) sin lanzar errores.
    var graph = new graphology.Graph({ multi: true });

    // --- Nodos ---
    (graphData.nodes || []).forEach(function (n) {
      // hasNode evita duplicados; pueden llegar si el mismo nodo aparece en
      // múltiples aristas dentro del _MAX_EDGES de graph_repo.
      if (!graph.hasNode(n.id)) {
        graph.addNode(n.id, {
          label: n.label || n.id,
          // Posición inicial aleatoria; ForceAtlas2 la reemplazará inmediatamente.
          x: Math.random() * 200 - 100,
          y: Math.random() * 200 - 100,
          // UserQuery más grande para distinguirlo visualmente de las normas.
          size: n.kind === "UserQuery" ? 10 : 5,
          // Color ya resuelto por Python (theme.py); el JS no hardcodea colores.
          color: n.color || "#94a3b8",
        });
      }
    });

    // --- Aristas ---
    (graphData.edges || []).forEach(function (e) {
      try {
        graph.addEdge(e.src, e.dst, {
          label: e.type,
          size: 1,
          color: e.color || "#111111",
        });
      } catch (_) {
        // addEdge lanza si src o dst no existen en el grafo (puede ocurrir si
        // Neo4j devuelve una arista cuyo nodo fue filtrado en otra parte de la
        // query). Se ignora silenciosamente para no interrumpir el rendering.
      }
    });

    // --- Layout ForceAtlas2 ---
    // Se ejecuta de forma síncrona en el hilo principal antes de instanciar
    // Sigma, de modo que el primer render ya muestra el layout final (sin
    // animación de convergencia). El nº de iteraciones escala inversamente
    // al tamaño del grafo: grafos pequeños convergen antes.
    if (graph.order > 0 && graphologyLibrary.layoutForceAtlas2) {
      var iters = Math.max(10, Math.min(100, Math.floor(3000 / graph.order)));
      graphologyLibrary.layoutForceAtlas2.assign(graph, {
        iterations: iters,
        settings: {
          gravity: 1,
          scalingRatio: 2, // separa más los clusters; reduce hairball effect
        },
      });
    }

    // Destruye la instancia anterior antes de crear una nueva para liberar los
    // recursos WebGL del contexto anterior (cada contexto consume VRAM).
    if (window._sigmaInstance) window._sigmaInstance.kill();

    window._sigmaInstance = new SigmaCtor(graph, container, {
      renderEdgeLabels: false, // con miles de aristas las etiquetas son ilegibles
      defaultNodeColor: "#94a3b8",
      defaultEdgeColor: "#111111",
      labelColor: { color: "#13283d" },
      labelFont: "Inter, sans-serif",
    });

    // --- Eventos de click ---
    // Se almacenan en window._lastClick y son consumidos por el timer de
    // sigma_canvas.py cada 500 ms. El consumo es "destructivo": getLastClick()
    // resetea el valor, por lo que cada click se procesa exactamente una vez.
    window._sigmaInstance.on("clickNode", function (e) {
      var node = e.node;
      window._lastClick = {
        node: { id: node, attrs: graph.getNodeAttributes(node) },
        edge: null,
      };
    });

    window._sigmaInstance.on("clickEdge", function (e) {
      var edge = e.edge;
      var extremities = graph.extremities(edge);
      window._lastClick = {
        node: null,
        edge: {
          id: edge,
          src: extremities[0],
          dst: extremities[1],
          attrs: graph.getEdgeAttributes(edge),
        },
      };
    });

    return "ok:" + graph.order + " nodos / " + graph.size + " aristas";
  } catch (err) {
    // No relanzar: si esto explota, NiceGUI nunca recibiría respuesta del
    // run_javascript y expiraría el timeout de 10 s. Volcamos en consola.
    console.error("initSigma error:", err);
    return "error:" + (err && err.message ? err.message : String(err));
  }
};

/**
 * Devuelve y consume el último evento de click registrado.
 * Llamado por el timer de sigma_canvas.py cada 500 ms.
 *
 * @returns {{ node: Object|null, edge: Object|null }}
 */
window.getLastClick = function () {
  var click = window._lastClick;
  // Resetear tras leer para que el siguiente sondeo no reprocese el mismo evento.
  window._lastClick = { node: null, edge: null };
  return click;
};

/**
 * Destruye la instancia Sigma y limpia el estado global.
 * Útil si la página se recarga o el grafo se desmonta.
 */
window.clearGraph = function () {
  if (window._sigmaInstance) {
    window._sigmaInstance.kill();
    window._sigmaInstance = null;
  }
  window._lastClick = { node: null, edge: null };
};
