import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'tmp', 'htn_demo'))
import buggy2  # noqa: E402


class T(unittest.TestCase):
    def test_double(self):
        self.assertEqual(buggy2.double(3), 6)

    def test_ratio_zero(self):
        self.assertIsNone(buggy2.ratio(1, 0))

    def test_ratio(self):
        self.assertEqual(buggy2.ratio(6, 3), 2)


if __name__ == '__main__':
    unittest.main()
