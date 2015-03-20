import unittest

from ..a import add
from ..iohog import touch_file
from ..miner import find_nonce, nonce_meets_target

# class TestMiner(unittest.TestCase):
#     def test_target_1(self):
#         nonce = find_nonce(1)
#         self.assertTrue(nonce_meets_target(nonce, 1))

#     def test_target_2(self):
#         nonce = find_nonce(2)
#         self.assertTrue(nonce_meets_target(nonce, 2))

#     def test_target_3(self):
#         nonce = find_nonce(3)
#         self.assertTrue(nonce_meets_target(nonce, 3))

#     @unittest.skip("skip for now")
#     def test_target_4(self):
#         nonce = find_nonce(4)
#         self.assertTrue(nonce_meets_target(nonce, 4))

#     @unittest.skip("This one takes ~70 seconds with testmon as opposed to just ~10s with standard unittest.")
#     def test_target_5(self):
#         nonce = find_nonce(5)
#         self.assertTrue(nonce_meets_target(nonce, 5))

#     @unittest.skip("This is quite a heavy one.")
#     def test_target_6(self):
#         nonce = find_nonce(6)
#         self.assertTrue(nonce_meets_target(nonce, 6))

#     @unittest.skip("Don't even think about running this one (unless you're bored as hell).")
#     def test_target_7(self):
#         nonce = find_nonce(7)
#         self.assertTrue(nonce_meets_target(nonce, 7))


# class TestIOHog(unittest.TestCase):
#     @unittest.skip("skip for now")
#     def test_io_500(self):
#         touch_file(500)

#     @unittest.skip("test")
#     def test_io_1K(self):
#         touch_file(1000)

#     @unittest.skip("test")
#     def test_io_10K(self):
#         touch_file(10000)

#     # def test_io_100K(self):
#     #     touch_file(100000)

#     # def test_io_1M(self):
#     #     touch_file(1000000)

#     # def test_io_10M(self):
#     #     touch_file(10000000)


# @unittest.skip("Unreal...")
# class TestAddIntensive(unittest.TestCase):
#     def test_compute_add_1K(self):
#         for i in range(1000):
#             self.assertEqual(add(i, i), 2*i)

#     def test_compute_add_10K(self):
#         for i in range(10000):
#             self.assertEqual(add(i, i), 2*i)

#     def test_compute_add_100K(self):
#         for i in range(100000):
#             self.assertEqual(add(i, i), 2*i)

#     def test_compute_add_1M(self):
#         for i in range(1000000):
#             self.assertEqual(add(i, i), 2*i)
