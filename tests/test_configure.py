import unittest

import configure


class ConfigureTest(unittest.TestCase):
    def test_positive_integer(self):
        self.assertEqual(262144, configure.positive_integer("262144"))
        for value in ("0", "-1", "one million"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                configure.positive_integer(value)


if __name__ == "__main__":
    unittest.main()
