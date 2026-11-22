import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'tmp', 'htn_demo'))
import buggy3  # noqa: E402


class T(unittest.TestCase):
    def test_a(self):
        self.assertEqual(buggy3.grade(95), 'A')

    def test_b(self):
        self.assertEqual(buggy3.grade(85), 'B')

    def test_c(self):
        self.assertEqual(buggy3.grade(75), 'C')

    def test_c_edge(self):
        self.assertEqual(buggy3.grade(70), 'C')

    def test_d(self):
        self.assertEqual(buggy3.grade(65), 'D')

    def test_f(self):
        self.assertEqual(buggy3.grade(10), 'F')


if __name__ == '__main__':
    unittest.main()
