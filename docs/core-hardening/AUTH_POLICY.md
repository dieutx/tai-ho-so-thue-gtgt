# Authentication response contracts — CORE-19

Both adapters use AuthOutcome with eight outcomes. Only explicit CAPTCHA rejection
calls solver.rejected and consumes another authentication attempt. Invalid credentials,
maintenance, access verification, OTP/SSO and unknown responses stop. Numeric DVC
error codes are not guessed. Script validators, hidden fields and inline hidden
elements are excluded from visible error evidence. HTTP 403 alone is unknown.

Authenticated operations recognize HTTP 401, an actual login form, a login final URL
or a login Location redirect as expired. Desktop reauthenticates at most once for
SessionExpired; an unknown operation page does not cause reauthentication. DVC and
legacy cookies remain isolated. Legacy retries use the latest returned login form;
DVC retries fetch the current CSRF token and a fresh challenge. Cancellation propagates.

Transport also terminates recognized maintenance/verification/interactive responses
before callers retry a business request. It does not retry arbitrary 5xx responses.
Error messages contain fixed AUTH_* codes; no response body or session identifier
is included. CLI logs the same code that desktop returns in JobResult.error_code,
including failures before pipeline execution.

The synthetic matrix in tests/test_auth_outcomes.py and fixtures/auth/manifest.json
covers both adapters, all outcomes, 200/401/403/503 and login redirects. Descriptive
JSON codes are fixture contracts, not claims of live portal support. All validation
is offline; no account or live portal was used.
