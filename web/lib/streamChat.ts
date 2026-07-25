import type { ChatStreamEvent } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080";

/**
 * Streams a chat turn from POST /chat. EventSource only supports GET, so
 * this parses the "data: {...}\n\n" SSE wire format by hand from a plain
 * fetch() response body reader — the standard pattern for POST-based SSE.
 */
export async function* streamChat(
  message: string,
  threadId: string | null,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`Chat request failed: ${response.status} ${response.statusText}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line; a frame may arrive split
    // across multiple chunks, so only split on complete "\n\n" boundaries
    // and keep any trailing partial frame in the buffer for next time.
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      const json = line.slice("data:".length).trim();
      if (!json) continue;
      yield JSON.parse(json) as ChatStreamEvent;
    }
  }
}
