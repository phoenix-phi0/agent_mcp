# 审查任务：按验收标准审查材料，返回结构化结论和问题列表
# 参数：材料 标准 补充?
# 返回派任务的完整结果；status 表示派任务是否成功，result.decision 才是审查结论。
用包 common
设 task = 审查提供的材料是否符合验收标准
设 inputs.material = {材料}
设 inputs.criteria = {标准}
设 inputs.context = {补充}
设 logic = 逐项对照验收标准，输出decision和issues，无法确认的项目列入issues
设 review = 派任务 {task} {inputs} {logic} decision:通过|需修改,issues:列表
返回 {review}
