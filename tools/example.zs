# 示例脚本：多城市介绍 + 写诗 + 存档
# 运行： python -m tools.dsl tools/example.zs

model glm-4.6
system 你是一个文字简洁、不说废话的助手
temp 0.8

set theme = 秋天

each city in 杭州, 苏州, 成都
  ask intro = 用一句话介绍{city}的{theme}
  print === {city} ===
  print {intro}
  ask poem = 根据这句话写两行诗，不要解释：{intro}
  print {poem}
  save 输出/{city}.txt {city}\n{intro}\n\n{poem}
end

print 全部完成。
