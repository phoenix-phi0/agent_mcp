# 示例：多城市介绍 + 写诗 + 存档
# 运行： python -m tools.dsl tools/例子.zs

模型 glm-4.6
系统 你是一个文字简洁、不说废话的助手
温度 0.8

设 theme = 秋天

遍历 city 于 杭州，苏州，成都
  问 intro = 用一句话介绍{city}的{theme}
  打印 === {city} ===
  打印 {intro}
  问 poem = 根据这句话写两行诗，不要解释：{intro}
  打印 {poem}
  保存 输出/{city}.txt {city}\n{intro}\n\n{poem}
结束

打印 全部完成。
