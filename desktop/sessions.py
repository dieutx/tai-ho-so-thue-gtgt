"""One in-memory account; a serialized ETAX DSE session; separate DVC cookies."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import timedelta
from threading import RLock
from typing import Any

from gdt_tax.auth_outcomes import AuthFailure, AuthOutcome, classify_response
from gdt_tax.constants import LEGACY_ETAX_ORIGIN, SOURCE_ETAX_LEGACY
from gdt_tax.errors import LegacyPageError
from gdt_tax.gnt.portal import GntPortal
from gdt_tax.http import HttpClient
from gdt_tax.identity import RecordKey, account_fingerprint
from gdt_tax.legacy_session import LegacySessionState, SessionExpired
from gdt_tax.ownership import prepare_output
from gdt_tax.portals import build_portals
from gdt_tax.portals.etax_legacy import EtaxLegacyPortal
from gdt_tax.proxy import parse_proxy
from gdt_tax.run_hooks import RunCancelled, RunHooks
from gdt_tax.tb.portal import TbPortal

from .services import JobResult, RunConfig, run_online


@dataclass
class AccountContext:
    username: str = ""
    password: str = field(default="", repr=False)
    version: int = 0
    state: str = "DISCONNECTED"

    def clear(self) -> None:
        self.username = self.password = ""
        self.version += 1
        self.state = "DISCONNECTED"


def is_auth_failure(response: Any) -> bool:
    return classify_response(response, 'ETAX_LEGACY', phase='operation', authenticated=True) == AuthOutcome.EXPIRED_SESSION


class SessionHttpClient(HttpClient):
    def __init__(self, *args, session_state: LegacySessionState, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.session_state = session_state
        self.authenticating = False

    def request(self, method: str, path: str, **kwargs):
        response = super().request(method, path, **kwargs)
        outcome = classify_response(response, 'ETAX_LEGACY', phase='operation',
                                    authenticated=self.session_state.authenticated)
        if outcome in {AuthOutcome.MAINTENANCE, AuthOutcome.INTERACTIVE_AUTH_REQUIRED,
                       AuthOutcome.INVALID_CREDENTIALS}:
            raise AuthFailure(outcome)
        if not self.authenticating and self.session_state.authenticated and is_auth_failure(response):
            self.session_state.clear()
            raise SessionExpired("Phiên ETAX hết hạn")
        return response


class RoutedHttpClient:
    """No cookie/CSRF crosses origins. Only used for explicit experimental DVC."""
    def __init__(self, legacy: Any, dvc: Any) -> None:
        self.legacy, self.dvc = legacy, dvc

    def request(self, method: str, path: str, **kwargs):
        from gdt_tax.http_policy import OriginPolicy, origin
        url = self.dvc.url(path)
        OriginPolicy().validate(url)
        target = self.legacy if origin(url) == LEGACY_ETAX_ORIGIN else self.dvc
        return target.request(method, path, **kwargs)

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)

    def url(self, path: str) -> str:
        return self.dvc.url(path)

    @property
    def hooks(self):
        return self.legacy.hooks


class ETaxSessionManager:
    def __init__(self, account: AccountContext | None = None,
                 client_factory: Callable[..., Any] = SessionHttpClient,
                 dvc_factory: Callable[..., Any] = HttpClient) -> None:
        self.account = account or AccountContext()
        self.client_factory, self.dvc_factory = client_factory, dvc_factory
        self.http: Any = None
        self.dvc_http: Any = None
        self.session = LegacySessionState()
        self.lock = RLock()
        self._fingerprint: tuple = ()

    def set_account(self, username: str, password: str) -> None:
        with self.lock:
            if (username, password) != (self.account.username, self.account.password):
                self._close_clients()
                self.account.clear()
                self.account.username, self.account.password = username, password

    def _close_clients(self) -> None:
        for client in (self.http, self.dvc_http):
            if client is not None:
                session = getattr(client, "session", None)
                if session is not None and hasattr(session, "cookies"):
                    session.cookies.clear()
                client.close()
        self.http = self.dvc_http = None
        self.session.clear()
        self._fingerprint = ()

    def logout(self) -> None:
        with self.lock:
            self._close_clients()
            self.account.clear()

    close = logout

    def invalidate(self) -> None:
        self._close_clients()
        self.account.state = "EXPIRED"

    def _client(self, config: RunConfig, hooks: RunHooks, logger) -> Any:
        settings = config.settings()
        fingerprint = (self.account.version, config.proxy, tuple(sorted(config.extra_headers.items())),
                       settings.request_timeout, settings.http_retries, settings.header_profile)
        if self.http is not None and fingerprint != self._fingerprint:
            self.invalidate()
        if self.http is None:
            self.http = self.client_factory(session_state=self.session, timeout=settings.request_timeout,
                    retries=settings.http_retries, header_profile=settings.header_profile,
                    proxy=parse_proxy(config.proxy), extra_headers=config.extra_headers, logger=logger, hooks=hooks)
            self._fingerprint = fingerprint
        self.http.hooks = hooks
        self.http.logger = logger
        return self.http

    def ensure_authenticated(self, config: RunConfig, hooks: RunHooks, captcha, logger) -> None:
        http = self._client(config, hooks, logger)
        if self.session.authenticated:
            return  # Every subsequent operation validates the server's response.
        self.account.state = "AUTHENTICATING"
        hooks.emit(session="AUTHENTICATING")
        http.authenticating = True
        try:
            EtaxLegacyPortal(http, captcha, config.settings(), logger, session_state=self.session).login()
            self.account.state = "CONNECTED"
            hooks.emit(session="CONNECTED")
        except Exception:
            self.invalidate()
            hooks.emit(session="EXPIRED")
            raise
        finally:
            http.authenticating = False

    def execute(self, config: RunConfig, hooks: RunHooks, captcha, logger=None) -> JobResult:
        logger = logger or logging.getLogger("gdt_tax.desktop")
        with self.lock:
            hooks.check()
            config = config.normalized_selection()
            self.set_account(config.username, config.password)
            settings = config.settings()
            if config.mode != "login":
                prepare_output(settings)
            if config.mode == "tax" and config.dvc and settings.from_date < settings.etax_cutoff <= settings.to_date:
                return self._mixed_tax(config, hooks, captcha, logger)
            needs_legacy = config.mode in {"login", "gnt", "notice"} or any(
                p.source == SOURCE_ETAX_LEGACY and settings.source_enabled(p.source) for p in settings.periods())
            for attempt in range(2):
                try:
                    if needs_legacy:
                        self.ensure_authenticated(config, hooks, captcha, logger)
                    else:
                        self._client(config, hooks, logger)
                    if config.mode == "login":
                        return JobResult("SUCCESS", "ETAX: Đã kết nối", config.output)
                    routed = self.http
                    if config.dvc and config.mode == "tax":
                        # DVC is experimental and authenticates independently per job.
                        self.dvc_http = self.dvc_factory(timeout=settings.request_timeout, retries=settings.http_retries,
                            header_profile=settings.header_profile, proxy=parse_proxy(config.proxy),
                            extra_headers=config.extra_headers, hooks=hooks, logger=logger)
                        routed = RoutedHttpClient(self.http, self.dvc_http)

                    def portal_factory(*_args, routed=routed):
                        if config.mode == "gnt":
                            return GntPortal(self.http, captcha, settings, logger, session_state=self.session)
                        if config.mode == "notice":
                            return TbPortal(self.http, captcha, settings, logger, session_state=self.session)
                        portals = build_portals(routed, captcha, settings, _args[3], logger)
                        if settings.source_enabled(SOURCE_ETAX_LEGACY):
                            portals[SOURCE_ETAX_LEGACY] = EtaxLegacyPortal(self.http, captcha, settings, logger, session_state=self.session)
                        return portals

                    return run_online(config, hooks, captcha, logger, http=routed, portal_factory=portal_factory,
                                      close_resources=False, propagate_auth=True)
                except SessionExpired:
                    self.invalidate()
                    hooks.emit(session="EXPIRED")
                    if attempt == 1:
                        return JobResult("ERROR", "Phiên ETAX tiếp tục hết hạn; hãy đăng nhập lại", config.output,
                                         errors=1, error_code='AUTH_EXPIRED_SESSION')
                    logger.warning("Phiên ETAX hết hạn; xác thực lại một lần rồi tiếp tục, reuse file đã hoàn thành")
                except LegacyPageError:
                    return JobResult("ERROR", 'AUTH_SCHEMA_UNKNOWN: Trang nghiệp vụ chưa được nhận diện; đã dừng xác thực lại.',
                                     config.output, errors=1, error_code='AUTH_SCHEMA_UNKNOWN')
                except AuthFailure as error:
                    return JobResult("ERROR", str(error), config.output, errors=1, error_code=error.code)
                except RunCancelled:
                    raise
                finally:
                    if self.dvc_http is not None:
                        self.dvc_http.close()
                        self.dvc_http = None
            raise AssertionError("Unreachable")

    def _mixed_tax(self, config: RunConfig, hooks: RunHooks, captcha, logger) -> JobResult:
        settings = config.settings()
        parts = [replace(config, dvc=False, to_date=(settings.etax_cutoff - timedelta(days=1)).strftime("%d/%m/%Y")),
                 replace(config, from_date=settings.etax_cutoff.strftime("%d/%m/%Y"))]
        if config.target_ids is not None:
            selected = set(config.target_ids)
            legacy_ids = {token for token in selected if RecordKey.parse(token).source == SOURCE_ETAX_LEGACY}
            dvc_ids = selected - legacy_ids
            parts = [replace(part, target_ids=tuple(sorted(legacy_ids if not part.dvc else dvc_ids)))
                     for part in parts if (legacy_ids if not part.dvc else dvc_ids)]
        if config.case_id:
            source = RecordKey.parse(config.case_id).source
            parts = [part for part in parts if (source == SOURCE_ETAX_LEGACY) == (not part.dvc)]
        result = JobResult("SUCCESS", "Chỉ tra cứu" if config.dry_run else "Đã hoàn tất", config.output)
        result.account_key = account_fingerprint(config.username)
        result.date_range = (config.from_date, config.to_date)
        outcomes = []
        for part in parts:
            try:
                hooks.check()
                child = self.execute(part, hooks, captcha, logger)
            except RunCancelled:
                result.state, result.message = "CANCELLED", "Đã dừng; kết quả của nguồn đã xử lý được giữ"
                break
            except Exception as error:
                logger.error("Nguồn %s chưa hoàn tất: %s", "DVC" if part.dvc else "ETAX", error)
                child = JobResult("ERROR", "Không kết nối được nguồn", config.output, errors=1)
            outcomes.append(child.state)
            result.rows.extend(child.rows)
            result.files = list(dict.fromkeys(result.files + child.files))
            result.discovered += child.discovered
            result.downloaded += child.downloaded
            result.errors += child.errors
            result.skipped += child.skipped + int(child.state == "ERROR")
            result.reused += child.reused
            result.issues.extend(child.issues)
            result.requested += child.requested
            if child.state == "CANCELLED":
                result.state, result.message = child.state, child.message
                break
            if config.case_id and child.discovered and (config.dry_run or child.downloaded):
                break
        if result.state != "CANCELLED" and any(s != "SUCCESS" for s in outcomes):
            result.state = "ERROR" if all(s == "ERROR" for s in outcomes) else "PARTIAL"
            result.message = "Chưa xử lý đủ ETAX/DVC; kết quả nguồn đã thành công được giữ. Xem nhật ký để biết nguồn lỗi."
        return result
