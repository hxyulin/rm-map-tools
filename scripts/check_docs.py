"""Check local Markdown links and references to removed capture scripts."""
from pathlib import Path
import re
import sys
from urllib.parse import unquote

root = Path(__file__).resolve().parents[1]
files = [root / 'README.md', root / 'README.zh-CN.md', *sorted((root / 'docs').rglob('*.md')), *sorted((root / 'benchmarks').rglob('*.md'))]
errors = []
for source in files:
    if '.vitepress' in source.parts:
        continue
    text = re.sub(r'```.*?```', '', source.read_text(), flags=re.S)
    for target in re.findall(r'!?\[[^\]]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)', text):
        if re.match(r'[a-z]+:|#|/', target, re.I):
            continue
        path = unquote(target.split('#', 1)[0])
        if path and not (source.parent / path).exists():
            errors.append(f'{source.relative_to(root)}: missing {target}')
if '--built' in sys.argv:
    from html.parser import HTMLParser
    from urllib.parse import urlparse

    dist = root / 'docs/.vitepress/dist'
    if not (dist / 'index.html').exists():
        errors.append('Build the site before checking generated links.')
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag in ('a', 'img', 'script', 'link'):
                for key, value in attrs:
                    if key in ('href', 'src') and value and not urlparse(value).scheme and not value.startswith('#'):
                        links.add(value.split('#')[0].split('?')[0])
    for page in dist.rglob('*.html'):
        links = set()
        parser = Links()
        parser.feed(page.read_text())
        for link in links:
            if link.startswith('/rm-map-tools/'):
                target = dist / unquote(link.removeprefix('/rm-map-tools/'))
            elif link.startswith('/'):
                target = dist / unquote(link.lstrip('/'))
            else:
                target = page.parent / unquote(link)
            if target.is_dir():
                target /= 'index.html'
            if not target.exists():
                errors.append(f'{page.relative_to(dist)}: missing built target {link}')
for error in errors:
    print(error)
print(f'Checked {len(files)} Markdown files; {len(errors)} missing local links.')
sys.exit(bool(errors))
