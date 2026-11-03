"""Explicit evidence-reviewed inclusion dispositions; no network or blanket removal."""
import copy
from collections import Counter
from datetime import date
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse
import html_json

ROOT = Path(__file__).resolve().parent


def policy(root=ROOT):
    rules = json.loads((Path(root) / 'inclusion.policy').read_text())
    date.fromisoformat(rules['reviewed_on'])
    template = Path(root) / 'home.template'
    if not re.fullmatch(r'[a-z]+\.kymatalabs\.com', rules['host']) or (template.exists() and 'https://' + rules['host'] + '/' not in template.read_text()):
        raise ValueError('Inclusion review belongs to another site')
    for entry in rules['decisions']:
        if entry['slug'] != re.sub(r'[^a-z0-9]+', '-', entry['entity'].lower()).strip('-'):
            raise ValueError('Reviewed entity requires its stable verified slug')
        if entry['disposition'] != 'review_reference' or not entry['reason'] or not entry['evidence']:
            raise ValueError('Inclusion decisions need explicit disposition, reason and primary evidence')
        for source in entry['evidence']:
            parsed = urlparse(source['url'])
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('Inclusion evidence must use explicit HTTPS sources')
    return rules


def include_core_repository(full_name, root=ROOT):
    excluded = {entry['entity'].lower() for entry in policy(root)['decisions']}
    return (full_name or '').lower() not in excluded


def apply(data, root=ROOT):
    result = copy.deepcopy(data)
    rules = policy(root)
    reviewed = {entry['entity'].lower(): entry for entry in rules['decisions']}
    result['items'] = [row for row in result['items'] if row['full_name'].lower() not in reviewed]
    if not result['items']:
        raise ValueError('Inclusion review cannot publish an empty ranked catalog')
    for rank, row in enumerate(result['items'], 1):
        row['rank'] = rank
    cats = Counter(row['category'] for row in result['items'])
    result['count'] = len(result['items'])
    result['categories'] = [{'name': name, 'count': count} for name, count in sorted(cats.items(), key=lambda x: -x[1])]
    references = []
    for entry in rules['decisions']:
        references.append({'full_name': entry['entity'], 'slug': entry['slug'], 'url': entry['repository'],
                           'description': entry['summary'], 'status': 'inclusion_review_reference',
                           'reviewed_on': rules['reviewed_on'], 'last_source_snapshot_at': entry['last_source_snapshot_at'],
                           'reason': entry['reason'], 'evidence_needed': entry['evidence_needed'],
                           'primary_sources': entry['evidence']})
    result['review_references'] = references
    result['inclusion_review'] = {'reviewed_on': rules['reviewed_on'], 'criteria': rules['criteria'],
                                  'scope': 'Only explicitly reviewed identities are withheld from ranked results; other entries retain their existing automated inclusion status, not independent verification.',
                                  'score_basis': 'Existing momentum scores retain their original source-snapshot basis; core ranks and category counts are recounted. Future refreshes exclude these reviewed identities before score normalization.'}
    return result


def section(data, site):
    if not data.get('review_references'): return ''
    e = lambda v: html.escape(str(v), quote=True)
    parts = ['<section class="catalog-about" id="catalog-inclusion-review"><h2>References under inclusion review</h2>',
             '<p>These published URLs are retained for context, outside ranked results and category filters. No current category, rank or momentum score is assigned.</p>',
             '<p>' + e(data['inclusion_review']['criteria']) + '</p><ul>']
    for row in data['review_references']:
        parts += ['<li><a href="' + e(site + 'p/' + row['slug'] + '/') + '">' + e(row['full_name']) + '</a> — ' + e(row['description']) +
                  ' Reviewed ' + e(row['reviewed_on']) + '. ' + e(row['reason']) + '</li>']
    parts += ['</ul><p>' + e(data['inclusion_review']['scope']) + '</p><p>' + e(data['inclusion_review']['score_basis']) + '</p></section>']
    return '\n'.join(parts)


def render_references(root=ROOT, data=None):
    root = Path(root)
    data = apply(data or json.loads((root / 'data.json').read_text()), root)
    rules = policy(root)
    e = lambda v: html.escape(str(v), quote=True)
    for row in data['review_references']:
        url = 'https://' + rules['host'] + '/p/' + row['slug'] + '/'
        schema = {'@context': 'https://schema.org', '@type': 'Article', 'headline': row['full_name'] + ' — inclusion review reference',
                  'url': url, 'description': row['description'], 'dateModified': row['reviewed_on'],
                  'about': {'@type': 'SoftwareSourceCode', 'name': row['full_name'], 'codeRepository': row['url']}}
        sources = ''.join('<li><a href="' + e(source['url']) + '">' + e(source['title']) + '</a></li>' for source in row['primary_sources'])
        output = ('<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
                  '<title>' + e(row['full_name']) + ' — inclusion review reference</title><meta name="description" content="' + e(row['description']) + '">'
                  '<link rel="canonical" href="' + url + '"><link rel="stylesheet" href="/style.css"><link rel="icon" href="/favicon.svg">'
                  '<script type="application/ld+json">' + html_json.dumps(schema, ensure_ascii=False) + '</script></head><body><main class="wrap detail">'
                  '<p><a href="/">Current ranked catalog</a> · <a href="/#catalog-inclusion-review">Inclusion review</a></p><h1>' + e(row['full_name']) + '</h1>'
                  '<p><strong>Unranked reference — inclusion under review.</strong></p><p>' + e(row['description']) + '</p>'
                  '<h2>Why this is outside ranked results</h2><p>' + e(row['reason']) + '</p><h2>Evidence needed for core inclusion</h2><p>' + e(row['evidence_needed']) + '</p>'
                  '<p>This reference has no current category, rank or momentum score. The project is not declared obsolete or unsafe.</p>'
                  '<p>Primary documentation reviewed <time datetime="' + e(row['reviewed_on']) + '">' + e(row['reviewed_on']) + '</time>. '
                  'Last catalog source snapshot: <time datetime="' + e(row['last_source_snapshot_at']) + '">' + e(row['last_source_snapshot_at']) + '</time>. No runtime test or benchmark is claimed.</p>'
                  '<h2>Sources</h2><ul>' + sources + '</ul><p><a href="' + e(row['url']) + '">Project repository</a></p></main><footer class="wrap"><a href="/privacy.html">Privacy and advertising</a></footer></body></html>\n')
        target = root / 'p' / row['slug'] / 'index.html'; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(output)


if __name__ == '__main__':
    path = ROOT / 'data.json'; data = apply(json.loads(path.read_text()), ROOT)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + '\n')
    print('Reviewed inclusion applied; ranked records:', data['count'], 'unranked references:', len(data['review_references']))
