import unittest

import no_such_module_for_htn_demo  # noqa: F401


class T(unittest.TestCase):
    def test_x(self):
        self.assertTrue(True)


if __name__ == '__main__':
    unittest.main()
