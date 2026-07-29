"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { ChatInput } from "@/components/ChatInput";
import { ChatMessage } from "@/components/ChatMessage";
import { CompassGauge } from "@/components/CompassGauge";
import { ListingCard } from "@/components/ListingCard";
import { ThemeToggle } from "@/components/ThemeToggle";
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

  const latestRecommendations = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const rec = messages[i].recommendations;
      if (rec && rec.length > 0) return rec;
    }
    return null;
  }, [messages]);

  return (
    <div className="min-h-dvh bg-paper">
      {/* Top nav */}
      <header className="flex items-center justify-between border-b border-rule px-4 py-4 sm:px-8">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full border border-rule-bright text-brass">
            ✎
          </span>
          <span className="font-display text-xl text-ink">Home Compass</span>
        </div>
        <div className="flex items-center gap-3">
          <ThemeToggle />
          <button className="rounded-md bg-brass-deep px-4 py-2 font-mono text-xs uppercase tracking-wide text-cream hover:bg-brass">
            Start a search
          </button>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-5xl px-4 pb-8 pt-12 sm:px-8">
        <p className="font-mono text-xs uppercase tracking-widest text-brass">AI real estate agent</p>
        <h1 className="mt-3 max-w-3xl font-display text-4xl leading-[1.1] text-ink sm:text-5xl">
          Tell it what you need.
        </h1>
      </section>

      {/* Two-panel workspace */}
      <section className="mx-auto grid max-w-5xl grid-cols-1 gap-4 px-4 pb-12 sm:px-8 lg:grid-cols-2">
        {/* Left: chat thread */}
        <div className="flex h-[640px] flex-col rounded-lg border border-rule bg-card">
          <div className="flex items-center justify-between border-b border-rule px-5 py-3">
            <span className="font-mono text-xs uppercase tracking-wide text-muted">Compass agent</span>
            {threadId && (
              <span className="font-mono text-xs text-muted">Thread #{threadId.slice(0, 5).toUpperCase()}</span>
            )}
          </div>

          <div ref={transcriptRef} className="transcript flex-1 overflow-y-auto px-5 py-5">
            <div className="flex flex-col gap-6">
              {!hasStarted && (
                <p className="max-w-sm text-sm text-muted">
                  Tell the agent what you&apos;re looking for. It&apos;ll ask what it needs to know
                  before searching — and show you exactly how confident it is at every step.
                </p>
              )}

              {messages.map((message) => (
                <ChatMessage key={message.id} message={message} />
              ))}

              {error && (
                <p className="rounded-lg border border-danger/40 bg-danger/5 px-4 py-3 text-sm text-danger">
                  {error}
                </p>
              )}
            </div>
          </div>

          <div className="border-t border-rule px-5 py-4">
            <ChatInput onSend={handleSend} disabled={isStreaming} />
          </div>
        </div>

        {/* Right: matches + confidence */}
        <div className="flex h-[640px] flex-col rounded-lg border border-rule bg-card">
          <div className="flex items-center justify-between border-b border-rule px-5 py-3">
            <span className="font-mono text-xs uppercase tracking-wide text-muted">Your matches</span>
            <button
              onClick={() => {
                setMessages([]);
                setThreadId(null);
                setLatestConfidence(null);
                setError(null);
              }}
              className="rounded-md border border-rule-bright px-3 py-1 font-mono text-xs uppercase tracking-wide text-ink-dim hover:border-ink hover:text-ink"
            >
              ↺ Replay
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-5">
            <CompassGauge score={latestConfidence ?? 0} variant="full" label="Needs understood" />
            <p className="mt-3 text-xs leading-relaxed text-muted">
              This reflects how well Compass understands what you&apos;re looking for — budget,
              location, must-haves, timeline. It&apos;s not a score for the listings below; see the
              match badge on each card for that.
            </p>

            {latestRecommendations ? (
              <>
                <div className="mt-6 flex items-baseline justify-between">
                  <span className="font-mono text-xs uppercase tracking-wide text-muted">
                    Top matches — {latestRecommendations.length} found
                  </span>
                  <span className="font-mono text-xs uppercase tracking-wide text-muted">Sorted by fit</span>
                </div>
                <div className="mt-3 flex flex-col gap-3">
                  {latestRecommendations.map((rec) => (
                    <ListingCard key={rec.listing.id} recommendation={rec} />
                  ))}
                </div>
              </>
            ) : (
              <p className="mt-8 text-sm text-muted">
                Matches will appear here once Compass is confident it understands what you&apos;re
                looking for.
              </p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}