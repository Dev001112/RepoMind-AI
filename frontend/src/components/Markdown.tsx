import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-0.5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-0.5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="text-primary underline underline-offset-2 hover:text-primary/80"
    >
      {children}
    </a>
  ),
  h1: ({ children }) => <p className="mb-1 mt-2 font-semibold text-foreground first:mt-0">{children}</p>,
  h2: ({ children }) => <p className="mb-1 mt-2 font-semibold text-foreground first:mt-0">{children}</p>,
  h3: ({ children }) => <p className="mb-1 mt-2 font-semibold text-foreground first:mt-0">{children}</p>,
  code: ({ className, children }) =>
    className ? (
      // fenced block (has a language- className) -- `pre` below owns the box styling
      <code className={className}>{children}</code>
    ) : (
      <code className="rounded bg-background px-1 py-0.5 text-xs">{children}</code>
    ),
  pre: ({ children }) => (
    <pre className="mb-2 overflow-x-auto rounded-md bg-background p-3 text-xs leading-relaxed last:mb-0">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="mb-2 overflow-x-auto last:mb-0">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead>{children}</thead>,
  th: ({ children }) => (
    <th className="border border-border bg-background px-2 py-1 text-left font-medium text-muted-foreground">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="border border-border px-2 py-1 align-top">{children}</td>,
  hr: () => <hr className="my-2 border-border" />,
};

export function Markdown({ content }: { content: string }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  );
}
