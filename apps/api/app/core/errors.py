"""Standardized safe error responses.

Every response body in this API already nests its error payload under a
`detail` key -- that is plain FastAPI convention (`raise
HTTPException(detail=...)`), used throughout this codebase for both
generic errors and deliberate domain payloads (e.g. `RuntimeResult`,
`ApprovalActionResult` for 404/409s that the frontend already parses).
This module does not change that shape. What it adds:

- A `{"code", "message", "request_id"}` envelope for the *generic* error
  paths that had no established contract before Milestone 10: auth
  failures, rate limiting, request validation errors, and any unhandled
  exception. Those are recognized by already carrying "code" and
  "message" keys (set by app.core.security / app.core.rate_limit) or by
  being one of the two exception types handled globally below.
- Never touches the pre-existing domain-specific detail payloads
  (RuntimeResult/ApprovalActionResult dumps, plain string details like
  "Execution not found") -- those are not "raw internals", they are an
  already-reviewed, already-relied-upon safe contract, and rewriting
  their shape would break the frontend that already parses them.
- Guarantees no stack trace, SQL, or raw exception text ever reaches a
  client: any exception that is not an HTTPException/RequestValidationError
  is logged in full server-side (with the request id for correlation) and
  answered with a generic 500 body.
"""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.request_context import get_request_id

logger = logging.getLogger("safeops")


def _is_generic_error_detail(detail: Any) -> bool:
    return isinstance(detail, dict) and "code" in detail and "message" in detail


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if _is_generic_error_detail(detail):
            detail = {**detail, "request_id": get_request_id()}
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Never echo back pydantic's raw error internals (which can quote
        # submitted values) to the client -- log them server-side instead,
        # correlated by request id.
        logger.warning("request_validation_error", extra={"errors": exc.errors()})
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request body failed validation.",
                    "request_id": get_request_id(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception")
        return JSONResponse(
            status_code=500,
            content={
                "detail": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred.",
                    "request_id": get_request_id(),
                }
            },
        )
