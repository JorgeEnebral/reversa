// sigma_bridge.js — puente Sigma.js / graphology para NiceGUI
// Siguiendo vision-v3.md §3.4 (~50 líneas de lógica real)

window._sigmaInstance = null;
window._lastClick = { node: null, edge: null };

window.initSigma = function (graphData) {
  const container = document.getElementById("sigma-canvas");
  if (!container || typeof Sigma === "undefined") return;

  const graph = new graphology.Graph({ multi: true });

  (graphData.nodes || []).forEach((n) => {
    if (!graph.hasNode(n.id)) {
      graph.addNode(n.id, {
        label: n.label || n.id,
        x: Math.random() * 200 - 100,
        y: Math.random() * 200 - 100,
        size: 4,
        color: n.attrs && n.attrs.vigente === false ? "#e74c3c" : "#3498db",
        ...n.attrs,
      });
    }
  });

  (graphData.edges || []).forEach((e) => {
    try {
      graph.addEdge(e.src, e.dst, {
        label: e.type,
        size: 1,
        color: "#aaa",
        ...e.attrs,
      });
    } catch (_) {}
  });

  if (window._sigmaInstance) window._sigmaInstance.kill();

  window._sigmaInstance = new Sigma(graph, container, {
    renderEdgeLabels: false,
    defaultNodeColor: "#3498db",
    defaultEdgeColor: "#aaa",
  });

  window._sigmaInstance.on("clickNode", ({ node }) => {
    window._lastClick = {
      node: { id: node, attrs: graph.getNodeAttributes(node) },
      edge: null,
    };
  });

  window._sigmaInstance.on("clickEdge", ({ edge }) => {
    const attrs = graph.getEdgeAttributes(edge);
    const [src, dst] = graph.extremities(edge);
    window._lastClick = {
      node: null,
      edge: { id: edge, src, dst, attrs },
    };
  });
};

window.getLastClick = function () {
  const click = window._lastClick;
  window._lastClick = { node: null, edge: null }; // consume
  return click;
};

window.clearGraph = function () {
  if (window._sigmaInstance) {
    window._sigmaInstance.kill();
    window._sigmaInstance = null;
  }
  window._lastClick = { node: null, edge: null };
};
