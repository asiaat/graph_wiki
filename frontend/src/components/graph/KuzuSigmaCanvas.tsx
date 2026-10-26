import React from "react";
import Sigma from "sigma";
import Graphology from "graphology";

interface KuzuSigmaCanvasProps {
  entities: any[];
  edges: any[];
}

export default function KuzuSigmaCanvas({ entities, edges }: KuzuSigmaCanvasProps) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const sigmaRef = React.useRef<Sigma | null>(null);
  const graphRef = React.useRef<Graphology | null>(null);

  React.useEffect(() => {
    if (!containerRef.current) return;

    const graph = new Graphology();
    graphRef.current = graph;

    entities.forEach((entity) => {
      graph.addNode(entity.id, {
        label: entity.canonical_name,
        category: entity.category,
        size: 10,
      });
    });

    edges.forEach((edge) => {
      graph.addEdge(edge.source, edge.target, {
        label: edge.relation_type,
        weight: edge.weight || 1,
      });
    });

    const sigma = new Sigma(graph, containerRef.current, {
      nodeReducer: (node, data) => {
        const res = { ...data };
        res.color = categoryColor(data.category);
        res.size = Math.max(5, (data.size || 5) * 2);
        return res;
      },
      edgeReducer: (edge, data) => {
        const res = { ...data };
        res.size = Math.max(1, (data.weight || 1) * 2);
        return res;
      },
    });

    sigmaRef.current = sigma;

    return () => {
      sigma.kill();
    };
  }, [entities, edges]);

  function categoryColor(cat: string) {
    switch (cat) {
      case "Person": return "#3b82f6";
      case "Organization": return "#8b5cf6";
      case "Location": return "#10b981";
      case "MilitarySystem": return "#f59e0b";
      case "Component": return "#ef4444";
      case "NarrativeFrame": return "#ec4899";
      default: return "#6b7280";
    }
  }

  return <div ref={containerRef} className="w-full h-full" />;
}