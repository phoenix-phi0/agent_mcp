UPDATE textbook_import_task SET status = '已撤下' WHERE series_code = :series_code AND status = '已导入'
