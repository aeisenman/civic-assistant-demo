/**
 * Assistant replies rendered as paragraphs, bullet/numbered lists, pipe tables,
 * inline bold, inline code and http(s) links — nothing else, never as raw HTML.
 * Rendered by the chat page. Depends on nothing: a markdown library would be a
 * dependency and an XSS surface for the handful of features the model uses.
 */

const BULLET = /^\s*[-*•]\s+/;
const ORDERED = /^\s*\d+[.)]\s+/;
// Bold, code, then links. The link arm is last so `**[a](b)**` still bolds.
const INLINE = /\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]\n]+)\]\(([^)\s]+)\)/g;
// A table row is a line with at least one pipe that is not the whole line.
const TABLE_ROW = /\|/;
// The line under the header: only dashes, colons, pipes and spaces.
const TABLE_SEPARATOR = /^\s*\|?[\s:-]*-[\s:|-]*\|?\s*$/;

/**
 * True only for absolute http(s) URLs.
 *
 * Everything else — `javascript:`, `data:`, a bare `mailto:`, a relative path —
 * renders as plain text. React already escapes the text, but an <a href> is the
 * one place a string becomes executable, so the scheme is allow-listed rather
 * than blocked. `new URL` is used instead of a regex because it is the browser's
 * own parser and does not get fooled by `java\nscript:`.
 */
function isSafeUrl(url: string): boolean {
  try {
    const scheme = new URL(url).protocol;
    return scheme === "http:" || scheme === "https:";
  } catch {
    return false;
  }
}

/** Split one table row into cells, dropping the leading/trailing pipe. */
function cells(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((c) => c.trim());
}

/**
 * A markdown pipe table, or null when this block is not one.
 *
 * The model reaches for a table on any "compare X and Y" question, and before
 * this the resident saw raw `| fee | days |` rows (red-team finding 14). The
 * shape has to be exact — header, separator, at least one body row — so an
 * ordinary sentence containing a pipe is still a paragraph.
 */
function parseTable(lines: string[]): { header: string[]; rows: string[][] } | null {
  if (lines.length < 3) return null;
  if (!TABLE_ROW.test(lines[0]) || !TABLE_SEPARATOR.test(lines[1])) return null;
  const header = cells(lines[0]);
  if (header.length < 2) return null;
  const rows = lines.slice(2).map(cells);
  if (rows.some((r) => r.length < 2)) return null;
  return { header, rows };
}

/** Bold, code and safe links inside one line of text. */
function inline(text: string, key: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let last = 0;
  let i = 0;
  INLINE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = INLINE.exec(text)) !== null) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1] !== undefined) {
      out.push(
        <strong key={`${key}-b${i}`} className="font-semibold">
          {m[1]}
        </strong>,
      );
    } else if (m[2] !== undefined) {
      out.push(
        <code
          key={`${key}-c${i}`}
          className="rounded bg-black/5 px-1 py-0.5 font-mono text-[13px]"
        >
          {m[2]}
        </code>,
      );
    } else if (isSafeUrl(m[4])) {
      out.push(
        <a
          key={`${key}-a${i}`}
          href={m[4]}
          target="_blank"
          rel="noopener noreferrer"
          className="underline underline-offset-2 hover:no-underline"
        >
          {m[3]}
        </a>,
      );
    } else {
      // Not a URL we will link to: show exactly what the model wrote.
      out.push(m[0]);
    }
    last = m.index + m[0].length;
    i += 1;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export default function MarkdownLite({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/).filter((p) => p.trim().length > 0);

  return (
    <>
      {blocks.map((block, i) => {
        const lines = block.split("\n").filter((l) => l.trim().length > 0);
        const spacing = i > 0 ? "mt-3" : undefined;

        const table = parseTable(lines);
        if (table) {
          return (
            // Fee tables are wider than a chat bubble on a phone, so the table
            // scrolls inside the bubble rather than stretching the page.
            <div key={i} className={`overflow-x-auto ${spacing ?? ""}`}>
              <table className="w-full border-collapse text-left text-[13px]">
                <thead>
                  <tr>
                    {table.header.map((cell, j) => (
                      <th
                        key={j}
                        className="border-b border-black/10 px-2 py-1 font-semibold"
                      >
                        {inline(cell, `${i}-h${j}`)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {table.rows.map((row, j) => (
                    <tr key={j}>
                      {row.map((cell, k) => (
                        <td key={k} className="border-b border-black/5 px-2 py-1 align-top">
                          {inline(cell, `${i}-r${j}-${k}`)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        if (lines.length > 0 && lines.every((l) => BULLET.test(l))) {
          return (
            <ul key={i} className={`list-disc space-y-1 pl-5 ${spacing ?? ""}`}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(BULLET, ""), `${i}-${j}`)}</li>
              ))}
            </ul>
          );
        }
        if (lines.length > 0 && lines.every((l) => ORDERED.test(l))) {
          return (
            <ol key={i} className={`list-decimal space-y-1 pl-5 ${spacing ?? ""}`}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(ORDERED, ""), `${i}-${j}`)}</li>
              ))}
            </ol>
          );
        }
        return (
          <p key={i} className={spacing}>
            {lines.map((line, j) => (
              <span key={j}>
                {j > 0 ? <br /> : null}
                {inline(line, `${i}-${j}`)}
              </span>
            ))}
          </p>
        );
      })}
    </>
  );
}
