"""Reviewed, packaged capabilities and date routing. No remote configuration loader."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from .constants import (
    DVC_DOWNLOAD,
    DVC_DOWNLOAD_FORM,
    DVC_SEARCH,
    DVC_VALIDATE,
    ETAX_DOWNLOAD,
    ETAX_SEARCH,
    LEGACY_ETAX_ORIGIN,
)
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
    scope_kind: str = 'id'
    page_total_id: str = 'totalPage'
    page_input_id: str = 'gotoPageInput'
    pagination: str = 'numbered'
    max_days: int = 31
    document_kinds: tuple[str, ...] = ('DECLARATION', 'ATTACHMENT')
    response_contract: TableSchema = field(default_factory=lambda: SCHEMAS['DVC'])

    def validate(self):
        if self.source not in {'DVC', 'ETAX'} or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', self.version) or self.pagination != 'numbered' or self.scope_kind not in {'id', 'class'}:
            raise ConfigError('PORTAL_PROFILE_UNSUPPORTED')
        for endpoint in (self.search_endpoint, self.validate_endpoint, self.download_endpoint, self.download_form_endpoint):
            if not re.fullmatch(r'/[A-Za-z0-9/_-]+', endpoint):
                raise ConfigError('PORTAL_ENDPOINT_INVALID')
        for identifier in (self.form_id, self.page_parameter, self.result_container, self.page_total_id, self.page_input_id):
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', identifier):
                raise ConfigError('PORTAL_DESCRIPTOR_INVALID')
        if not 1 <= self.max_days <= 31 or self.response_contract.name != self.source:
            raise ConfigError('PORTAL_CAPABILITY_INVALID')
        if self.document_kinds != (('DECLARATION', 'ATTACHMENT') if self.source == 'DVC' else ('DECLARATION',)):
            raise ConfigError('PORTAL_CAPABILITY_INVALID')


DVC_PROFILE = PortalProfile()
ETAX_PROFILE = PortalProfile(source='ETAX', search_endpoint=ETAX_SEARCH, download_endpoint=ETAX_DOWNLOAD,
    form_id='form_search_tdt', result_container='bangKetQuaTraCuu_tdt', scope_kind='class',
    page_total_id='goToPage_tdt', page_input_id='goToPage_tdt', response_contract=SCHEMAS['ETAX'], document_kinds=('DECLARATION',))


@dataclass(frozen=True)
class LegacyProfile:
    source: str
    operation: str
    form_id: str
    table_id: str
    document_kinds: tuple[str, ...]
    version: str = PROFILE_VERSION
    endpoint: str = '/etaxnnt/Request'
    page_parameter: str = 'pn'
    query_event: str = 'query'
    download_event: str = 'download'
    pagination: str = 'post-number'
    max_days: int = 31

    def validate(self):
        if self.source not in {'ETAX_LEGACY', 'GNT', 'TB'} or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', self.version) or not 1 <= self.max_days <= 31:
            raise ConfigError('LEGACY_PROFILE_INVALID')
        if not re.fullmatch(r'/etaxnnt/[A-Za-z0-9/_-]+', self.endpoint):
            raise ConfigError('PORTAL_ENDPOINT_INVALID')
        for value in (self.operation, self.form_id, self.table_id, self.page_parameter, self.query_event, self.download_event):
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', value):
                raise ConfigError('PORTAL_DESCRIPTOR_INVALID')
        expected = {'ETAX_LEGACY': ('DECLARATION',), 'GNT': ('GNT',), 'TB': ('NOTICE',)}
        strategy = 'post-first-get-number' if self.source == 'TB' else 'post-number'
        if self.document_kinds != expected[self.source] or self.pagination != strategy:
            raise ConfigError('LEGACY_CAPABILITY_UNSUPPORTED')

    @property
    def request_url(self):
        return LEGACY_ETAX_ORIGIN + self.endpoint

    @property
    def schema(self):
        return replace(SCHEMAS[self.source], table_id=self.table_id, empty_form=self.form_id, operation=self.operation)


LEGACY_PROFILES = (
    LegacyProfile('ETAX_LEGACY', 'traCuuToKhaiProc', 'traCuuKhaiForm', 'data_content_onday', ('DECLARATION',), download_event='downTkhai'),
    LegacyProfile('GNT', 'corpQueryTaxProc', 'reportForm', 'data_content_onday', ('GNT',)),
    LegacyProfile('TB', 'tracuuTBThueKhacProc', 'tKhaiForm', 'tbl_tracuu', ('NOTICE',), pagination='post-first-get-number'),
)


def profile_for(settings, source: str) -> PortalProfile | LegacyProfile:
    selected: PortalProfile | LegacyProfile
    if source in {'DVC', 'ETAX'}:
        default = DVC_PROFILE if source == 'DVC' else ETAX_PROFILE
        value = getattr(settings, 'dvc_profile' if source == 'DVC' else 'etax_profile', default)
        selected = value if isinstance(value, PortalProfile) else default
    else:
        values = getattr(settings, 'legacy_profiles', LEGACY_PROFILES)
        if not isinstance(values, tuple):
            values = LEGACY_PROFILES
        matches = [value for value in values if isinstance(value, LegacyProfile) and value.source == source]
        if len(matches) != 1:
            raise ConfigError('PORTAL_PROFILE_MISSING_OR_DUPLICATE')
        selected = matches[0]
    selected.validate()
    if selected.source != source:
        raise ConfigError('PORTAL_PROFILE_SOURCE_MISMATCH')
    return selected


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

    def plan(self, start: date, end: date, *, max_days: int, enabled, dvc_profile=DVC_PROFILE, source_limits=None) -> ExecutionPlan:
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
                limit = min(max_days, (source_limits or {}).get(source, dvc_profile.max_days if source == 'DVC' else max_days))
                if not 1 <= limit <= 31:
                    raise ConfigError('ROUTING_SOURCE_LIMIT_INVALID')
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
