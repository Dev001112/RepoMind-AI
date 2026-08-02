/**
 * Phase 3.3 — search-first retrieval UX.
 *
 * Search bar with debounced suggestions, intent badge, scored result cards,
 * a knowledge-graph preview, and per-run retrieval metrics. All buttons,
 * badges and cards use the project's shadcn-style primitive components; no
 * Tailwind classes beyond what RepositoryPage already uses.
 */

import { FormEvent, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useIntelligentSearch, useQueryHistory, useSuggestions } from "@/hooks/useRepositories";
import { cn } from "@/lib/utils";
import type {
  KnowledgeGraph,
  RerankedHit,
  SearchMode,
} from "@/types/retrieval";
import type { RetrievalContext } from "@/types/retrieval";

const SEARCH_MODES: { value: SearchMode; label: string }[] = [
  { value: "auto", label: "auto" },
  { value: "semantic", label: "semantic" },
  { value: "hybrid", label: "hybrid" },
  { value: "exact", label: "exact" },
  { value: "relationship", label: "relationship" },
  { value: "architecture", label: "architecture" },
  { value: "dependency", label: "dependency" },
  { value: "documentation", label: "documentation" },
];

const INTENT_LABEL: Record<string, string> = {
  architecture: "architecture",
  explanation: "explanation",
  setup: "setup",
  deployment: "deployment",
  api: "api",
  database: "database",
  security: "security",
  performance: "performance",
  dependencies: "dependencies",
  documentation: "documentation",
  file_lookup: "file",
  function_lookup: "function",
  class_lookup: "class",
  comparison: "compare",
  bug_investigation: "bug",
  feature_location: "feature",
};

function TypeFact({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <Badge variant="outline" className="font-mono text-[10px]">
      {label}: {value}
    </Badge>
  );
}

function SuggestionList({
  items,
  onPick,
  visible,
}: {
  items: string[];
  onPick: (q: string) => void;
  visible: boolean;
}) {
  if (!visible || items.length === 0) return null;
  return (
    <div className="absolute left-0 right-0 top-full z-20 mt-1 rounded-lg border border-border bg-card py-1 shadow-lg">
      {items.map((suggestion) => (
        <button
          key={suggestion}
          type="button"
          onClick={() => onPick(suggestion)}
          className="w-full px-4 py-2 text-left font-mono text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          {suggestion}
        </button>
      ))}
    </div>
  );
}

