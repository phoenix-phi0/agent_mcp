import unittest
from pkg.calc import add


class T(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(1, 2), 3)
