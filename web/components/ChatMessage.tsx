import type { ChatMessage as ChatMessageType } from "@/lib/types";
import { AnswerConfidencePanel } from "./AnswerConfidencePanel";
import { CompassGauge } from "./CompassGauge";
import { StatusLog } from "./StatusLog";

interface ChatMessageProps {
  message: ChatMessageType;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";
  const hasContent = message.content.trim().length > 0;

  return (
    <div className={`flex flex-col ${isUser ? "items-end" : "items-start"} gap-2`}>
      {!isUser && message.statusLog && message.statusLog.length > 0 && (
        <div className="ml-0 sm:ml-4">
          <StatusLog entries={message.statusLog} />
        </div>
      )}

      {(isUser || hasContent) && (
        <div className="flex items-end gap-2 max-w-[85%] sm:max-w-[70%]">
          {!isUser && (
            <span className="mb-1 hidden sm:block h-2 w-2 shrink-0 rounded-full bg-brass" aria-hidden />
          )}
          <div
            className={
              isUser
                ? "rounded-2xl rounded-br-sm bg-user-bg px-4 py-2.5 text-user-fg"
                : "rounded-2xl rounded-bl-sm bg-card border border-rule px-4 py-2.5 text-ink"
            }
          >
            <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
          </div>
        </div>
      )}

      {!isUser && typeof message.confidenceScore === "number" && (
        <div className="ml-0 sm:ml-4 opacity-90">
          <CompassGauge score={message.confidenceScore} size={48} variant="compact" />
        </div>
      )}

      {/* Listings are shown in the side "Your matches" panel, not inline
          in the chat — the chat just carries the conversation. */}

      {!isUser && message.answerConfidence && (
        <div className="ml-0 sm:ml-4 w-full">
          <AnswerConfidencePanel confidence={message.answerConfidence} />
        </div>
      )}
    </div>
  );
}