function GraphPreview({ graph }: { graph: KnowledgeGraph }) {
  const nodes = graph.nodes.slice(0, 8);
  const nodeIndex = useMemo(
    () => new Map(nodes.map((n, i) => [n.id, i])),
    [nodes],
  );
  if (graph.nodes.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-mono text-xs text-muted-foreground">
          knowledge graph
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          {nodes.map((node) => (
            <div
              key={node.id}
              className="flex flex-col gap-1 rounded-lg border border-border px-2 py-1.5"
            >
              <Badge variant="outline" className="w-min font-mono text-[10px]">
                {node.type}
              </Badge>
              <span
                className="max-w-36 truncate font-mono text-[11px] text-foreground"
                title={node.label}
              >
                {node.label}
              </span>
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-1">
          {graph.edges.slice(0, 6).map((edge, i) => {
            const source = nodeIndex.get(edge.source);
            const target = nodeIndex.get(edge.target);
            if (source === undefined || target === undefined) return null;
            return (
              <div
                key={`${edge.source}-${edge.target}-${i}`}
                className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground"
              >
                <span className="max-w-[140px] truncate">
                  {nodes[source].label}
                </span>
                <span className="text-primary">-- {edge.kind} --&gt;</span>
                <span className="max-w-[140px] truncate">
                  {nodes[target].label}
                </span>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

function SearchResults({ context }: { context: RetrievalContext }) {
  if (context.chunks.length === 0) {
    return (
      <p className="font-mono text-xs text-muted-foreground">
        no results for “{context.query}” — try different wording, or clear the
        chunk-type filter.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-2">
      {context.chunks.map((hit) => (
        <SearchCard key={hit.chunkId} hit={hit} />
      ))}
    </div>
  );
}

function SearchCard({ hit }: { hit: RerankedHit }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 py-3">
        <div className="flex items-center gap-2 font-mono text-xs">
          <Badge variant="outline">{INTENT_LABEL[hit.type] ?? hit.type}</Badge>
          <span className="flex-1 truncate font-medium text-foreground">
            {hit.title}
          </span>
          <span className="text-success">{hit.displayScore}%</span>
          {hit.hop > 0 && (
            <span className="text-muted-foreground/60">hop {hit.hop}</span>
          )}
        </div>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {hit.summary}
        </p>
        {(hit.file || hit.symbol) && (
          <p className="truncate font-mono text-xs text-muted-foreground/70">
            {hit.file}
            {hit.symbol ? ` › ${hit.symbol}` : ""}
          </p>
        )}
        {hit.relatedChunks.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-xs text-muted-foreground/50">
              related
            </span>
            {hit.relatedChunks.slice(0, 4).map((related) => (
              <Badge key={related.chunkId} variant="outline" className="font-mono text-[10px]">
                {related.title}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MetricsBar({ context }: { context: RetrievalContext }) {
  const m = context.metrics;
  return (
    <div className="flex flex-wrap items-center gap-2 font-mono text-xs text-muted-foreground">
      <Badge variant="outline">intent: {INTENT_LABEL[context.intent] ?? context.intent}</Badge>
      <span>confidence {Math.round(context.confidence * 100)}%</span>
      <span>latency {m.latencyMs.toFixed(0)}ms</span>
      <span>cache {m.cacheHit ? "hit" : "miss"}</span>
      <span>candidates {m.totalCandidates}</span>
      <span>returned {m.returnedChunks}</span>
      {m.compressionRatio > 0 && m.compressionRatio !== 1 && (
        <span>compression ×{m.compressionRatio}</span>
      )}
    </div>
  );
}

function MetadataFacts({ context }: { context: RetrievalContext }) {
  const m = context.metadata;
  if (!m.type && !m.language && !m.framework && !m.file && !m.symbol && !m.apiRoute) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <TypeFact label="type" value={m.type} />
      <TypeFact label="language" value={m.language} />
      <TypeFact label="framework" value={m.framework} />
      <TypeFact label="file" value={m.file} />
      <TypeFact label="symbol" value={m.symbol} />
      <TypeFact label="api" value={m.apiRoute} />
    </div>
  );
}

export function RetrievalSearch({ repositoryId }: { repositoryId: string }) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("auto");
  const [activeType, setActiveType] = useState<string | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [submittedQuery, setSubmittedQuery] = useState<string | null>(null);

  const search = useIntelligentSearch(repositoryId);
  const suggestions = useSuggestions(repositoryId, submittedQuery ?? "", true);
  const history = useQueryHistory(repositoryId);

  useEffect(() => {
    if (!submittedQuery) return;
    const t = window.setTimeout(() => setSuggestionsOpen(false), 400);
    return () => window.clearTimeout(t);
  }, [submittedQuery]);

  function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    setSubmittedQuery(trimmed);
    setSuggestionsOpen(false);
    search.mutate({
      query: trimmed,
      mode,
      filters: activeType ? { type: activeType } : null,
      limit: 10,
    });
  }

  function pickSuggestion(suggestion: string) {
    setQuery(suggestion);
    setSuggestionsOpen(false);
    setSubmittedQuery(suggestion);
    search.mutate({
      query: suggestion,
      mode,
      filters: activeType ? { type: activeType } : null,
      limit: 10,
    });
  }

  const visibleSuggestions = useMemo(() => {
    if (suggestionsOpen === false) return [];
    const base = suggestions.data?.items ?? [];
    if (!submittedQuery) return base;
    return base.filter((s) => s.toLowerCase().includes(submittedQuery.toLowerCase()));
  }, [suggestions.data, submittedQuery, suggestionsOpen]);

  const context = search.data?.context ?? null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="font-mono text-sm font-medium text-muted-foreground">
          search the knowledge
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {/* Search bar */}
        <div className="relative">
          <form
            onSubmit={runSearch}
            className="flex items-center gap-3 rounded-lg border border-border bg-background px-4 py-2.5 focus-within:ring-1 focus-within:ring-ring"
            aria-label="intelligent search"
          >
            <span className="font-mono text-xs text-primary">?</span>
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                if (event.target.value) setSuggestionsOpen(true);
              }}
              onFocus={() => suggestions.data && setSuggestionsOpen(true)}
              placeholder="ask about the code -- e.g. 'how does authentication work'"
              className="flex-1 bg-transparent font-mono text-sm placeholder:text-muted-foreground focus:outline-none"
            />
            <Button
              type="submit"
              size="sm"
              disabled={search.isPending}
              className="gap-1.5"
            >
              {search.isPending ? "searching…" : "search"}
            </Button>
          </form>

          <SuggestionList
            items={visibleSuggestions}
            onPick={pickSuggestion}
            visible={suggestionsOpen}
          />
        </div>

        {/* Controls */}
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          <div className="flex flex-wrap gap-1.5">
            {SEARCH_MODES.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setMode(option.value)}
                className={cn(
                  "rounded-full border px-2.5 py-1 transition-colors",
                  mode === option.value
                    ? "border-primary bg-primary/10 text-foreground"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
          {activeType && (
            <Badge variant="outline" className="font-mono text-[10px]">
              type: {activeType}
              <button
                type="button"
                onClick={() => setActiveType(null)}
                className="ml-1 text-muted-foreground hover:text-foreground"
              >
                ×
              </button>
            </Badge>
          )}
        </div>

        {/* Analysis banners */}
        {context && (
          <div className="flex flex-col gap-2">
            <MetricsBar context={context} />
            <MetadataFacts context={context} />
            {context.summary && (
              <Card className="border-primary/20 bg-primary/5">
                <CardContent className="py-3">
                  <p className="font-mono text-[11px] leading-relaxed text-foreground">
                    {context.summary}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {context.citations.slice(0, 4).map((citation) => (
                      <Badge key={citation.chunkId} variant="outline" className="font-mono text-[10px]">
                        {citation.title}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* Results */}
        {context && (
          <SearchResults context={context} />
        )}

        {/* Graph */}
        {context && context.graph.nodes.length > 0 && (
          <GraphPreview graph={context.graph} />
        )}

        {/* History toggle */}
        {history.data && history.data.total > 0 && (
          <div className="flex flex-col gap-1">
            <button
              type="button"
              onClick={() => setHistoryOpen((current) => !current)}
              className="self-start font-mono text-xs text-muted-foreground hover:text-foreground"
            >
              {historyOpen ? "▾" : "▸"} history ({history.data.total})
            </button>
            {historyOpen && (
              <div className="flex flex-col gap-1 rounded-lg border border-border bg-background/50 p-2">
                {history.data.items.slice(0, 5).map((record) => (
                  <div
                    key={record.id}
                    className="flex items-center gap-3 font-mono text-[11px] text-muted-foreground"
                  >
                    <span className="w-34 shrink-0 truncate text-foreground">
                      {record.query}
                    </span>
                    <Badge variant="outline" className="w-16 shrink-0">
                      {INTENT_LABEL[record.intent] ?? record.intent}
                    </Badge>
                    <span className="text-muted-foreground/60">
                      {record.latencyMs.toFixed(0)}ms
                      {record.cacheHit ? " cache" : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
