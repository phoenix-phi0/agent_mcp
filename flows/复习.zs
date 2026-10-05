# 复习：针对错题重新出题并讲解
# 参数：codes（题号，逗号分隔）、level（级别）
用包 common quiz

系统 你是日语教师 JP-E01-π。复习材料要精准针对错题，不铺开讲。中文解释为主。

设 questions = 取题 content/n2n3/题库 {codes}
设 answers = 取答案 content/n2n3/题库 {codes}

打印 —— 错题重做 ——
打印 {questions}
打印

问 explanation = 学习者做错了这些题：\n{answers}\n\n针对每道题的考点，给出：一句话点明易错处、一个对比例句（正确 vs 常见错误）、一个记忆提示。每题控制在100字内，{level}级别。
打印 —— 要点 ——
打印 {explanation}
