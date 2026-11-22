import unittest


class T(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(1 + 1, 2)

    def test_sum(self):
        items = [1, 2, 3]
        total = sum(items[1:])
        self.assertEqual(total, 6)


if __name__ == '__main__':
    unittest.main()
