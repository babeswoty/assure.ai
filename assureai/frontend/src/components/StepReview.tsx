import { useState } from "react";
import type { StepReviewState } from "@/types";
import { ErrorBanner } from "@/components/Shared";

export function StepReview({
  label,
  review,
  canReview,
  busy,
  error,
  onApprove,
  onRequestChanges,
}: {
  label: string;
  review?: StepReviewState;
  canReview: boolean;
  busy: boolean;
  error?: string | null;
  onApprove: () => void;
  onRequestChanges: (comment: string) => void;
}) {
  const [requesting, setRequesting] = useState(false);
  const [comment, setComment] = useState("");
  const approved = review?.status === "approved";

  return (
    <div className="mt-4 border-t border-ink-200 pt-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-500">Human review</span>
        <button className="btn-primary" disabled={!canReview || busy || approved} onClick={onApprove}>
          {busy ? "Submitting..." : approved ? `${label} Approved` : `Approve ${label}`}
        </button>
        <button
          className="btn-secondary"
          aria-label={`Request changes to ${label}`}
          disabled={!canReview || busy}
          onClick={() => setRequesting((r) => !r)}
        >
          Request Changes
        </button>
      </div>
      {requesting && (
        <div className="flex gap-2">
          <input
            className="input flex-1"
            aria-label={`Comment for ${label}`}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="What needs to change?"
          />
          <button
            className="btn-secondary"
            aria-label={`Send change request for ${label}`}
            disabled={busy}
            onClick={() => {
              onRequestChanges(comment);
              setRequesting(false);
              setComment("");
            }}
          >
            Send
          </button>
        </div>
      )}
      <ErrorBanner message={error ?? null} />
      {approved && (
        <p className="text-xs text-ink-500">
          Approved by {review?.reviewer}. The next step is now unlocked.
        </p>
      )}
      {review?.status === "changes_requested" && (
        <p className="text-xs text-amber-800">
          Changes requested by {review.reviewer}
          {review.comment ? `: ${review.comment}` : "."} Edit or re-run this step, then approve it to continue.
        </p>
      )}
    </div>
  );
}
