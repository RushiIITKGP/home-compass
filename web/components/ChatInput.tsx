"use client";

import { useState, type KeyboardEvent } from "react";

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [value, setValue] = useState("");

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className="flex items-end gap-2 rounded-xl border border-rule bg-card p-2 focus-within:border-brass/60">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder="Tell the agent what you're looking for…"
        rows={1}
        className="flex-1 resize-none bg-transparent px-2 py-2 text-ink placeholder:text-muted focus:outline-none disabled:opacity-50"
      />
      <button
        onClick={submit}
        disabled={disabled || !value.trim()}
        className="shrink-0 rounded-lg bg-brass-deep px-4 py-2 font-mono text-xs uppercase tracking-wide text-cream transition-colors hover:bg-brass disabled:opacity-40 disabled:hover:bg-brass-deep"
      >
        Send
      </button>
    </div>
  );
}