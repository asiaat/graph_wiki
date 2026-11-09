import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy } from "lucide-react";

interface CompiledWikiViewProps {
  content: string;
  frontmatter: Record<string, any>;
  onOpenWikiSlug?: (slug: string) => void;
}

export default function CompiledWikiView({
  content,
  frontmatter,
  onOpenWikiSlug,
}: CompiledWikiViewProps) {
  const [copied, setCopied] = useState(false);

  const admiralty = String(frontmatter.admiralty_rating || "F_CANNOT_BE_JUDGED");
  const admiraltyLetter = admiralty.charAt(0).toLowerCase();
  const markdownWithWikiLinks = content.replace(
    /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g,
    (_match, slug: string, label?: string) =>
      `[${label || slug}](#wiki:${encodeURIComponent(slug.trim())})`,
  );

  return (
    <div className="prose prose-sm max-w-none p-4">
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">{frontmatter.canonical_name || "Entity"}</h1>
        <div className="flex gap-2">
          <span className={`badge badge-admiralty-${admiraltyLetter}`}>{admiralty}</span>
          <span className="badge badge-gray-100">{frontmatter.entity_type}</span>
          <span className="badge badge-gray-100">
            Confidence: {Math.round((frontmatter.confidence_score || 0.5) * 100)}%
          </span>
        </div>
      </div>

      <div className="mb-4 p-3 bg-gray-50 rounded-lg text-xs text-gray-600">
        Last compiled: {String(frontmatter.last_compiled ?? "n/a")} • kuzu_id:{" "}
        {String(frontmatter.kuzu_id ?? "n/a")}
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
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) => {
              if (href?.startsWith("#wiki:")) {
                const slug = decodeURIComponent(href.slice("#wiki:".length));
                return (
                  <button
                    type="button"
                    className="text-blue-700 underline decoration-blue-300 underline-offset-2 hover:text-blue-900"
                    onClick={() => onOpenWikiSlug?.(slug)}
                  >
                    {children}
                  </button>
                );
              }
              return (
                <a href={href} target="_blank" rel="noreferrer">
                  {children}
                </a>
              );
            },
          }}
        >
          {markdownWithWikiLinks}
        </ReactMarkdown>
      </div>
    </div>
  );
}
