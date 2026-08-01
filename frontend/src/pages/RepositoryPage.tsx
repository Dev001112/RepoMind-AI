import { useState, type FormEvent, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import {
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Loader2,
  Search,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";
import {
  useKnowledgeSearch,
  useKnowledgeStats,
  useRepository,
  useRepositoryAnalysisRuns,
  useRepositoryChat,
  useRepositoryChunks,
  useRepositoryKnowledge,
  useRepositoryMetrics,
  useRepositoryProgress,
} from "@/hooks/useRepositories";
import type {
  ChatMessage,
  KnowledgeSearchHit,
  RepositoryStatus,
  StageProgress,
} from "@/types/repository";

const STATUS_STYLE: Record<RepositoryStatus, string> = {
  pending: "bg-primary animate-pulse",
  cloning: "bg-primary animate-pulse",
  scanning: "bg-primary animate-pulse",
  knowledge_built: "bg-primary animate-pulse",
  embedding: "bg-primary animate-pulse",
  ready: "bg-success",
  failed: "bg-destructive",
};

const STAGE_STATE_STYLE: Record<StageProgress["state"], string> = {
  done: "bg-success",
  active: "bg-primary animate-pulse",
  queued: "bg-muted-foreground/40",
  failed: "bg-destructive",
};

function StatusPill({ status }: { status: RepositoryStatus }) {
  return (
    <span className="inline-flex items-center gap-2 font-mono text-xs text-muted-foreground">
      <span className={cn("h-1.5 w-1.5 rounded-full", STATUS_STYLE[status])} />
      {status}
    </span>
  );
}

function ProgressBar({ percent, className }: { percent: number; className?: string }) {
  return (
    <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-muted", className)}>
      <div
        className="h-full rounded-full bg-primary transition-all duration-500"
        style={{ width: `${Math.min(100, Math.max(0, percent))}%` }}
      />
    </div>
  );
}

function Requirement({
  label,
  value,
  trueIsGood = false,
}: {
  label: string;
  value: boolean | null;
  trueIsGood?: boolean;
}) {
  const unknown = value === null;
  const good = unknown ? false : trueIsGood ? value : !value;
  return (
    <div className="flex items-center justify-between py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span
        className={cn(
          "font-mono text-xs",
          unknown ? "text-muted-foreground" : good ? "text-success" : "text-primary",
        )}
      >
        {unknown ? "unknown" : value ? "yes" : "no"}
      </span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="font-mono text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

function relativeTime(iso: string | null): string | null {
  if (!iso) return null;
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

function ProgressPanel({ id }: { id: string }) {
  const { data: progress, isLoading } = useRepositoryProgress(id, true);

  if (isLoading || !progress) {
    return (
      <div className="flex items-center gap-2 font-mono text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        starting analysis...
      </div>
    );
  }

  const scanning = progress.stages.find((s) => s.name === "scanning");

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-baseline justify-between font-mono text-sm font-medium text-muted-foreground">
          <span>analysis pipeline</span>
          <span className="text-foreground">{progress.overallPercent}%</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <ProgressBar percent={progress.overallPercent} className="h-2" />
          <p className="font-mono text-xs text-muted-foreground">
            {progress.message ?? progress.status}
          </p>
        </div>

        <div className="flex flex-col gap-3">
          {progress.stages.map((stage) => (
            <div key={stage.name} className="flex flex-col gap-1">
              <div className="flex items-center gap-2 font-mono text-xs">
                <span className={cn("h-1.5 w-1.5 rounded-full", STAGE_STATE_STYLE[stage.state])} />
                <span className="text-foreground">{stage.label}</span>
                <span className="ml-auto text-muted-foreground/60">
                  {stage.state === "done"
                    ? "done"
                    : stage.state === "failed"
                      ? "failed"
                      : `${stage.percent}%`}
                </span>
              </div>
              {stage.name !== "scanning" ? (
                <ProgressBar percent={stage.percent} className="ml-3.5 w-[calc(100%-0.875rem)]" />
              ) : null}
              {stage.name === "scanning" && scanning?.detectors ? (
                <div className="ml-3.5 grid grid-cols-1 gap-x-6 sm:grid-cols-2">
                  {scanning.detectors.map((detector) => (
                    <div
                      key={detector.name}
                      className="flex items-center gap-2 py-1 font-mono text-xs"
                    >
                      <span className="w-36 shrink-0 truncate text-muted-foreground">
                        {detector.label}
                      </span>
                      <ProgressBar percent={detector.percent} className="flex-1" />
                      <span className="w-8 shrink-0 text-right text-muted-foreground/60">
                        {detector.percent}%
                      </span>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function MetricStat({
  label,
  value,
  unit,
}: {
  label: string;
  value: number | null;
  unit?: string;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 py-4">
        <span className="font-mono text-2xl font-semibold text-foreground">
          {value === null ? "–" : value.toLocaleString()}
          {unit ? (
            <span className="ml-1 text-xs font-normal text-muted-foreground">{unit}</span>
          ) : null}
        </span>
        <span className="font-mono text-xs text-muted-foreground">{label}</span>
      </CardContent>
    </Card>
  );
}

function AnalysisOverview({ id }: { id: string }) {
  const { data: knowledge, isLoading, isError } = useRepositoryKnowledge(id, true);
  const { data: metrics } = useRepositoryMetrics(id, true);
  const { data: runs } = useRepositoryAnalysisRuns(id, true);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 font-mono text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        loading report...
      </div>
    );
  }
  if (isError || !knowledge) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="font-mono text-sm font-medium text-destructive">
            report unavailable
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Analysis finished, but the knowledge report couldn't be loaded. Try refreshing --
            if that doesn't help, check the backend logs for repository {id}.
          </p>
        </CardContent>
      </Card>
    );
  }

  const metricByName = new Map((metrics ?? []).map((m) => [m.metricName, m]));
  const latestRun = runs?.[0];

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-col gap-2 py-4">
          {(knowledge.metadata.name || knowledge.metadata.description) && (
            <div className="flex flex-col gap-0.5">
              {knowledge.metadata.name && (
                <span className="font-mono text-base font-semibold text-foreground">
                  {knowledge.metadata.name}
                </span>
              )}
              {knowledge.metadata.description && (
                <p className="text-sm text-muted-foreground">
                  {knowledge.metadata.description}
                </p>
              )}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-2 text-success">
            <span className="h-1.5 w-1.5 rounded-full bg-success" />
            analysis complete
          </span>
          <span>knowledge built</span>
          <span>
            last scan{" "}
            {knowledge.metadata.analyzedAt
              ? relativeTime(knowledge.metadata.analyzedAt)
              : "recently"}
          </span>
          {latestRun?.durationMs != null && (
            <span>scan time {(latestRun.durationMs / 1000).toFixed(1)}s</span>
          )}
          <span className="inline-flex items-center gap-2">
            {metricByName.get("languages")?.metricValue ?? knowledge.languages.languages.length}{" "}
            languages
          </span>
          <span className="inline-flex items-center gap-2">
            {metricByName.get("frameworks")?.metricValue ?? knowledge.frameworks.frameworks.length}{" "}
            frameworks
          </span>
        </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <MetricStat
          label="files"
          value={metricByName.get("total_files")?.metricValue ?? knowledge.files.totalFiles}
        />
        <MetricStat
          label="symbols"
          value={metricByName.get("total_symbols")?.metricValue ?? knowledge.symbols.totalSymbols}
        />
        <MetricStat
          label="endpoints"
          value={metricByName.get("endpoints")?.metricValue ?? knowledge.apis.endpoints.length}
        />
        <MetricStat
          label="dependencies"
          value={
            metricByName.get("dependencies")?.metricValue ??
            Object.keys(knowledge.dependencies.dependencies).length
          }
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Section title="languages & frameworks">
          <div className="flex flex-wrap gap-1.5">
            {knowledge.languages.languages.map((l) => (
              <Badge key={l}>{l}</Badge>
            ))}
            {knowledge.frameworks.frameworks.map((f) => (
              <Badge key={f} variant="outline">
                {f}
              </Badge>
            ))}
            {knowledge.languages.languages.length === 0 &&
              knowledge.frameworks.frameworks.length === 0 && (
                <p className="text-sm text-muted-foreground">None detected.</p>
              )}
          </div>
        </Section>

        <Section title="dependencies">
          {Object.keys(knowledge.dependencies.dependencies).length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(knowledge.dependencies.dependencies).map(([name, version]) => (
                <Badge key={name} variant="outline">
                  {name}
                  {version ? `@${version}` : ""}
                </Badge>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No dependencies detected.</p>
          )}
        </Section>

        <Section title="requirements">
          <Requirement label="GPU required" value={knowledge.cuda.gpuRequired} />
          <Requirement label="CUDA required" value={knowledge.cuda.cudaRequired} />
          <Requirement label="Docker support" value={knowledge.docker.dockerSupport} trueIsGood />
        </Section>

        <Section title="readiness">
          <div className="flex flex-col gap-1.5 text-sm">
            <p>
              <span className="text-muted-foreground">production readiness:</span>{" "}
              {knowledge.architecture.productionReadiness ?? "unknown"}
            </p>
            <p>
              <span className="text-muted-foreground">difficulty:</span>{" "}
              {knowledge.architecture.difficultyLevel ?? "unknown"}
            </p>
            <p>
              <span className="text-muted-foreground">license:</span>{" "}
              {knowledge.metadata.license ?? "unknown"}
            </p>
          </div>
        </Section>

        <Section title="install">
          {knowledge.documentation.installationSteps.length > 0 ? (
            <pre className="overflow-x-auto rounded-md bg-background p-3 font-mono text-xs leading-relaxed text-foreground">
              {knowledge.documentation.installationSteps.join("\n")}
            </pre>
          ) : (
            <p className="text-sm text-muted-foreground">No installation steps detected.</p>
          )}
        </Section>

        <Section title="analysis runs">
          {runs && runs.length > 0 ? (
            <div className="flex flex-col divide-y divide-border">
              {runs.slice(0, 5).map((run) => (
                <div key={run.id} className="flex items-center gap-2 py-1.5 font-mono text-xs">
                  <span
                    className={cn(
                      "h-1.5 w-1.5 rounded-full",
                      run.status === "completed"
                        ? "bg-success"
                        : run.status === "failed"
                          ? "bg-destructive"
                          : "bg-primary",
                    )}
                  />
                  <span className="text-muted-foreground">{run.trigger}</span>
                  <span className="text-muted-foreground/60">
                    {relativeTime(run.startedAt)}
                  </span>
                  <span className="ml-auto text-muted-foreground/60">
                    {run.status}
                    {run.durationMs != null && run.status === "completed"
                      ? ` · ${(run.durationMs / 1000).toFixed(1)}s`
                      : ""}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">No runs recorded yet.</p>
          )}
        </Section>

        {knowledge.architecture.summary && (
          <div className="md:col-span-2">
            <Section title="architecture">
              <p className="text-sm leading-relaxed text-muted-foreground">
                {knowledge.architecture.summary}
              </p>
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}

const CHUNK_TYPE_LABEL: Record<string, string> = {
  summary: "summary",
  architecture: "architecture",
  folder: "folder",
  file: "file",
  api_endpoint: "api endpoint",
  database: "database",
  framework: "framework",
  dependency: "dependency",
  docker: "docker",
  cuda: "cuda",
  cicd: "ci/cd",
  deployment: "deployment",
  testing: "testing",
  documentation: "documentation",
  performance: "performance",
  security: "security",
  quality: "quality",
};

function KnowledgeHitCard({ hit }: { hit: KnowledgeSearchHit }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 py-3">
        <div className="flex items-center gap-2 font-mono text-xs">
          <Badge variant="outline">{CHUNK_TYPE_LABEL[hit.type] ?? hit.type}</Badge>
          <span className="font-medium text-foreground">{hit.title}</span>
          <span className="ml-auto text-success">{Math.round(hit.score * 100)}%</span>
        </div>
        <p className="text-sm leading-relaxed text-muted-foreground">{hit.summary}</p>
        {(hit.file || hit.symbol) && (
          <p className="truncate font-mono text-xs text-muted-foreground/70">
            {hit.file}
            {hit.symbol ? ` › ${hit.symbol}` : ""}
          </p>
        )}
        {hit.relatedChunks.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-xs text-muted-foreground/50">related</span>
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

function KnowledgeExplorer({ id }: { id: string }) {
  const { data: stats } = useKnowledgeStats(id, true);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"semantic" | "hybrid">("semantic");
  const [activeType, setActiveType] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const search = useKnowledgeSearch(id);
  const chunkPage = useRepositoryChunks(id, {
    chunkType: activeType ?? undefined,
    page,
    pageSize: 12,
  });

  function runSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) return;
    search.mutate({
      query: trimmed,
      mode,
      filters: activeType ? { type: activeType } : {},
    });
  }

  function toggleType(chunkType: string) {
    setActiveType((current) => (current === chunkType ? null : chunkType));
    setPage(1);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <MetricStat label="knowledge chunks" value={stats?.totalChunks ?? null} />
        <MetricStat label="categories" value={stats?.categories.length ?? null} />
        <MetricStat label="files indexed" value={stats?.filesIndexed ?? null} />
        <Card>
          <CardContent className="flex flex-col gap-1 py-4">
            <span className="font-mono text-2xl font-semibold text-foreground">
              {stats?.languages.length ?? 0}
            </span>
            <span className="font-mono text-xs text-muted-foreground">languages</span>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="font-mono text-sm font-medium text-muted-foreground">
            knowledge explorer
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <form
            onSubmit={runSearch}
            className="flex items-center gap-3 rounded-lg border border-border bg-background px-4 py-2.5 focus-within:ring-1 focus-within:ring-ring"
          >
            <Search className="h-4 w-4 text-primary" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="search the knowledge -- try 'how does authentication work'"
              className="flex-1 bg-transparent font-mono text-sm placeholder:text-muted-foreground focus:outline-none"
            />
            <Button type="submit" size="sm" disabled={search.isPending} className="gap-1.5">
              {search.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              search
            </Button>
          </form>

          <div className="flex items-center gap-4 font-mono text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              semantic
            </span>
            <button
              type="button"
              onClick={() => setMode((m) => (m === "semantic" ? "hybrid" : "semantic"))}
              className={cn(
                "rounded-full border px-3 py-1 transition-colors",
                mode === "hybrid"
                  ? "border-primary text-foreground"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              hybrid (keyword + vector)
            </button>
          </div>

          {search.data && search.data.results.length === 0 && (
            <p className="font-mono text-xs text-muted-foreground">
              no knowledge matched "{search.data.query}" -- try different wording, or clear the
              category filter.
            </p>
          )}
          {search.data?.results.map((hit) => (
            <KnowledgeHitCard key={hit.chunkId} hit={hit} />
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="font-mono text-sm font-medium text-muted-foreground">
            indexed chunks
            {chunkPage.data ? (
              <span className="ml-2 text-foreground/60">({chunkPage.data.total})</span>
            ) : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {stats && stats.categories.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {stats.categories.slice(0, 12).map((category) => (
                <button
                  key={category.type}
                  type="button"
                  onClick={() => toggleType(category.type)}
                  className={cn(
                    "rounded-full border px-3 py-1 font-mono text-xs transition-colors",
                    activeType === category.type
                      ? "border-primary text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground",
                  )}
                >
                  {CHUNK_TYPE_LABEL[category.type] ?? category.type}
                  <span className="ml-1.5 text-muted-foreground/60">{category.count}</span>
                </button>
              ))}
            </div>
          )}

          {chunkPage.isLoading ? (
            <div className="flex items-center gap-2 font-mono text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              loading chunks...
            </div>
          ) : chunkPage.data && chunkPage.data.items.length === 0 ? (
            <p className="font-mono text-xs text-muted-foreground">
              no chunks to show -- analysis may still be indexing this repository.
            </p>
          ) : (
            <div className="flex flex-col divide-y divide-border">
              {chunkPage.data?.items.map((item) => (
                <div key={item.chunkId} className="flex items-center gap-2 py-1.5 font-mono text-xs">
                  <Badge variant="outline" className="shrink-0">
                    {CHUNK_TYPE_LABEL[item.type] ?? item.type}
                  </Badge>
                  <span className="truncate text-foreground">{item.title}</span>
                  <span className="ml-auto shrink-0 text-muted-foreground/60">
                    {item.confidence > 0 ? `${Math.round(item.confidence * 100)}%` : ""}
                  </span>
                </div>
              ))}
            </div>
          )}

          {chunkPage.data && chunkPage.data.total > chunkPage.data.pageSize && (
            <div className="flex items-center justify-end gap-2 font-mono text-xs text-muted-foreground">
              <Button
                variant="ghost"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="gap-1"
              >
                <ChevronLeft className="h-3.5 w-3.5" /> prev
              </Button>
              <span>
                page {page} of {Math.max(1, Math.ceil(chunkPage.data.total / chunkPage.data.pageSize))}
              </span>
              <Button
                variant="ghost"
                size="sm"
                disabled={page >= Math.ceil(chunkPage.data.total / chunkPage.data.pageSize)}
                onClick={() => setPage((p) => p + 1)}
                className="gap-1"
              >
                next <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export function RepositoryPage() {
  const { id } = useParams<{ id: string }>();
  const { data: repository, isLoading: repoLoading } = useRepository(id);
  const knowledgeReady = repository?.status === "ready";

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const chat = useRepositoryChat(id);

  async function handleAsk(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setQuestion("");

    try {
      const response = await chat.mutateAsync(trimmed);
      setMessages((prev) => [...prev, { role: "assistant", content: response.answer }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            repository?.status === "ready"
              ? "no answer -- something went wrong reaching the model."
              : "no answer -- this repository hasn't finished analyzing yet.",
        },
      ]);
    }
  }

  if (repoLoading || !repository) {
    return (
      <div className="flex items-center gap-2 font-mono text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        loading repository...
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <h1 className="font-mono text-lg font-semibold text-foreground">
            {repository.sourceUrl?.replace(/^https?:\/\/(www\.)?/, "") ?? repository.uploadFilename}
          </h1>
          <StatusPill status={repository.status} />
        </div>
        {repository.sourceUrl && (
          <a
            href={repository.sourceUrl}
            target="_blank"
            rel="noreferrer"
            className="flex w-fit items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground"
          >
            {repository.sourceUrl}
            <ExternalLink className="h-3 w-3" />
          </a>
        )}
      </div>

      {repository.status === "failed" ? (
        <Card>
          <CardHeader>
            <CardTitle className="font-mono text-sm font-medium text-destructive">
              analysis failed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              {repository.lastError
                ? `Failed during "${repository.lastErrorStage}": ${repository.lastError}`
                : `Something went wrong analyzing this repository -- check the backend logs for repository ${repository.id}. Common causes: an invalid or private URL without a GitHub token configured, or a malformed zip upload.`}
            </p>
          </CardContent>
        </Card>
      ) : !knowledgeReady ? (
        <ProgressPanel id={repository.id} />
      ) : (
        <>
          <AnalysisOverview id={repository.id} />
          <KnowledgeExplorer id={repository.id} />
        </>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="font-mono text-sm font-medium text-muted-foreground">
            ask about this repository
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex max-h-[32rem] flex-col gap-3 overflow-y-auto">
            {messages.length === 0 && (
              <p className="font-mono text-xs text-muted-foreground">
                no messages yet -- ask something below.
              </p>
            )}
            {messages.map((message, index) =>
              message.role === "user" ? (
                <p key={index} className="font-mono text-sm leading-relaxed">
                  <span className="text-muted-foreground">you ›</span>{" "}
                  <span className="text-foreground">{message.content}</span>
                </p>
              ) : (
                <div key={index} className="font-mono text-sm leading-relaxed">
                  <span className="text-primary">repomind ›</span>
                  <div className="mt-1 text-foreground">
                    <Markdown content={message.content} />
                  </div>
                </div>
              ),
            )}
          </div>
          <form onSubmit={handleAsk} className="flex items-center gap-3 rounded-lg border border-border bg-background px-4 py-2.5 focus-within:ring-1 focus-within:ring-ring">
            <span className="font-mono text-primary">&gt;</span>
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="what are the main dependencies?"
              className="flex-1 bg-transparent font-mono text-sm placeholder:text-muted-foreground focus:outline-none"
            />
            <Button type="submit" size="sm" disabled={chat.isPending} className="gap-1.5">
              {chat.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ArrowRight className="h-3.5 w-3.5" />}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
