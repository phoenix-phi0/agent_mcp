# 批改：对照题库判断作答，不调模型
# 参数：codes（题号，逗号分隔）、answers（学生作答）
用包 common quiz

设 result = 批量判题 content/n2n3/题库 {codes} {answers}
打印 {result}
