"use client";

import { useEffect, useRef, useState } from "react";
import { ChatInput } from "@/components/ChatInput";
import { ChatMessage } from "@/components/ChatMessage";
import { CompassGauge } from "@/components/CompassGauge";
import { streamChat } from "@/lib/streamChat";
import type { ChatMessage as ChatMessageType } from "@/lib/types";

function newId(): string {
  return Math.random().toString(36).slice(2);
}

export default function Home() {
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [latestConfidence, setLatestConfidence] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function handleSend(text: string) {
    setError(null);
    const userMessage: ChatMessageType = { id: newId(), role: "user", content: text };
    const agentMessageId = newId();
    const agentMessage: ChatMessageType = { id: agentMessageId, role: "agent", content: "" };

    setMessages((prev) => [...prev, userMessage, agentMessage]);
    setIsStreaming(true);

    try {
      for await (const event of streamChat(text, threadId)) {
        if ("thread_id" in event) {
          setThreadId(event.thread_id);
        } else if ("status" in event) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === agentMessageId ? { ...m, statusLog: [...(m.statusLog ?? []), event.status] } : m,
            ),
          );
        } else if ("token" in event) {
          setMessages((prev) =>
            prev.map((m) => (m.id === agentMessageId ? { ...m, content: m.content + event.token } : m)),
          );
        } else if ("replace" in event) {
          // Compliance guardrail revised the draft after it streamed —
          // swap the bubble's full text for the compliant version.
          setMessages((prev) =>
            prev.map((m) => (m.id === agentMessageId ? { ...m, content: event.replace } : m)),
          );
        } else if ("done" in event) {
          setLatestConfidence(event.confidence_score);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === agentMessageId
                ? {
                    ...m,
                    confidenceScore: event.confidence_score,
                    recommendations: event.recommendations,
                    answerConfidence: event.answer_confidence ?? null,
                  }
                : m,
            ),
          );
        }
      }
    } catch {
      setError("Lost the connection to the agent. Check that the API is running and try again.");
    } finally {
      setIsStreaming(false);
    }
  }

  const hasStarted = messages.length > 0;

  return (
    <div className="flex h-dvh flex-col bg-ink">
      <header className="flex items-center justify-between border-b border-rule px-4 py-3 sm:px-6">
        <div>
          <h1 className="font-display text-xl sm:text-2xl text-parchment tracking-tight">Home Compass</h1>
          <p className="text-xs text-muted hidden sm:block">An agent that says how sure it is before it recommends anything.</p>
        </div>
        <CompassGauge score={latestConfidence ?? 0} />
      </header>

      <main ref={transcriptRef} className="transcript flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto flex max-w-3xl flex-col gap-6">
          {!hasStarted && (
            <div className="flex flex-col items-center gap-3 py-20 text-center">
              <div className="opacity-70">
                <CompassGauge score={0} size={72} />
              </div>
              <p className="max-w-sm text-muted">
                Tell the agent what you&apos;re looking for. It&apos;ll ask what it needs to know before
                searching — and show you exactly how confident it is at every step.
              </p>
            </div>
          )}

          {messages.map((message) => (
            <ChatMessage key={message.id} message={message} />
          ))}

          {error && (
            <p className="rounded-lg border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
              {error}
            </p>
          )}
        </div>
      </main>

      <footer className="border-t border-rule px-4 py-4 sm:px-6">
        <div className="mx-auto max-w-3xl">
          <ChatInput onSend={handleSend} disabled={isStreaming} />
        </div>
      </footer>
    </div>
  );
}
