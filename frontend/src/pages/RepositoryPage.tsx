import { useState, type FormEvent, type ReactNode } from "react";
import { useParams } from "react-router-dom";
import { ArrowRight, ExternalLink, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Markdown } from "@/components/Markdown";
import { cn } from "@/lib/utils";
import {
  useRepository,
  useRepositoryChat,
  useRepositoryKnowledge,
} from "@/hooks/useRepositories";
import type { ChatMessage, RepositoryStatus } from "@/types/repository";

const STAGES: { status: RepositoryStatus; label: string }[] = [
  { status: "cloning", label: "clone repository" },
  { status: "scanning", label: "detect languages/frameworks/deps/docker/cuda/cicd/apis, parse source" },
  { status: "knowledge_built", label: "assemble repository knowledge" },
  { status: "embedding", label: "generate embeddings" },
];

const STATUS_ORDER: RepositoryStatus[] = [
  "pending",
  "cloning",
  "scanning",
  "knowledge_built",
  "embedding",
  "ready",
];

function stageState(stage: RepositoryStatus, current: RepositoryStatus): "done" | "active" | "queued" {
  const stageIdx = STATUS_ORDER.indexOf(stage);
  const currentIdx = STATUS_ORDER.indexOf(current);
  if (currentIdx > stageIdx) return "done";
  if (currentIdx === stageIdx) return "active";
  return "queued";
}

const STAGE_DOT_STYLE = {
  done: "bg-success",
  active: "bg-primary animate-pulse",
  queued: "bg-muted-foreground/40",
};

const STATUS_STYLE: Record<RepositoryStatus, string> = {
  pending: "bg-primary animate-pulse",
  cloning: "bg-primary animate-pulse",
  scanning: "bg-primary animate-pulse",
  knowledge_built: "bg-primary animate-pulse",
  embedding: "bg-primary animate-pulse",
  ready: "bg-success",
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

export function RepositoryPage() {
  const { id } = useParams<{ id: string }>();
  const { data: repository, isLoading: repoLoading } = useRepository(id);
  const knowledgeReady = repository?.status === "ready";
  const {
    data: knowledge,
    isLoading: knowledgeLoading,
    isError: knowledgeError,
  } = useRepositoryKnowledge(id, knowledgeReady);

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
            {knowledge?.metadata.name ?? repository.sourceUrl?.replace(/^https?:\/\/(www\.)?/, "") ?? repository.uploadFilename}
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
        {knowledge?.metadata.description && (
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{knowledge.metadata.description}</p>
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
        <Card>
          <CardHeader>
            <CardTitle className="font-mono text-sm font-medium text-muted-foreground">
              analysis pipeline
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {STAGES.map((stage) => {
              const state = stageState(stage.status, repository.status);
              return (
                <div key={stage.status} className="flex items-center gap-2 font-mono text-xs">
                  <span className={cn("h-1.5 w-1.5 rounded-full", STAGE_DOT_STYLE[state])} />
                  <span className="text-muted-foreground">{stage.label}</span>
                  <span className="ml-auto text-muted-foreground/60">{state}</span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      ) : knowledgeLoading ? (
        <div className="flex items-center gap-2 font-mono text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          loading report...
        </div>
      ) : knowledgeError || !knowledge ? (
        <Card>
          <CardHeader>
            <CardTitle className="font-mono text-sm font-medium text-destructive">
              report unavailable
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Analysis finished, but the knowledge report couldn't be loaded. Try refreshing --
              if that doesn't help, check the backend logs for repository {repository.id}.
            </p>
          </CardContent>
        </Card>
      ) : (
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
              {knowledge.languages.languages.length === 0 && knowledge.frameworks.frameworks.length === 0 && (
                <p className="text-sm text-muted-foreground">None detected.</p>
              )}
            </div>
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
