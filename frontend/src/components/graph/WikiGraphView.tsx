import KuzuSigmaCanvas from "./KuzuSigmaCanvas";
import { useWikiMap } from "../../hooks/useKuzuSubgraph";

interface WikiGraphViewProps {
  selectedEntityId: string | null;
  onOpenEntity: (entityId: string) => void;
}

export default function WikiGraphView({ selectedEntityId, onOpenEntity }: WikiGraphViewProps) {
  const { data, isLoading, error } = useWikiMap();

  if (isLoading) {
    return <div className="p-6 text-sm text-slate-500">Loading the wiki graph…</div>;
  }
  if (error) {
    return <div className="p-6 text-sm text-red-600">Could not load the wiki graph: {String(error)}</div>;
  }
  if (!data?.entities.length) {
    return <div className="p-6 text-sm text-slate-500">No wiki dossiers are in the graph yet.</div>;
  }

  const rootId = data.entities.some((entity) => entity.id === selectedEntityId)
    ? selectedEntityId!
    : data.entities[0].id;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-slate-200 bg-white px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-900">Wiki graph</h3>
        <p className="mt-1 text-xs text-slate-600">
          Each node is a compiled wiki dossier. Select a node to read its page, or an arrow to inspect the cited relationship.
        </p>
        <details className="mt-2 max-w-3xl rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-700">
          <summary className="cursor-pointer font-medium text-slate-800">How are nodes and relations defined?</summary>
          <div className="mt-2 space-y-1.5 leading-5">
            <p><strong>Node:</strong> one compiled entity dossier, such as an organization, person, or component.</p>
            <p><strong>Arrow:</strong> a directed, typed relation recorded between two entities. Its direction runs from source to target.</p>
            <p><strong>Evidence:</strong> selecting an arrow shows the linked claim and its source quote when available. A node without arrows has no relation recorded in this graph yet.</p>
          </div>
        </details>
      </div>
      <div className="min-h-0 flex-1">
        <KuzuSigmaCanvas
          entities={data.entities}
          edges={data.edges}
          rootId={rootId}
          onOpenEntity={onOpenEntity}
        />
      </div>
    </div>
  );
}
