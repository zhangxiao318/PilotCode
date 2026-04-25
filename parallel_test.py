import concurrent.futures
import logging
import time
import threading
from typing import List

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(threadName)s - %(levelname)s - %(message)s"
)

# 共享资源
shared_counter = 0
shared_list: List[int] = []
lock = threading.Lock()


def increment_counter(value: int) -> int:
    """递增共享计数器 - 存在线程安全问题"""
    global shared_counter
    # 模拟处理时间
    time.sleep(0.001)

    # 读取当前值
    current_value = shared_counter
    # 模拟一些处理时间
    time.sleep(0.001)
    # 写入新值
    shared_counter = current_value + value

    logging.info(f"Counter incremented by {value}, new value: {shared_counter}")
    return shared_counter


def safe_increment_counter(value: int) -> int:
    """使用锁保护的线程安全递增"""
    global shared_counter
    with lock:
        time.sleep(0.001)  # 模拟处理时间
        current_value = shared_counter
        time.sleep(0.001)  # 模拟处理时间
        shared_counter = current_value + value
        logging.info(f"Safe counter incremented by {value}, new value: {shared_counter}")
        return shared_counter


def append_to_list(value: int) -> None:
    """向共享列表添加元素 - 存在线程安全问题"""
    global shared_list
    time.sleep(0.001)
    shared_list.append(value)
    logging.info(f"Appended {value} to list, size: {len(shared_list)}")


def safe_append_to_list(value: int) -> None:
    """使用锁保护的线程安全添加"""
    global shared_list
    with lock:
        time.sleep(0.001)
        shared_list.append(value)
        logging.info(f"Safe appended {value} to list, size: {len(shared_list)}")


def test_unsafe_operations():
    """测试不安全的并行操作"""
    logging.info("=== 测试不安全的并行操作 ===")
    global shared_counter, shared_list

    # 重置共享资源
    shared_counter = 0
    shared_list = []

    # 使用ThreadPoolExecutor进行并行执行
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # 提交多个任务
        futures = [executor.submit(increment_counter, 1) for _ in range(10)]
        # 等待所有任务完成
        concurrent.futures.wait(futures)

    logging.info(f"Final counter value (unsafe): {shared_counter}")
    logging.info(f"Final list size (unsafe): {len(shared_list)}")


def test_safe_operations():
    """测试安全的并行操作"""
    logging.info("=== 测试安全的并行操作 ===")
    global shared_counter, shared_list

    # 重置共享资源
    shared_counter = 0
    shared_list = []

    # 使用ThreadPoolExecutor进行并行执行
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # 提交多个任务
        futures = [executor.submit(safe_increment_counter, 1) for _ in range(10)]
        # 等待所有任务完成
        concurrent.futures.wait(futures)

    logging.info(f"Final counter value (safe): {shared_counter}")
    logging.info(f"Final list size (safe): {len(shared_list)}")


def test_list_operations():
    """测试列表操作的并行执行"""
    logging.info("=== 测试列表操作的并行执行 ===")
    global shared_list

    # 重置共享资源
    shared_list = []

    # 使用ThreadPoolExecutor进行并行执行
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # 提交多个任务
        futures = [executor.submit(append_to_list, i) for i in range(10)]
        # 等待所有任务完成
        concurrent.futures.wait(futures)

    logging.info(f"Final list size (unsafe): {len(shared_list)}")
    logging.info(f"List contents: {shared_list}")


def test_safe_list_operations():
    """测试安全的列表操作"""
    logging.info("=== 测试安全的列表操作 ===")
    global shared_list

    # 重置共享资源
    shared_list = []

    # 使用ThreadPoolExecutor进行并行执行
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # 提交多个任务
        futures = [executor.submit(safe_append_to_list, i) for i in range(10)]
        # 等待所有任务完成
        concurrent.futures.wait(futures)

    logging.info(f"Final list size (safe): {len(shared_list)}")
    logging.info(f"List contents: {shared_list}")


if __name__ == "__main__":
    # 运行测试
    test_unsafe_operations()
    test_safe_operations()
    test_list_operations()
    test_safe_list_operations()
