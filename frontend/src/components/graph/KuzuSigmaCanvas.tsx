import React from "react";
import Sigma from "sigma";
import Graphology from "graphology";
import type { GraphEdge, SubgraphEntity } from "../../types/jevGraph";

interface KuzuSigmaCanvasProps {
  entities: SubgraphEntity[];
  edges: GraphEdge[];
  rootId: string;
  onOpenEntity: (entityId: string) => void;
}

const RELATION_KEY = "relationKey";

export default function KuzuSigmaCanvas({
  entities,
  edges,
  rootId,
  onOpenEntity,
}: KuzuSigmaCanvasProps) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const sigmaRef = React.useRef<Sigma | null>(null);
  const [selectedNodeId, setSelectedNodeId] = React.useState<string | null>(rootId);
  const [selectedRelationKey, setSelectedRelationKey] = React.useState<string | null>(null);
  const selectedNodeRef = React.useRef(selectedNodeId);
  const selectedRelationKeyRef = React.useRef(selectedRelationKey);
  selectedNodeRef.current = selectedNodeId;
  selectedRelationKeyRef.current = selectedRelationKey;

  React.useEffect(() => {
    setSelectedNodeId(rootId);
    setSelectedRelationKey(null);
  }, [rootId]);

  React.useEffect(() => {
    sigmaRef.current?.refresh();
  }, [selectedNodeId, selectedRelationKey]);

  React.useEffect(() => {
    if (!containerRef.current || entities.length === 0) return;

    const graph = new Graphology({ multi: true, type: "directed" });
    const root = entities.find((entity) => entity.id === rootId) ?? entities[0];
    const others = entities
      .filter((entity) => entity.id !== root.id)
      .sort((left, right) => left.canonical_name.localeCompare(right.canonical_name));
    const radius = Math.max(3.2, Math.min(6, 1.5 + others.length * 0.16));

    graph.addNode(root.id, {
      label: root.canonical_name,
      category: root.category,
      size: 15,
      x: 0,
      y: 0,
      isRoot: true,
    });
    others.forEach((entity, index) => {
      const angle = (2 * Math.PI * index) / Math.max(others.length, 1) - Math.PI / 2;
      graph.addNode(entity.id, {
        label: entity.canonical_name,
        category: entity.category,
        size: 10,
        x: Math.cos(angle) * radius,
        y: Math.sin(angle) * radius,
      });
    });

    edges.forEach((edge, index) => {
      const relationKey = `relation-${index}`;
      if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target)) return;
      graph.addEdge(edge.source, edge.target, {
        [RELATION_KEY]: relationKey,
        label: edge.relation_type,
        type: "arrow",
        size: Math.max(1, (edge.weight ?? 0.5) * 3),
        color: edge.is_disputed ? "#dc2626" : "#94a3b8",
      });
    });

    const sigma = new Sigma(graph, containerRef.current, {
      enableEdgeEvents: true,
      renderEdgeLabels: true,
      labelDensity: 0.12,
      labelGridCellSize: 60,
      labelRenderedSizeThreshold: 3,
      nodeReducer: (node, data) => {
        const isSelected = node === selectedNodeRef.current;
        return {
          ...data,
          color: isSelected ? "#1d4ed8" : categoryColor(data.category),
          size: Math.max(7, (data.size || 5) * (isSelected ? 1.25 : 1)),
          highlighted: isSelected,
        };
      },
      edgeReducer: (edge, data) => ({
        ...data,
        color: graph.getEdgeAttribute(edge, RELATION_KEY) === selectedRelationKeyRef.current
          ? "#2563eb"
          : data.color,
        size: graph.getEdgeAttribute(edge, RELATION_KEY) === selectedRelationKeyRef.current
          ? Math.max(3, data.size * 1.5)
          : data.size,
        forceLabel: graph.getEdgeAttribute(edge, RELATION_KEY) === selectedRelationKeyRef.current,
      }),
    });

    sigma.on("clickNode", ({ node }) => {
      setSelectedNodeId(node);
      setSelectedRelationKey(null);
    });
    sigma.on("clickEdge", ({ edge }) => {
      const relationKey = graph.getEdgeAttribute(edge, RELATION_KEY) as string;
      if (!relationKey) return;
      setSelectedNodeId(null);
      setSelectedRelationKey(relationKey);
    });

    sigmaRef.current = sigma;
    return () => {
      sigma.kill();
      sigmaRef.current = null;
    };
  }, [entities, edges, rootId]);

  const selectedEntity = entities.find((entity) => entity.id === selectedNodeId);
  const selectedRelation = selectedRelationKey
    ? (() => {
        const edgeIndex = Number(selectedRelationKey.replace("relation-", ""));
        return Number.isNaN(edgeIndex) ? undefined : edges[edgeIndex];
      })()
    : undefined;

  function selectRelation(index: number) {
    const edge = edges[index];
    if (!edge) return;
    setSelectedNodeId(null);
    setSelectedRelationKey(`relation-${index}`);
  }

  return (
    <div className="flex h-full min-h-[440px] flex-col lg:flex-row">
      <div className="relative min-h-[360px] flex-1 bg-slate-50">
        <div ref={containerRef} className="absolute inset-0" />
        <div className="absolute bottom-3 left-3 rounded bg-white/90 px-3 py-2 text-[11px] text-slate-600 shadow">
          Scroll to zoom · drag to pan · select a node or arrow for details
        </div>
        <div className="absolute left-3 top-3 flex flex-wrap gap-2 rounded bg-white/90 px-3 py-2 text-[11px] shadow">
          <LegendDot color="#1d4ed8" label="Selected" />
          <LegendDot color="#8b5cf6" label="Organization" />
          <LegendDot color="#3b82f6" label="Person" />
          <LegendDot color="#10b981" label="Location" />
          <LegendDot color="#dc2626" label="Disputed relation" />
        </div>
      </div>

      <aside className="flex max-h-[45vh] w-full shrink-0 flex-col border-t border-slate-200 bg-white lg:max-h-none lg:w-80 lg:border-l lg:border-t-0">
        <div className="border-b border-slate-200 px-4 py-3">
          <h3 className="font-semibold text-sm text-slate-900">Relations in this view</h3>
          <p className="mt-1 text-xs text-slate-500">
            {entities.length} entities · {edges.length} directed relations
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          {selectedRelation ? (
            <RelationDetails edge={selectedRelation} entities={entities} />
          ) : selectedEntity ? (
            <EntityDetails entity={selectedEntity} onOpenEntity={onOpenEntity} />
          ) : (
            <p className="mb-3 px-1 text-xs text-slate-500">Choose a relation to inspect its evidence.</p>
          )}

          <h4 className="mb-2 mt-4 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Relationship list
          </h4>
          {edges.length === 0 ? (
            <p className="rounded bg-slate-50 p-3 text-xs text-slate-500">
              No direct relationships are recorded for this entity yet.
            </p>
          ) : (
            <ul className="space-y-1">
              {edges.map((edge, index) => {
                const source = entities.find((entity) => entity.id === edge.source)?.canonical_name ?? edge.source;
                const target = entities.find((entity) => entity.id === edge.target)?.canonical_name ?? edge.target;
                return (
                  <li key={`${edge.source}-${edge.target}-${edge.relation_type}-${index}`}>
                    <button
                      type="button"
                      onClick={() => selectRelation(index)}
                      className="w-full rounded px-2 py-2 text-left text-xs hover:bg-blue-50"
                    >
                      <span className="block truncate font-medium text-slate-800">{source}</span>
                      <span className="block truncate pl-2 text-[10px] text-blue-700">
                        — {edge.relation_type} →
                      </span>
                      <span className="block truncate pl-4 text-slate-600">{target}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>
    </div>
  );
}

function EntityDetails({
  entity,
  onOpenEntity,
}: {
  entity: SubgraphEntity;
  onOpenEntity: (entityId: string) => void;
}) {
  return (
    <section className="rounded-lg border border-blue-100 bg-blue-50/60 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-blue-700">Entity</p>
      <h4 className="mt-1 font-semibold text-sm text-slate-900">{entity.canonical_name}</h4>
      <p className="mt-1 text-xs text-slate-600">{entity.category || "Uncategorized"}</p>
      {entity.summary && <p className="mt-2 text-xs leading-5 text-slate-700">{entity.summary}</p>}
      <p className="mt-2 text-[11px] text-slate-500">
        Confidence: {typeof entity.confidence === "number" ? `${Math.round(entity.confidence * 100)}%` : "unknown"}
      </p>
      <button
        type="button"
        className="mt-3 btn-primary btn-sm"
        onClick={() => onOpenEntity(entity.id)}
      >
        Read wiki dossier
      </button>
    </section>
  );
}

function RelationDetails({
  edge,
  entities,
}: {
  edge: GraphEdge;
  entities: SubgraphEntity[];
}) {
  const source = entities.find((entity) => entity.id === edge.source);
  const target = entities.find((entity) => entity.id === edge.target);
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-blue-700">Directed relation</p>
      <p className="mt-2 text-sm font-semibold text-slate-900">{edge.relation_type}</p>
      <p className="mt-2 text-xs leading-5 text-slate-700">
        {source?.canonical_name ?? edge.source} → {target?.canonical_name ?? edge.target}
      </p>
      <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-slate-500">
        {typeof edge.weight === "number" && <span>Weight {edge.weight.toFixed(2)}</span>}
        {typeof edge.claim_confidence === "number" && (
          <span>Confidence {Math.round(edge.claim_confidence * 100)}%</span>
        )}
        {typeof edge.entailment === "number" && <span>NLI {Math.round(edge.entailment * 100)}%</span>}
        {edge.is_disputed && <span className="font-semibold text-red-700">Disputed</span>}
      </div>
      {edge.claim_statement && <p className="mt-3 text-xs text-slate-700">{edge.claim_statement}</p>}
      {(edge.evidence ?? []).map((item, index) => (
        <div key={`${item.source_sha256}-${index}`} className="mt-3 border-l-2 border-emerald-300 pl-3">
          <blockquote className="text-xs leading-5 text-slate-700">“{item.exact_quote}”</blockquote>
          <p className="mt-1 break-all text-[10px] text-slate-500">
            Source SHA-256: {item.source_sha256}
          </p>
        </div>
      ))}
      {edge.claim_id && <p className="mt-2 break-all font-mono text-[10px] text-slate-400">{edge.claim_id}</p>}
    </section>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}

function categoryColor(category?: string) {
  switch (category) {
    case "Person": return "#3b82f6";
    case "Organization": return "#8b5cf6";
    case "Location": return "#10b981";
    case "MilitarySystem": return "#f59e0b";
    case "Component": return "#ef4444";
    case "NarrativeFrame": return "#ec4899";
    case "Event": return "#06b6d4";
    default: return "#64748b";
  }
}
