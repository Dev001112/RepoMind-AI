import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Loader2, UploadCloud } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useSubmitRepository, useUploadRepository } from "@/hooks/useRepositories";

const STAGES = [
  {
    step: "01",
    title: "Clone & scan",
    body: "Pulls the repo (or your zip) and walks the tree -- languages, package managers, Docker.",
  },
  {
    step: "02",
    title: "Detect & parse",
    body: "Deterministic checks for GPU/CUDA needs, frameworks, dependencies -- not the LLM's guess.",
  },
  {
    step: "03",
    title: "Ask anything",
    body: "Chat against the parsed source once it's embedded -- install steps, architecture, gaps.",
  },
];

export function HomePage() {
  const [mode, setMode] = useState<"url" | "upload">("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const navigate = useNavigate();
  const submitRepository = useSubmitRepository();
  const uploadRepository = useUploadRepository();

  const isPending = submitRepository.isPending || uploadRepository.isPending;
  const isError = submitRepository.isError || uploadRepository.isError;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mode === "url") {
      if (!url.trim()) return;
      const repo = await submitRepository.mutateAsync(url.trim());
      navigate(`/repositories/${repo.id}`);
    } else {
      if (!file) return;
      const repo = await uploadRepository.mutateAsync(file);
      navigate(`/repositories/${repo.id}`);
    }
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-16">
      <div className="flex flex-col gap-6">
        <div className="text-center">
          <p className="font-mono text-xs text-primary">// repository intelligence</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
            Understand a repo
            <br />
            before you depend on it.
          </h1>
          <p className="mx-auto mt-4 max-w-md text-sm text-muted-foreground">
            Drop in a GitHub URL or a zip. Get languages, frameworks, GPU/CUDA needs, install
            steps, and a chat to ask what the README left out.
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex gap-1 self-center rounded-md border border-border p-1 font-mono text-xs">
            <button
              type="button"
              onClick={() => setMode("url")}
              className={cn(
                "rounded px-3 py-1.5 transition-colors",
                mode === "url"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              github url
            </button>
            <button
              type="button"
              onClick={() => setMode("upload")}
              className={cn(
                "rounded px-3 py-1.5 transition-colors",
                mode === "upload"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              upload zip
            </button>
          </div>

          <form onSubmit={handleSubmit}>
            {mode === "url" ? (
              <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 shadow-sm focus-within:ring-1 focus-within:ring-ring">
                <span
                  className={cn(
                    "font-mono text-primary",
                    url.length === 0 && "animate-blink",
                  )}
                >
                  &gt;
                </span>
                <input
                  type="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="github.com/owner/repo"
                  required
                  className="flex-1 bg-transparent font-mono text-sm text-foreground placeholder:text-muted-foreground focus:outline-none"
                />
                <Button type="submit" size="sm" disabled={isPending} className="gap-1.5">
                  {isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <>
                      Analyze
                      <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </Button>
              </div>
            ) : (
              <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3 shadow-sm">
                <UploadCloud className="h-4 w-4 shrink-0 text-primary" />
                <label className="flex-1 cursor-pointer font-mono text-sm text-muted-foreground">
                  {file ? file.name : "choose a .zip file"}
                  <input
                    type="file"
                    accept=".zip"
                    onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                    className="hidden"
                    required
                  />
                </label>
                <Button type="submit" size="sm" disabled={!file || isPending} className="gap-1.5">
                  {isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <>
                      Analyze
                      <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </Button>
              </div>
            )}
          </form>
          {isError && (
            <p className="text-center font-mono text-xs text-destructive">
              couldn't submit that repository -- try again.
            </p>
          )}
        </div>
      </div>

      <div className="grid gap-6 sm:grid-cols-3">
        {STAGES.map((stage) => (
          <div key={stage.step} className="flex flex-col gap-1.5">
            <span className="font-mono text-xs text-primary">{stage.step}</span>
            <h3 className="text-sm font-medium text-foreground">{stage.title}</h3>
            <p className="text-sm leading-relaxed text-muted-foreground">{stage.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
