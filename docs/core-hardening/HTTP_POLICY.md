# HTTP origin, response and run limits

CORE-14 / CORE-15. Requests use reviewed HTTPS origins for DVC and legacy eTax.
Userinfo, alternate ports, downgrade and lookalike/external origins are rejected.
HTML form actions and DSE operation URLs are validated at the transport boundary.
Every redirect is checked before another request is sent. Redirects stay within
the initiating origin, even between two otherwise reviewed portal origins; new
SSO/domain flows need adapter review. 301/302 POST and 303 switch to GET without
body/content headers; 307/308 preserve the method. Six hops stop cycles. Desktop
source routing uses parsed origins.

Responses are streamed with automatic decoding and checked after every chunk.
Limits: page 8 MiB, CAPTCHA 2 MiB, downloads 128 MiB, generic DSE operations
64 MiB. Content-Length can reject early but never replaces the actual decoded
byte count. A temporary spool rolls to disk above 1 MiB and is always closed.
The bounded final bytes remain available through the existing Response API so
download validators and atomic stores keep their contracts. No parallel DSE
downloads are introduced.

RunHooks carries one shared RunBudget: 30 minutes, 10,000 requests, 1 GiB decoded
traffic, 10,000 logical pages and 20 authentication attempts by default. Retries
and redirects count against requests; the three pipelines count logical pages.
Desktop may replace hooks at each job, creating a fresh budget for that action.
Tests can inject a monotonic clock and smaller limits. The deadline clamps socket
timeouts and is checked between chunks/requests/retry sleeps. It cannot interrupt
a socket earlier than its timeout, or interrupt an atomic file commit.

GET/HEAD/OPTIONS can retry HTTP 429, except stateful legacy Request operations.
POST requires an explicit retry-safe OperationPolicy. Disconnects, schema and
credential failures are not transport retries. Retry-After accepts finite seconds
or HTTP-date, rejects NaN/inf/negative values to the default, and caps pauses at
60 seconds. Higher-level bounded login/search retries remain within the shared
run limits. Existing 503 responses return to the caller without an automatic
retry.

Compatibility: public get/post still return a fully read Response. Custom
unreviewed base URLs no longer work with the default policy. Local proxy tests
inject a test-only policy; no CLI bypass exists. No file or catalog migration is
needed; rollback is the preceding source revision. Contract tests are synthetic
stream/session stubs plus the existing local proxy server, without real tax
credentials or portal calls.
