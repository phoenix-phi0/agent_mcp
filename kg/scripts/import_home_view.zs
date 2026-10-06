# 教材导入页首页的两张表：导入任务、已导入的系列（不含 hanabira）。
# 由接口「执行」，直接往响应里放 lists（同一个请求线程，响应动词照样用得上）。

用包 db http

设 jobs = 查询 app.db import_jobs
设 series_list = 查询 app.db import_series_list
设 group.import_jobs = {jobs}
设 group.import_series = {series_list}
响应 lists {group}
