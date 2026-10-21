"""Allowlisted structural evidence; never export portal HTML as a sanitized fixture."""
from __future__ import annotations

import hashlib
import json
from collections import Counter

from bs4 import BeautifulSoup

from .table_contracts import SCHEMAS, normalize_label


def safe_schema_evidence(html: str) -> dict:
    if len(html.encode('utf-8')) > 2 * 1024 * 1024:
        return {'code': 'EVIDENCE_LIMIT'}
    soup = BeautifulSoup(html, 'html.parser')
    allowed_tags = {'form', 'input', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a', 'select', 'option'}
    tags = Counter(node.name for node in soup.find_all(allowed_tags))
    # Unknown labels/attributes/IDs are omitted, rather than guessed to be anonymous.
    aliases = {alias: field for schema in SCHEMAS.values() for alias, field in schema.aliases.items()}
    fields = sorted({aliases[label] for cell in soup.find_all('th')
                     if (label := normalize_label(cell.get_text(' ', strip=True))) in aliases})
    structure = {'tag_counts': dict(sorted(tags.items())), 'known_fields': fields}
    return {**structure, 'fingerprint': hashlib.sha256(json.dumps(structure, sort_keys=True).encode()).hexdigest(),
            'policy': 'structure-only-v1'}
