import unittest


class MyTestCase(unittest.TestCase):
    def test_something(self):
        self.assertEqual(True, False)  # add assertion here

    def test_print(self):
        num = 7
        print(f"{num:02d}")

    def test_date(self):
        from datetime import datetime
        d = datetime.now()
        print(d.strftime('%Y年-%m月'))


if __name__ == '__main__':
    unittest.main()
