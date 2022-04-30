import multiprocessing

bind = ':8000'
timeout = 45
worker_class='gthread'
threads = 1
workers = multiprocessing.cpu_count() * 2 + 1
