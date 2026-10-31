import { Fragment } from "react";

/** Renders a translated headline, setting the part wrapped in *asterisks* in italic. */
export default function Display({ text }: { text: string }) {
  return (
    <>
      {text
        .split(/(\*[^*]+\*)/)
        .map((part, i) =>
          part.startsWith("*") && part.endsWith("*") ? (
            <em key={i}>{part.slice(1, -1)}</em>
          ) : (
            <Fragment key={i}>{part}</Fragment>
          ),
        )}
    </>
  );
}
