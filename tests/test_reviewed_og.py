import json
from pathlib import Path
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

class ReviewedCountShareCardTests(unittest.TestCase):
    def test_share_card_has_curated_ranked_count_and_original_snapshot(self):
        data = json.loads((ROOT / 'data.json').read_text())
        with Image.open(ROOT / 'og.png') as image:
            self.assertEqual(image.info['CatalogCount'], str(data['count']))
            self.assertEqual(image.info['SourceSnapshot'], data['generated_at'])
            self.assertIn('unranked review references excluded', image.info['CatalogScope'])
            self.assertTrue(image.info['FooterText'].startswith(str(data['count']) + ' ranked'))
            self.assertEqual(image.size, (1200,630))

    def test_generated_footer_text_fits_between_card_margins(self):
        with Image.open(ROOT / 'og.png') as image:
            self.assertLessEqual(float(image.info['FooterWidth']), 1060)
            self.assertIn('snapshot 2026-', image.info['FooterText'])

if __name__ == '__main__': unittest.main()
