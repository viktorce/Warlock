"""Inline links and heading anchors in the shipped plugin Markdown must resolve.

Only `](target)` links outside fenced blocks and code spans, and `#` headings, are
read. Reference-style definitions, HTML anchors and underlined headings are not.
"""
from pathlib import Path
import re
import tempfile
import unittest
from urllib.parse import unquote

PLUGIN = Path(__file__).resolve().parents[1]
FENCE = re.compile(r' {0,3}(`{3,}|~{3,})(.*)')
HEADING = re.compile(r' {0,3}#{1,6} +(.+?)(?: +#+)? *$')
INLINE_CODE = re.compile(r'`[^`]*`')
LINK = re.compile(r'\]\(([^)\s]+)')
SCHEME = re.compile(r'[A-Za-z][A-Za-z0-9+.-]*:')


def prose(path):
    """Yield numbered lines outside fenced code blocks."""
    fence = None
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        match = FENCE.match(line)
        if fence is None:
            if match:
                fence = match.group(1)
            else:
                yield number, line
        elif match and match.group(1).startswith(fence) and not match.group(2).strip():
            fence = None


def anchors(path):
    """Return the anchors GitHub derives from plain-text headings, numbering repeats."""
    found, repeats = set(), {}
    for _, line in prose(path):
        match = HEADING.match(line)
        if match:
            slug = re.sub(r'[^\w\- ]', '', match.group(1).lower()).replace(' ', '-')
            count = repeats.get(slug, 0)
            repeats[slug] = count + 1
            found.add(slug + '-' + str(count) if count else slug)
    return found


def broken_links(root):
    """List inline relative links under root whose file or heading anchor is missing."""
    broken = []
    for doc in sorted(root.rglob('*.md')):
        for number, line in prose(doc):
            for target in LINK.findall(INLINE_CODE.sub('', line)):
                if SCHEME.match(target):
                    continue
                name, _, fragment = target.partition('#')
                dest = doc.parent / unquote(name) if name else doc
                if not dest.exists() or (fragment and dest.suffix == '.md'
                                         and unquote(fragment) not in anchors(dest)):
                    broken.append(str(doc.relative_to(root)) + ':' + str(number) + ': ' + target)
    return broken


class DocLinkTests(unittest.TestCase):
    def test_shipped_markdown_links_resolve(self):
        self.assertEqual(broken_links(PLUGIN), [])

    def test_only_missing_files_and_stale_anchors_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'guide.md').write_text('\n'.join([
                '# Guide',
                '## Kept section',
                '## Kept section',
                '   ## Closed heading ##',
                '```sh',
                '# Shell comment',
                '```']))
            (root / 'index.md').write_text('\n'.join([
                '# Index',
                '[kept](guide.md#kept-section) [repeat](guide.md#kept-section-1)',
                '[self](#index) [file](guide.md) [closed](guide.md#closed-heading)',
                '[web](https://example.com/#gone) `[span](missing.md)`',
                '````',
                '```',
                '[sample](missing.md)',
                '```',
                '~~~',
                '[fenced](missing.md)',
                '````',
                '[stale](guide.md#renamed-section) [comment](guide.md#shell-comment)',
                '[wrapped',
                'label](missing.md) [![image](missing.png)](guide.md)']))
            self.assertEqual(broken_links(root), [
                'index.md:12: guide.md#renamed-section',
                'index.md:12: guide.md#shell-comment',
                'index.md:14: missing.md',
                'index.md:14: missing.png'])


if __name__ == '__main__':
    unittest.main()
