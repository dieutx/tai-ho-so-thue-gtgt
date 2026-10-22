"""Visible HTML text for control messages, without mutating the parsed tree."""
from __future__ import annotations

from bs4 import Comment, NavigableString, PageElement, Tag


def visible_text(scope: Tag, *, include_hidden_root: bool = False) -> str:
    parts: list[str] = []
    stack: list[PageElement] = [scope]
    while stack:
        node = stack.pop()
        if isinstance(node, Tag):
            style = ''.join(str(node.get('style', '')).casefold().split())
            if (not (include_hidden_root and node is scope) and (
                    node.name in {'script', 'style', 'noscript', 'template'} or node.has_attr('hidden')
                    or str(node.get('aria-hidden', '')).casefold() == 'true'
                    or 'display:none' in style or 'visibility:hidden' in style)):
                continue
            stack.extend(reversed(list(node.children)))
        elif isinstance(node, NavigableString) and not isinstance(node, Comment):
            if text := str(node).strip():
                parts.append(text)
    return ' '.join(parts)
