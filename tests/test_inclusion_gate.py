from collections import Counter
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import inclusion_gate

ROOT = Path(__file__).resolve().parents[1]


class ReviewedInclusionTests(unittest.TestCase):
    def test_reviewed_identity_is_unranked_but_url_and_evidence_are_retained(self):
        data = json.loads((ROOT / 'data.json').read_text()); rules = inclusion_gate.policy(ROOT)
        for entry in rules['decisions']:
            self.assertNotIn(entry['entity'], [row['full_name'] for row in data['items']])
            ref = next(row for row in data['review_references'] if row['full_name'] == entry['entity'])
            for key in ('rank', 'momentum', 'category'): self.assertNotIn(key, ref)
            path = 'p/' + entry['slug'] + '/'
            detail = (ROOT / path / 'index.html').read_text()
            self.assertIn('Unranked reference — inclusion under review', detail)
            self.assertNotIn('index rank', detail)
            self.assertNotIn('applicationCategory', detail)
            self.assertIn('https://' + rules['host'] + '/' + path, (ROOT / 'sitemap.xml').read_text())
            self.assertIn(entry['evidence'][0]['url'], detail)
            self.assertIn(entry['reason'].replace('&', '&amp;'), detail)

    def test_counts_categories_and_ranks_match_only_core_results(self):
        data = json.loads((ROOT / 'data.json').read_text())
        self.assertEqual(data['count'], len(data['items']))
        self.assertEqual([row['rank'] for row in data['items']], list(range(1, len(data['items']) + 1)))
        self.assertEqual(Counter(row['category'] for row in data['items']), {row['name']: row['count'] for row in data['categories']})
        self.assertEqual(inclusion_gate.apply(data, ROOT), data)

    def test_future_topic_match_cannot_reintroduce_demonstrated_review_case(self):
        rules = inclusion_gate.policy(ROOT)
        self.assertFalse(inclusion_gate.include_core_repository(rules['decisions'][0]['entity'].swapcase(), ROOT))
        self.assertTrue(inclusion_gate.include_core_repository('unreviewed/example', ROOT))
        data = json.loads((ROOT / 'data.json').read_text()); before = len(data['items'])
        fixture = dict(data['items'][0], full_name=rules['decisions'][0]['entity'])
        data['items'].insert(0, fixture)
        result = inclusion_gate.apply(data, ROOT)
        self.assertEqual(len(result['items']), before)
        self.assertEqual(len(result['review_references']), 1)

    def test_root_schema_machine_files_and_feed_do_not_rank_reference(self):
        data = json.loads((ROOT / 'data.json').read_text()); ref = data['review_references'][0]
        home = (ROOT / 'index.html').read_text(); llms = (ROOT / 'llms.txt').read_text()
        self.assertIn('id="catalog-inclusion-review"', home)
        # Ranked source ItemList must omit the reviewed URL; reference section keeps it linked.
        import re
        graphs = [json.loads(s) for s in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', home, re.S)]
        def nodes(v):
            if isinstance(v, dict):
                yield v
                for x in v.values(): yield from nodes(x)
            elif isinstance(v, list):
                for x in v: yield from nodes(x)
        for node in nodes(graphs):
            if node.get('@type') == 'ItemList': self.assertNotIn(ref['slug'], json.dumps(node))
        self.assertIn('unranked inclusion-review reference', llms)
        self.assertNotIn(ref['full_name'], (ROOT / 'rss.xml').read_text())

    def test_direct_ranked_detail_renderer_rejects_reviewed_identity(self):
        spec = importlib.util.spec_from_file_location('reviewed_details', ROOT / 'gen_details.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        entry = inclusion_gate.policy(ROOT)['decisions'][0]
        with self.assertRaisesRegex(ValueError, 'unranked reference'):
            module.page({'full_name': entry['entity']}, [])


if __name__ == '__main__': unittest.main()
