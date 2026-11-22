import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'tmp', 'htn_demo'))
import buggy  # noqa: E402


class T(unittest.TestCase):
    def test_clamp(self):
        self.assertEqual(buggy.clamp(-1, 0, 3), 0)


if __name__ == '__main__':
    unittest.main()
