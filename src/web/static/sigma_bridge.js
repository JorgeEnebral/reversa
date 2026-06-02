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
 * Mapa id→{id, kind, label, attrs} con los datos originales (Neo4j) de cada
 * nodo. Permite devolver a Python todos los campos al hacer click, en lugar
 * de solo los atributos Sigma (x, y, size, color).
 */
window._nodeData = {};

/**
 * Mapa edgeKey→{src, dst, type, attrs} con los datos originales de cada arista.
 * Permite devolver a Python tipo y atributos completos al hacer click en una arista.
 */
window._edgeData = {};

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

    // Grafo dirigido con multi:true para permitir aristas paralelas.
    var graph = new graphology.Graph({ multi: true, type: "directed" });

    // Limpiar datos previos al reinicializar.
    window._nodeData = {};
    window._edgeData = {};

    // --- Nodos ---
    // Posición inicial en elipse para que ForceAtlas2 converja desde una
    // distribución circular (evita el aspecto de cuadrado en zoom-out).
    var nodes = graphData.nodes || [];
    nodes.forEach(function (n) {
      // hasNode evita duplicados; pueden llegar si el mismo nodo aparece en
      // múltiples aristas dentro del _MAX_EDGES de graph_repo.
      if (!graph.hasNode(n.id)) {
        // Posición inicial uniforme dentro de un círculo (no solo en la
        // circunferencia): sqrt(rand) distribuye el radio uniformemente en área.
        var angle = Math.random() * 2 * Math.PI;
        var r = Math.sqrt(Math.random()) * 100;
        graph.addNode(n.id, {
          label: n.label || n.id,
          x: Math.cos(angle) * r,
          y: Math.sin(angle) * r,
          // UserQuery más grande para distinguirlo visualmente de las normas.
          size: n.kind === "UserQuery" ? 10 : 5,
          // Color ya resuelto por Python (theme.py).
          color: n.color || "#94a3b8",
        });
        // Guardar datos originales para devolverlos en el evento click.
        window._nodeData[n.id] = {
          id: n.id,
          kind: n.kind || "",
          label: n.label || n.id,
          attrs: n.attrs || {},
        };
      }
    });

    // --- Aristas ---
    (graphData.edges || []).forEach(function (e) {
      try {
        var edgeKey = graph.addDirectedEdge(e.src, e.dst, {
          label: e.type,
          size: 2,
          color: e.color || "#111111",
          type: "arrow",
        });
        // Guardar datos originales para devolverlos en el evento click.
        window._edgeData[edgeKey] = {
          src: e.src,
          dst: e.dst,
          type: e.type || "",
          attrs: e.attrs || {},
        };
      } catch (_) {
        // addDirectedEdge lanza si src o dst no existen en el grafo (puede
        // ocurrir si Neo4j devuelve una arista cuyo nodo fue filtrado). Se
        // ignora silenciosamente para no interrumpir el rendering.
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
      defaultEdgeType: "arrow", // aristas dirigidas con punta de flecha
      enableEdgeClickEvents: true, // necesario en Sigma v2 para que clickEdge dispare
      enableEdgeHoverEvents: false,
      enableEdgeWheelEvents: false,
      labelColor: { color: "#13283d" },
      labelFont: "Inter, sans-serif",
      // Proporciones de la punta de flecha (por defecto 2.5 y 1.5).
      arrowHeadLengthThicknessRatio: 4,
      arrowHeadWidthLengthRatio: 1,
    });

    // --- Eventos de click ---
    // Se almacenan en window._lastClick y son consumidos por el timer de
    // sigma_canvas.py cada 500 ms. El consumo es "destructivo": getLastClick()
    // resetea el valor, por lo que cada click se procesa exactamente una vez.
    window._sigmaInstance.on("clickNode", function (e) {
      var nodeId = e.node;
      var data = window._nodeData[nodeId] || {
        id: nodeId,
        kind: "",
        label: nodeId,
        attrs: {},
      };
      window._lastClick = {
        node: { id: data.id, kind: data.kind, label: data.label, attrs: data.attrs },
        edge: null,
      };
    });

    window._sigmaInstance.on("clickEdge", function (e) {
      var edgeId = e.edge;
      var data = window._edgeData[edgeId];
      var extremities = graph.extremities(edgeId);
      window._lastClick = {
        node: null,
        edge: {
          id: edgeId,
          src: data ? data.src : extremities[0],
          dst: data ? data.dst : extremities[1],
          type: data ? data.type : "",
          attrs: data ? data.attrs : {},
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
  window._nodeData = {};
  window._edgeData = {};
  window._lastClick = { node: null, edge: null };
};
