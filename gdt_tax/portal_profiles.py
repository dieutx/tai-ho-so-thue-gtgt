"""Reviewed, packaged capabilities and date routing. No remote configuration loader."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from .constants import DVC_DOWNLOAD, DVC_DOWNLOAD_FORM, DVC_SEARCH, DVC_VALIDATE
from .errors import ConfigError
from .models import SearchPeriod
from .table_contracts import SCHEMAS, TableSchema

PROFILE_VERSION = 'portal-capabilities-v1'
ROUTING_VERSION = 'date-routing-v1'


@dataclass(frozen=True)
class PortalProfile:
    source: str = 'DVC'
    version: str = PROFILE_VERSION
    search_endpoint: str = DVC_SEARCH
    validate_endpoint: str = DVC_VALIDATE
    download_endpoint: str = DVC_DOWNLOAD
    download_form_endpoint: str = DVC_DOWNLOAD_FORM
    form_id: str = 'form_search'
    page_parameter: str = 'page'
    result_container: str = 'table-container'
    page_total_id: str = 'totalPage'
    page_input_id: str = 'gotoPageInput'
    pagination: str = 'numbered'
    max_days: int = 31
    document_kinds: tuple[str, ...] = ('DECLARATION', 'ATTACHMENT')
    response_contract: TableSchema = field(default_factory=lambda: SCHEMAS['DVC'])

    def validate(self):
        if self.source != 'DVC' or not self.version or self.pagination != 'numbered':
            raise ConfigError('PORTAL_PROFILE_UNSUPPORTED')
        for endpoint in (self.search_endpoint, self.validate_endpoint, self.download_endpoint, self.download_form_endpoint):
            if not re.fullmatch(r'/[A-Za-z0-9/_-]+', endpoint):
                raise ConfigError('PORTAL_ENDPOINT_INVALID')
        for identifier in (self.form_id, self.page_parameter, self.result_container, self.page_total_id, self.page_input_id):
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', identifier):
                raise ConfigError('PORTAL_DESCRIPTOR_INVALID')
        if not 1 <= self.max_days <= 31 or self.response_contract.name != self.source:
            raise ConfigError('PORTAL_CAPABILITY_INVALID')


DVC_PROFILE = PortalProfile()


@dataclass(frozen=True)
class RouteWindow:
    source: str
    start: date
    end: date


@dataclass
class ExecutionPlan:
    version: str
    periods: list[SearchPeriod] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class RoutingPolicy:
    version: str
    effective_at: date
    windows: tuple[RouteWindow, ...]

    def plan(self, start: date, end: date, *, max_days: int, enabled, dvc_profile=DVC_PROFILE) -> ExecutionPlan:
        if start > end or not 1 <= max_days <= 31 or start < self.effective_at:
            raise ConfigError('ROUTING_RANGE_INVALID')
        dvc_profile.validate()
        for window in self.windows:
            if window.source not in {'DVC', 'ETAX', 'ETAX_LEGACY'} or window.start > window.end:
                raise ConfigError('ROUTING_WINDOW_INVALID')
        result = ExecutionPlan(self.version)
        # Split at every effective boundary; detect coverage without expanding days.
        stop = end.toordinal() + 1
        boundaries = sorted({start.toordinal(), stop} | {
            point for window in self.windows for point in (window.start.toordinal(), window.end.toordinal() + 1)
            if start.toordinal() < point < stop})
        for first, last in zip(boundaries, boundaries[1:], strict=False):
            sources = sorted({window.source for window in self.windows
                              if window.start.toordinal() <= first <= window.end.toordinal()})
            if len(sources) != 1:
                result.issues.append({'code': 'ROUTING_GAP' if not sources else 'ROUTING_OVERLAP',
                    'start': date.fromordinal(first).isoformat(), 'end': date.fromordinal(last - 1).isoformat(), 'sources': sources})
            for source in sources:
                limit = min(max_days, dvc_profile.max_days) if source == 'DVC' else max_days
                cursor = first
                while cursor < last:
                    chunk_end = min(last, cursor + limit)
                    period = SearchPeriod(date.fromordinal(cursor), date.fromordinal(chunk_end - 1), source)
                    result.periods.append(period)
                    if not enabled(source):
                        result.issues.append({'code': 'SOURCE_DISABLED', 'source': source,
                                              'start': period.start.isoformat(), 'end': period.end.isoformat()})
                    cursor = chunk_end
        result.periods.sort(key=lambda period: (period.start, period.source))
        return result


def compatibility_routing(settings) -> RoutingPolicy:
    old_source = 'ETAX_LEGACY' if settings.legacy_etax or not settings.dvc_enabled else 'ETAX'
    windows = []
    if settings.etax_cutoff > date.min:
        windows.append(RouteWindow(old_source, date.min, settings.etax_cutoff - timedelta(days=1)))
    windows.append(RouteWindow('DVC', settings.etax_cutoff, date.max))
    return RoutingPolicy(ROUTING_VERSION, date.min, tuple(windows))
