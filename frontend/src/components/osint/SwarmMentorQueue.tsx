import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useComplicateEntity } from "../../hooks/useKuzuSubgraph";
import { apiClient } from "../../services/apiClient";

interface GapTicket {
  ticket_id: string;
  target_entity_id: string;
  gap_description: string;
  required_evidence: string;
  created_at: string | null;
}

interface SwarmMentorQueueProps {
  entityId: string | null;
}

export default function SwarmMentorQueue({ entityId }: SwarmMentorQueueProps) {
  const [target, setTarget] = useState("");
  const complicateMutation = useComplicateEntity();
  const queryClient = useQueryClient();
  const gapTickets = useQuery<{ tickets: GapTicket[] }>({
    queryKey: ["osint", "gap-tickets", "OPEN"],
    queryFn: async () => {
      const response = await apiClient.get("/osint/gap-tickets", { params: { status: "OPEN" } });
      return response.data as { tickets: GapTicket[] };
    },
    refetchInterval: 30000,
  });
  const reviewGap = useMutation({
    mutationFn: async (input: { ticketId: string; action: "approve" | "reject" | "defer" }) =>
      apiClient.post("/osint/gap-tickets/review", {
        ticket_id: input.ticketId,
        action: input.action,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["osint", "gap-tickets"] }),
  });

  const entityIdToUse = target.trim() || entityId || "";

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Search size={20} className="text-gray-500" />
        <h3 className="font-semibold text-sm">Complicate Subgraph</h3>
      </div>
      <div className="space-y-2">
        <div className="relative">
          <input
            type="text"
            placeholder="Entity ID (e.g. organization:acme-corporation)"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="input pl-10"
          />
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 h-4 w-4" />
        </div>
        {entityId && !target && (
          <p className="text-xs text-gray-500">Will target the selected entity: {entityId}</p>
        )}
        <button
          disabled={!entityIdToUse || complicateMutation.isPending}
          onClick={() => complicateMutation.mutate(entityIdToUse)}
          className="btn-primary btn-sm w-full"
        >
          {complicateMutation.isPending ? "Complicating..." : "Dispatch OSINT Agent"}
        </button>
      </div>
      {complicateMutation.isPending && (
        <div className="bg-yellow-50 border-l-4 border-yellow-500 p-3 rounded-r-lg">
          <p className="text-xs text-yellow-800">
            OSINT agent hunting for corroborating sources...
          </p>
        </div>
      )}
      {complicateMutation.isSuccess && (
        <div className="bg-green-50 border-l-4 border-green-500 p-3 rounded-r-lg">
          <p className="text-xs text-green-800">
            Tickets opened:{" "}
            {((complicateMutation.data as { tickets_created?: string[] })?.tickets_created ?? []).length}
          </p>
        </div>
      )}
      {complicateMutation.error && (
        <div className="bg-red-50 border-l-4 border-red-500 p-3 rounded-r-lg">
          <p className="text-xs text-red-800">Error: {String(complicateMutation.error)}</p>
        </div>
      )}

      <div className="border-t border-gray-200 pt-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-sm">Evidence Gap Queue</h3>
          <span className="text-xs text-gray-500">{gapTickets.data?.tickets.length ?? 0} open</span>
        </div>
        {gapTickets.isLoading ? (
          <p className="text-xs text-gray-500">Loading gap tickets…</p>
        ) : gapTickets.error ? (
          <p className="text-xs text-red-600">Could not load evidence gaps.</p>
        ) : (gapTickets.data?.tickets.length ?? 0) === 0 ? (
          <p className="text-xs text-gray-500">No open query gaps.</p>
        ) : (
          <ul className="space-y-3">
            {gapTickets.data?.tickets.slice(0, 8).map((ticket) => (
              <li key={ticket.ticket_id} className="rounded border border-amber-200 bg-amber-50 p-3">
                <p className="text-xs font-medium text-gray-800">{ticket.gap_description}</p>
                {ticket.target_entity_id && (
                  <p className="mt-1 break-all text-[11px] text-gray-500">
                    Entity: {ticket.target_entity_id}
                  </p>
                )}
                <p className="mt-1 text-[11px] text-gray-600">{ticket.required_evidence}</p>
                <div className="mt-2 flex gap-2">
                  <button
                    className="btn-secondary btn-sm"
                    disabled={reviewGap.isPending}
                    onClick={() => reviewGap.mutate({ ticketId: ticket.ticket_id, action: "approve" })}
                  >
                    Approve
                  </button>
                  <button
                    className="btn-secondary btn-sm"
                    disabled={reviewGap.isPending}
                    onClick={() => reviewGap.mutate({ ticketId: ticket.ticket_id, action: "defer" })}
                  >
                    Defer
                  </button>
                  <button
                    className="btn-secondary btn-sm"
                    disabled={reviewGap.isPending}
                    onClick={() => reviewGap.mutate({ ticketId: ticket.ticket_id, action: "reject" })}
                  >
                    Reject
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
        {reviewGap.error && <p role="alert" className="text-xs text-red-600">Could not update the gap ticket.</p>}
      </div>
    </div>
  );
}
