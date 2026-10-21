"""One bounded, non-network XML policy shared by downloaded and offline data."""
from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

MAX_XML_BYTES = 32 * 1024 * 1024
MAX_XML_DEPTH = 100
MAX_XML_NODES = 200_000


class XmlReadError(ValueError):
    """Input rejected by the XML syntax or resource policy."""


@dataclass(frozen=True)
class XmlPolicy:
    max_bytes: int = MAX_XML_BYTES
    max_depth: int = MAX_XML_DEPTH
    max_nodes: int = MAX_XML_NODES

    def __post_init__(self) -> None:
        if min(self.max_bytes, self.max_depth, self.max_nodes) < 1:
            raise ValueError('XML limits must be positive')


DEFAULT_XML_POLICY = XmlPolicy()


def parse_xml(data: bytes, policy: XmlPolicy = DEFAULT_XML_POLICY) -> etree._Element:
    if len(data) > policy.max_bytes:
        raise XmlReadError('XML_TOO_LARGE')
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True,
                             huge_tree=False, recover=False)
    try:
        root = etree.fromstring(data, parser=parser)
    except (etree.XMLSyntaxError, ValueError, TypeError) as error:
        raise XmlReadError('INVALID_XML') from error
    if root is None:
        raise XmlReadError('EMPTY_XML')
    # Historical declarations may name an external DTD. It is never loaded.
    # Entity declarations/references remain forbidden, including UTF-16 input.
    dtd = root.getroottree().docinfo.internalDTD
    if (dtd is not None and any(dtd.iterentities())
            or any(isinstance(node, etree._Entity) for node in root.iter())):
        raise XmlReadError('XML_DTD_NOT_ALLOWED')
    count = 0
    stack = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        if not isinstance(node.tag, str):
            continue
        count += 1
        if count > policy.max_nodes:
            raise XmlReadError('XML_TOO_MANY_NODES')
        if depth > policy.max_depth:
            raise XmlReadError('XML_TOO_DEEP')
        stack.extend((child, depth + 1) for child in node)
    return root
