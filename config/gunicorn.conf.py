import multiprocessing

bind = ':8000'
timeout = 180
workers = multiprocessing.cpu_count() * 2 + 1
