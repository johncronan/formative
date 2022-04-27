import multiprocessing

bind = ':8000'
timeout = 45
workers = multiprocessing.cpu_count() * 2 + 1
