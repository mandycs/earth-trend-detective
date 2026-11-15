export interface SseMessage {
  event: string;
  data: string;
}

/**
 * Incremental Server-Sent Events parser (same field rules as
 * backend/scripts/detective_run.py:parse_sse). A trailing "\r" is held until
 * the next chunk so a "\r\n" split across chunks is one line end.
 */
export function createSseParser(onMessage: (m: SseMessage) => void): {
  push(chunk: string): void;
  end(): void;
} {
  let buffer = "";
  let name = "message";
  let data: string[] = [];

  function line(raw: string): void {
    if (raw === "") {
      if (data.length > 0) onMessage({ event: name, data: data.join("\n") });
      name = "message";
      data = [];
      return;
    }
    if (raw.startsWith(":")) return;
    const i = raw.indexOf(":");
    const field = i === -1 ? raw : raw.slice(0, i);
    let value = i === -1 ? "" : raw.slice(i + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") name = value;
    else if (field === "data") data.push(value);
  }

  function drain(final: boolean): void {
    let start = 0;
    for (let i = 0; i < buffer.length; i++) {
      const c = buffer[i];
      if (c === "\n") {
        line(buffer.slice(start, i));
        start = i + 1;
      } else if (c === "\r") {
        if (i === buffer.length - 1 && !final) break; // may be half of \r\n
        line(buffer.slice(start, i));
        if (buffer[i + 1] === "\n") i++;
        start = i + 1;
      }
    }
    buffer = buffer.slice(start);
  }

  return {
    push(chunk: string): void {
      buffer += chunk;
      drain(false);
    },
    end(): void {
      drain(true);
      if (buffer !== "") line(buffer);
      buffer = "";
      if (data.length > 0) onMessage({ event: name, data: data.join("\n") });
      name = "message";
      data = [];
    },
  };
}
