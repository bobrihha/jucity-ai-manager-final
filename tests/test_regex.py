
import re
import unittest

def check_app_id(text):
    match = re.search(r'(?:id|ид|код|номер|^)\s*[:.\-]?\s*(\d{4,})', text, re.IGNORECASE)
    return match.group(1) if match else None

class TestAppIDRegex(unittest.TestCase):
    def test_explicit_id(self):
        self.assertEqual(check_app_id("ID 12345"), "12345")
        self.assertEqual(check_app_id("id: 12345"), "12345")
        self.assertEqual(check_app_id("ид 12345"), "12345")
        self.assertEqual(check_app_id("мой номер 12345"), "12345")
        
    def test_implicit_id(self):
        self.assertEqual(check_app_id("12345"), "12345")
        self.assertEqual(check_app_id("123456"), "123456")
        
    def test_no_match(self):
        self.assertIsNone(check_app_id("привет"))
        self.assertIsNone(check_app_id("мне 2 билета"))  # Too short (one digit)
        self.assertIsNone(check_app_id("на 10:00"))      # Time format not matched as simple digit sequence usually, but regex allows d{4,}. "10:00" might match if stripped. Let's see. 
        # Actually my regex is `(\d{4,})`. "10:00" has digits but separated.
        self.assertIsNone(check_app_id("123"))           # Too short (<4 digits)
        
    def test_text_with_id(self):
        self.assertEqual(check_app_id("вот мой id 12345 спасибо"), "12345")
        
if __name__ == '__main__':
    unittest.main()
