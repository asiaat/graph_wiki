import React from "react";

interface VerbatimPopoverProps {
  quote: string;
  sourceTitle: string;
  nliScore: number;
}

export default function VerbatimPopover({ quote, sourceTitle, nliScore }: VerbatimPopoverProps) {
  return (
    <div className="p-3 bg-white border border-gray-200 rounded-lg shadow-lg max-w-md">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-700">{sourceTitle}</span>
        <span className="text-xs px-2 py-0.5 bg-green-100 text-green-800 rounded">
          NLI: {(nliScore * 100).toFixed(0)}%
        </span>
      </div>
      <p className="text-sm text-gray-700 italic">"{quote}"</p>
    </div>
  );
}