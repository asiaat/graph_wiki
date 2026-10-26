import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Copy } from "lucide-react";

interface CompiledWikiViewProps {
  content: string;
  frontmatter: Record<string, any>;
}

export default function CompiledWikiView({ content, frontmatter }: CompiledWikiViewProps) {
  const [copied, setCopied] = useState(false);

  return (
    <div className="prose prose-sm max-w-none p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">{frontmatter.canonical_name || "Entity"}</h1>
        <div className="flex gap-2">
          <span className={`badge badge-admiralty-${(frontmatter.admiralty_rating || "f").toLowerCase().split("_")[0]}`}>
            {frontmatter.admiralty_rating?.split("_")[1] || "F"}
          </span>
          <span className="badge badge-gray-100">{frontmatter.entity_type}</span>
          <span className="badge badge-gray-100">Confidence: {(frontmatter.confidence_score || 0.5) * 100}%</span>
        </div>
      </div>

      <div className="mb-4 p-3 bg-gray-50 rounded-lg text-xs text-gray-600">
        Last compiled: {frontmatter.last_compiled} • kuzu_id: {frontmatter.kuzu_id}
      </div>

      <div className="relative">
        <button
          className="absolute top-2 right-2 btn btn-secondary btn-sm"
          onClick={() => {
            navigator.clipboard.writeText(content);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
          }}
        >
          <Copy size={14} className="mr-1" />
          {copied ? "Copied!" : "Copy Markdown"}
        </button>
        <ReactMarkdown>{content}</ReactMarkdown>
      </div>
    </div>
  );
}