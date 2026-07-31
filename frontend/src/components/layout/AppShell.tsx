import { Link, Outlet } from "react-router-dom";

export function AppShell() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border">
        <div className="container flex h-14 items-center justify-between">
          <Link to="/" className="flex items-center gap-1.5 font-mono text-sm font-semibold">
            <span className="text-primary">{">"}</span>
            <span>repomind</span>
            <span className="text-muted-foreground">_ai</span>
          </Link>
          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="font-mono text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            v0.1.0 · phase 1
          </a>
        </div>
      </header>
      <main className="container flex-1 py-10">
        <Outlet />
      </main>
      <footer className="border-t border-border py-4">
        <p className="container font-mono text-xs text-muted-foreground">
          repomind_ai reads repositories, it doesn't write code.
        </p>
      </footer>
    </div>
  );
}
