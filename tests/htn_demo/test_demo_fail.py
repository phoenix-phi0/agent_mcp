import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'tmp', 'htn_demo'))
import buggy  # noqa: E402


class T(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(buggy.clamp(5, 0, 3), 3)

    def test_mean_empty(self):
        self.assertEqual(buggy.mean([]), 0)

    def test_mean(self):
        self.assertEqual(buggy.mean([2, 4]), 3)


if __name__ == '__main__':
    unittest.main()
