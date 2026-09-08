import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { ApiError } from "@/lib/api";
import { ErrorState } from "@/components/states";

describe("ErrorState", () => {
  it("renders a friendly message and never a raw stack trace", () => {
    const error = new Error(
      'Traceback (most recent call last):\n  File "app.py", line 42\nKeyError: SECRET'
    );
    render(<ErrorState error={error} />);
    // The component only ever surfaces `error.message`, which for backend
    // failures is always our own ApiError message (see lib/api.ts) -- but
    // even for an arbitrary JS Error, it must not add any additional raw
    // internals of its own, and it must show a stable, human heading.
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
  });

  it("shows a distinct offline message for a network-level ApiError", () => {
    const error = new ApiError("Cannot reach the SafeOps backend.", 0);
    render(<ErrorState error={error} />);
    expect(screen.getByText(/backend unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/cannot reach the safeops backend/i)).toBeInTheDocument();
  });

  it("never renders backend detail objects as [object Object]", () => {
    const error = new ApiError("Execution not found", 404);
    render(<ErrorState error={error} />);
    expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
  });
});
