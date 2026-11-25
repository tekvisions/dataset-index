import json, tempfile, unittest
from pathlib import Path
import url_lifecycle

ROOT = Path(url_lifecycle.__file__).parent
REAL = json.loads((ROOT / 'url.lifecycle').read_text())


class RetainedSiteNameTests(unittest.TestCase):
    def test_retained_pages_name_this_site(self):
        entry = REAL['retained_references'][0]
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            policy = {'host': REAL['host'], 'site_name': REAL['site_name'],
                      'captured_public_urls': [entry['canonical_url']], 'retained_references': [entry]}
            (root / 'url.lifecycle').write_text(json.dumps(policy))
            (root / 'data.json').write_text('{"items": []}')
            (root / 'sitemap.xml').write_text('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>')
            self.assertEqual(url_lifecycle.render_retained(root), 1)
            body = (root / 'p' / entry['slug'] / 'index.html').read_text()
            self.assertEqual(REAL['site_name'], 'The Dataset Index')
            self.assertIn('retained reference | The Dataset Index', body)
            self.assertNotIn('Diffusion', body)
            self.assertEqual(url_lifecycle.verify(root)['explicitly_retired'], [])


if __name__ == '__main__':
    unittest.main()
