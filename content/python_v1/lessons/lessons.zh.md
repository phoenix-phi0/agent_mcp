# Python 从零入门

每个代码块独立运行。输出块以最后一个换行结束；行尾空格有意义。精确的输入输出以 JSON 字段为准。

# 第 1 课 · 从第一个程序到算术运算

`python.lesson01` · 等级: 入门

关联知识点（按学习顺序）:

- `python.env` — 环境与第一个程序
- `python.var` — 变量与赋值
- `python.num` — 数字类型
- `python.op` — 算术运算

## 学习目标

- 能保存并运行 .py 文件，分清代码、注释与输出。
- 能用变量保存数值，进行转换、交换和基本运算。

## 讲解

先学环境，再学变量、数字和运算。把代码保存为 hello.py，在终端运行 python3 hello.py；终端命令不要写进 .py 文件。Python 从上往下执行语句，print() 显示结果，# 到行尾是注释。先观察输出，再改一个数重跑。

赋值语句 = 先计算右边，再让左边的名字引用结果。变量名区分大小写；本课用字母、数字、下划线，不能以数字开头，也不能用 class 等关键字。a, b = b, a 先取右边旧值，再交换。

int 是整数，float 是浮点数；int(3.9) 去掉小数部分，不是四舍五入。+ - * / 表示加减乘除；整数相除用 / 仍得到 float。// 向下取整，% 求余，** 求幂；负数时 -7 // 2 是 -4。乘除先于加减，括号可改变顺序。x += 1 在本课数字场景相当于 x = x + 1。

## 代码示例

### 1. 运行与注释

```python
# First program
print("Hello, Python")
```

标准输入:

（空）

预期输出:

```text
Hello, Python
```

### 2. 赋值与交换

```python
a, b = 2, 5
a, b = b, a
print(a, b)
```

标准输入:

（空）

预期输出:

```text
5 2
```

### 3. 数字转换

```python
print(int(3.9), float("2.5"))
print(6 / 3)
```

标准输入:

（空）

预期输出:

```text
3 2.5
2.0
```

### 4. 运算与复合赋值

```python
x = (2 + 3) * 4
x += 1
print(x, 2 ** 3)
print(7 // 2, 7 % 2, -7 // 2)
```

标准输入:

（空）

预期输出:

```text
21 8
3 1 -4
```

## 常见错误

- 把终端命令当代码会出现语法错误；只将 Python 语句写入文件。
- 以为 int() 会四舍五入或 // 总是向零截断；先用正负数验证规则。

## 小练习

### 1. 有 17 本书，每盒放 5 本。输出装满的盒数和剩余本数。

参考答案:

```python
print(17 // 5, 17 % 5)
```

标准输入:

（空）

预期输出:

```text
3 2
```

答案说明: // 得到完整份数，% 得到余数。

### 2. 将字符串 "12" 转为整数后加 3，输出结果。

参考答案:

```python
print(int("12") + 3)
```

标准输入:

（空）

预期输出:

```text
15
```

答案说明: 转换后才能按数值相加。

# 第 2 课 · 字符串、方法与格式化输出

`python.lesson02` · 等级: 入门

关联知识点（按学习顺序）:

- `python.str` — 字符串基础
- `python.strm` — 字符串方法
- `python.fstr` — 格式化输出 f-string

## 学习目标

- 能创建字符串，按索引取字符并使用常见字符串方法。
- 能用 f-string 插入变量并控制小数位数。

## 讲解

字符串 str 用成对的单引号或双引号包围。+ 连接字符串，* 整数表示重复；len() 求字符数，索引从 0 开始。字符串不可原地修改，方法通常返回新字符串；想保留结果就赋给变量。

upper()/lower() 改变大小写，strip() 去掉两端空白，replace(旧, 新) 替换内容。split(分隔符) 切成若干字符串，join() 用指定分隔符连接它们。split 的输出中方括号表示列表，第 5 课会详细学习；此处先理解拆分与连接。

f-string 在引号前加 f，用 {表达式} 插入值。:.2f 按两位小数格式显示，不会修改原变量。float 用二进制近似表示许多十进制小数，临界值的显示未必符合直觉中的十进制四舍五入；示例选用结果明确的数。

## 代码示例

### 1. 创建、拼接与索引

```python
s = "Python"
print(s[0], len(s))
print("ab" * 2 + "!")
```

标准输入:

（空）

预期输出:

```text
P 6
abab!
```

### 2. 方法返回新字符串

```python
s = "  PyThOn  "
print(s.strip().lower())
print(s.strip().upper().replace("PY", "MY"))
print(len(s))
```

标准输入:

（空）

预期输出:

```text
python
MYTHON
10
```

### 3. 拆分与连接

```python
parts = "red,blue".split(",")
print(parts)
print("/".join(parts))
```

标准输入:

（空）

预期输出:

```text
['red', 'blue']
red/blue
```

### 4. 插值与小数位

```python
name = "Ada"
price = 3.5
print(f"{name}: {price:.2f}")
```

标准输入:

（空）

预期输出:

```text
Ada: 3.50
```

## 常见错误

- 忘记 f 时花括号不会展开；确认引号前有 f。
- 调用 strip() 后忽略返回值，原字符串仍含空白。

## 小练习

### 1. 去掉 "  hello  " 两端空白，转成大写后输出。

参考答案:

```python
print("  hello  ".strip().upper())
```

标准输入:

（空）

预期输出:

```text
HELLO
```

答案说明: 方法可连续调用，后一个方法处理前一个方法的结果。

### 2. 用 f-string 将 7.0 输出为 "total=7.00"。

参考答案:

```python
total = 7.0
print(f"total={total:.2f}")
```

标准输入:

（空）

预期输出:

```text
total=7.00
```

答案说明: :.2f 固定显示两位小数。

# 第 3 课 · 输入、比较与条件分支

`python.lesson03` · 等级: 入门

关联知识点（按学习顺序）:

- `python.io` — 输入输出
- `python.bool` — 布尔与比较
- `python.logic` — 逻辑运算
- `python.if` — if 条件语句

## 学习目标

- 能读取输入并转换数字，理解比较与逻辑运算。
- 能用 if/elif/else 表达互斥的条件。

## 讲解

input() 读取一行，返回去掉行尾换行的字符串；要做数字运算先用 int() 或 float()。input("n: ") 会先输出提示，提示没有自动换行。print 的 sep 控制多个值的分隔符，end 控制结尾；自动核对输出时，提示和末尾换行也计入。

比较 < <= > >= == != 得到 True 或 False。= 是赋值，== 比较值，is 比较是否为同一个对象，不能代替一般的相等比较。and 表示并且，or 表示或者，not 取反；and/or 会短路，并且一般返回操作数，本课用比较结果作为操作数。

if 后写条件并加冒号，代码块统一缩进四个空格。elif 只在前面条件都不成立时继续判断；else 处理剩余情况。同一条 if 链最多执行一个分支。先把条件写成自然语言，再按范围从窄到宽安排。

## 代码示例

### 1. 输入与输出分隔符

```python
n = int(input("n: "))
print(n, n + 1, sep="/", end="!\n")
```

标准输入:

```text
4
```

预期输出:

```text
n: 4/5!
```

### 2. 比较与逻辑

```python
age = 18
print(age >= 18 and age < 65)
print(age < 0 or age > 120)
print(not (age == 18))
```

标准输入:

（空）

预期输出:

```text
True
False
False
```

### 3. 单分支与双分支

```python
n = 7
if n > 0:
    print("positive")
if n % 2 == 0:
    print("even")
else:
    print("odd")
```

标准输入:

（空）

预期输出:

```text
positive
odd
```

### 4. 多分支评分

```python
score = 85
if score >= 90:
    print("A")
elif score >= 80:
    print("B")
else:
    print("C")
```

标准输入:

（空）

预期输出:

```text
B
```

## 常见错误

- 输入 "5" 后直接加整数会出错；先转换为 int。
- 把 >= 60 放在 >= 90 前会遮住高分分支；注意判断顺序与缩进。

## 小练习

### 1. 读取一个整数：大于等于 18 输出 "adult"，否则输出 "minor"。用输入 16 核对。

参考答案:

```python
age = int(input())
if age >= 18:
    print("adult")
else:
    print("minor")
```

标准输入:

```text
16
```

预期输出:

```text
minor
```

答案说明: 输入先转换，分支缩进保持一致。

### 2. 令 a=3、b=3，分别输出 a==b 与 not(a<b)。不要用 is 比较数字。

参考答案:

```python
a = 3
b = 3
print(a == b)
print(not (a < b))
```

标准输入:

（空）

预期输出:

```text
True
True
```

答案说明: == 比较值；小于关系为假，取反为真。

# 第 4 课 · 重复执行：while 与 for

`python.lesson04` · 等级: 入门

关联知识点（按学习顺序）:

- `python.while` — while 循环
- `python.for` — for 循环与 range

## 学习目标

- 能写有终止条件的 while 循环，区分 break 与 continue。
- 能用 for 和 range 控制次数与步长。

## 讲解

while 在每轮开始前检查条件。计数循环需要初始化、条件和更新；缺少更新可能永不结束。break 退出整个循环；continue 跳过本轮剩余语句，因此应先更新计数器再 continue。

for 逐个取出可迭代对象中的元素，本课先遍历字符串和 range。range(n) 产生 0 到 n-1；range(起, 止, 步长) 不包含终止值。步长可为负但不能为 0，方向不匹配时没有元素。

## 代码示例

### 1. while 计数

```python
i = 0
while i < 3:
    print(i)
    i += 1
```

标准输入:

（空）

预期输出:

```text
0
1
2
```

### 2. 跳过与退出

```python
i = 0
while i < 5:
    i += 1
    if i == 2:
        continue
    if i == 4:
        break
    print(i)
```

标准输入:

（空）

预期输出:

```text
1
3
```

### 3. 遍历与次数

```python
for ch in "ab":
    print(ch)
for n in range(2):
    print(n)
```

标准输入:

（空）

预期输出:

```text
a
b
0
1
```

### 4. 正负步长

```python
for n in range(2, 7, 2):
    print(n, end=" ")
print()
for n in range(3, 0, -1):
    print(n)
```

标准输入:

（空）

预期输出:

```text
2 4 6 
3
2
1
```

## 常见错误

- while 里忘记修改条件依赖的变量；先手算前两轮。
- 把 range 的终止值算进去会多算一轮；记住右端不包含。

## 小练习

### 1. 用 for 计算 1 到 5 的和，只输出最后结果。

参考答案:

```python
total = 0
for n in range(1, 6):
    total += n
print(total)
```

标准输入:

（空）

预期输出:

```text
15
```

答案说明: 累加器放在循环外初始化，输出也放在循环外。

### 2. 用 while 从 3 倒数到 1，每行一个数。

参考答案:

```python
n = 3
while n > 0:
    print(n)
    n -= 1
```

标准输入:

（空）

预期输出:

```text
3
2
1
```

答案说明: 每轮减 1，变为 0 时结束。

# 第 5 课 · 列表、常用操作与切片

`python.lesson05` · 等级: 基础

关联知识点（按学习顺序）:

- `python.list` — 列表
- `python.listop` — 列表常用操作
- `python.slice` — 切片

## 学习目标

- 能创建和修改列表，区分追加、排序与删除操作。
- 能用正负索引和切片取出序列的一部分。

## 讲解

列表用方括号保存有顺序的多个值，索引从 0 开始，负索引 -1 表示最后一个。列表可修改：xs[0] = 新值 替换元素，append(x) 追加一个元素，extend(可迭代对象) 逐个追加其中元素。别名赋值不会复制列表。

sort() 原地排序，返回 None；sorted(xs) 返回排好序的新列表，原列表不变。remove(值) 删除第一个相等元素，不存在会报错；pop(索引) 删除并返回指定元素，省略索引则删除末尾。不要一边遍历同一个列表一边删除它的元素。

切片 [起:止:步长] 不包含终止位置，省略起止时采用对应边界；[::-1] 反向取出。切片也适用于字符串。列表切片生成新列表，但只是浅拷贝：若元素本身是列表，内部对象仍共享。

## 代码示例

### 1. 创建、修改与追加

```python
xs = [1, 2]
xs[0] = 9
xs.append(3)
xs.extend([4, 5])
print(xs, xs[-1])
```

标准输入:

（空）

预期输出:

```text
[9, 2, 3, 4, 5] 5
```

### 2. 两种排序

```python
xs = [3, 1, 2]
print(sorted(xs), xs)
result = xs.sort()
print(xs, result)
```

标准输入:

（空）

预期输出:

```text
[1, 2, 3] [3, 1, 2]
[1, 2, 3] None
```

### 3. 按值和位置删除

```python
xs = [1, 2, 2, 3]
xs.remove(2)
last = xs.pop()
print(xs, last)
```

标准输入:

（空）

预期输出:

```text
[1, 2] 3
```

### 4. 切片与反转

```python
xs = [0, 1, 2, 3, 4]
print(xs[1:4], xs[::2])
print("Python"[::-1], xs[-2:])
```

标准输入:

（空）

预期输出:

```text
[1, 2, 3] [0, 2, 4]
nohtyP [3, 4]
```

## 常见错误

- 写 xs = xs.sort() 会把 xs 变成 None；保留 xs 或用 sorted(xs)。
- append([3,4]) 会追加一个嵌套列表；追加两个元素用 extend([3,4])。

## 小练习

### 1. 对 [4,1,3] 生成排序后的新列表，并输出原列表，证明原列表没有变化。

参考答案:

```python
xs = [4, 1, 3]
ys = sorted(xs)
print(ys)
print(xs)
```

标准输入:

（空）

预期输出:

```text
[1, 3, 4]
[4, 1, 3]
```

答案说明: sorted 返回新列表。

### 2. 从 [10,20,30,40,50] 中用切片取出 [20,30,40]，再输出最后一个元素。

参考答案:

```python
xs = [10, 20, 30, 40, 50]
print(xs[1:4])
print(xs[-1])
```

标准输入:

（空）

预期输出:

```text
[20, 30, 40]
50
```

答案说明: 切片止于索引 4 之前，-1 指最后一项。

# 第 6 课 · 元组、字典、集合与嵌套数据

`python.lesson06` · 等级: 基础

关联知识点（按学习顺序）:

- `python.tuple` — 元组
- `python.dict` — 字典
- `python.set` — 集合
- `python.nest` — 嵌套数据

## 学习目标

- 能按需要选择元组、字典、集合并进行基本操作。
- 能读懂列表套列表及列表套字典的访问方式。

## 讲解

元组用逗号组合值，常写成 (1, 2)；单元素元组要写 (1,)。元组不能替换其中的元素，但若元素是列表，该列表内部仍能修改。a, b = 元组 是解包，左右数量应匹配。

字典把键映射到值，用 {键: 值} 创建。d[键] 可读取、增加或修改；读取不存在的键会报错，d.get(键, 默认值) 则返回默认值。for key, value in d.items() 可遍历键值对。键必须可哈希，本课用字符串键；列表不能当键。

集合 set 保存不重复的可哈希元素；空集合用 set()，{} 是空字典。& 求交集，| 求并集。集合没有可依赖的显示顺序，示例先 sorted() 再输出。嵌套数据从外到内访问：rows[0]["name"] 先选列表中的字典，再按键取值。

## 代码示例

### 1. 元组创建与解包

```python
point = (2, 3)
x, y = point
single = (7,)
print(x, y, len(single))
```

标准输入:

（空）

预期输出:

```text
2 3 1
```

### 2. 字典增改与遍历

```python
scores = {"Ada": 80}
scores["Ada"] = 90
scores["Bo"] = 75
print(scores.get("Cy", 0))
for name, score in scores.items():
    print(name, score)
```

标准输入:

（空）

预期输出:

```text
0
Ada 90
Bo 75
```

### 3. 集合去重与运算

```python
a = set([3, 1, 1, 2])
b = {2, 4}
print(sorted(a))
print(sorted(a & b), sorted(a | b))
print(len(set()))
```

标准输入:

（空）

预期输出:

```text
[1, 2, 3]
[2] [1, 2, 3, 4]
0
```

### 4. 两种嵌套

```python
grid = [[1, 2], [3, 4]]
rows = [{"name": "Ada", "score": 90}]
print(grid[1][0])
for row in rows:
    print(row["name"], row["score"])
```

标准输入:

（空）

预期输出:

```text
3
Ada 90
```

## 常见错误

- 把 (1) 当元组；它只是整数，单元素元组必须有逗号。
- 依赖集合的输出顺序会导致结果不稳定；先排序再展示。

## 小练习

### 1. 将 ("Ada", 90) 解包为 name 和 score，建立字典并用 get 读取不存在的键 "age"，默认值为 0。输出名字、分数、默认值。

参考答案:

```python
name, score = ("Ada", 90)
row = {"name": name, "score": score}
print(row["name"], row["score"], row.get("age", 0))
```

标准输入:

（空）

预期输出:

```text
Ada 90 0
```

答案说明: 解包取出值，get 在缺键时返回指定默认值。

### 2. 将 [2,1,2,3,1] 去重并按升序输出列表。

参考答案:

```python
print(sorted(set([2, 1, 2, 3, 1])))
```

标准输入:

（空）

预期输出:

```text
[1, 2, 3]
```

答案说明: set 去重，sorted 固定显示顺序。

# 第 7 课 · 定义函数、参数与返回值

`python.lesson07` · 等级: 基础

关联知识点（按学习顺序）:

- `python.func` — 函数定义
- `python.param` — 函数参数
- `python.ret` — 返回值

## 学习目标

- 能定义、调用有文档字符串的函数。
- 能使用位置参数、默认参数、关键字参数和 *args，分清打印与返回。

## 讲解

def 名字(参数): 定义函数，缩进中的语句只有调用时才运行。函数体第一条字符串可作说明用途的文档字符串，用 __doc__ 读取。把重复步骤封装成函数，调用者只需提供输入并使用结果。

位置参数按顺序传入，关键字参数按名字传入，默认参数在未传值时采用默认值。默认值在定义时计算一次，初学时避免用可变列表作默认值。*args 收集多余的位置参数为元组。普通调用中，位置参数写在关键字参数前。

return 立即结束本次调用并把值交还调用处。print 只负责显示；没有 return 的函数返回 None。return a, b 实际返回一个元组，调用方可以解包。本课不在函数里修改外部变量。

## 代码示例

### 1. 定义、调用与文档字符串

```python
def greet(name):
    """Build a greeting."""
    return "Hi, " + name
print(greet("Ada"))
print(greet.__doc__)
```

标准输入:

（空）

预期输出:

```text
Hi, Ada
Build a greeting.
```

### 2. 位置、默认与关键字参数

```python
def total(price, count=2):
    return price * count
print(total(3), total(3, 4))
print(total(count=5, price=2))
```

标准输入:

（空）

预期输出:

```text
6 12
10
```

### 3. 可变位置参数

```python
def add_all(*args):
    total = 0
    for n in args:
        total += n
    return total
print(add_all(1, 2, 3), add_all())
```

标准输入:

（空）

预期输出:

```text
6 0
```

### 4. 返回元组与隐式 None

```python
def bounds(xs):
    return xs[0], xs[-1]
def show():
    print("shown")
a, b = bounds([2, 5, 8])
print(a, b)
result = show()
print(result)
```

标准输入:

（空）

预期输出:

```text
2 8
shown
None
```

## 常见错误

- 只写函数名不加括号不会调用；传参后写 greet("Ada")。
- 把 print 的屏幕输出当返回值；需要继续计算的结果应使用 return。

## 小练习

### 1. 定义 square(n)，返回平方，输出 square(6)。

参考答案:

```python
def square(n):
    return n * n
print(square(6))
```

标准输入:

（空）

预期输出:

```text
36
```

答案说明: return 把乘积交给调用方的 print。

### 2. 定义 repeat(text, count=2)，返回重复的字符串。分别用默认次数和关键字 count=3 调用，传入 "ha"。

参考答案:

```python
def repeat(text, count=2):
    return text * count
print(repeat("ha"))
print(repeat("ha", count=3))
```

标准输入:

（空）

预期输出:

```text
haha
hahaha
```

答案说明: 默认参数可以省略，关键字参数可明确覆盖默认值。

# 第 8 课 · 作用域与 lambda 排序

`python.lesson08` · 等级: 基础

关联知识点（按学习顺序）:

- `python.scope` — 作用域
- `python.lambda` — lambda 匿名函数

## 学习目标

- 能区分局部与全局变量，理解 global 的作用。
- 能用 lambda 编写简单表达式，作为 sorted 的 key。

## 讲解

函数内赋值通常创建局部变量，不会自动修改同名全局变量。读取名称时先找局部，再找外围作用域、模块全局和内置名称。global 声明后，对该名称的赋值指向模块级变量；日常设计优先通过参数输入和 return 输出，减少共享状态。

lambda 参数: 表达式 创建小型匿名函数，结果自动作为返回值；不能在其中写多条普通语句。sorted(data, key=函数) 用每个元素经过 key 计算后的值比较排序，但返回的仍是原元素。复杂逻辑应写成有名字的 def 函数。

## 代码示例

### 1. 局部变量不覆盖全局

```python
x = 10
def local():
    x = 3
    return x
print(local(), x)
```

标准输入:

（空）

预期输出:

```text
3 10
```

### 2. 显式修改全局

```python
count = 0
def tick():
    global count
    count += 1
tick()
print(count)
```

标准输入:

（空）

预期输出:

```text
1
```

### 3. lambda 返回表达式

```python
double = lambda n: n * 2
print(double(4))
```

标准输入:

（空）

预期输出:

```text
8
```

### 4. 按键排序

```python
rows = [("Ada", 90), ("Bo", 75)]
print(sorted(rows, key=lambda row: row[1]))
```

标准输入:

（空）

预期输出:

```text
[('Bo', 75), ('Ada', 90)]
```

## 常见错误

- 在函数中对全局计数器直接 += 而未声明 global，可能触发 UnboundLocalError。
- 写 key=f() 是提前调用；key=f 才是把函数交给 sorted。

## 小练习

### 1. 全局 x=8，函数内设置局部 x=2 并返回它。输出调用结果和全局 x。

参考答案:

```python
x = 8
def value():
    x = 2
    return x
print(value(), x)
```

标准输入:

（空）

预期输出:

```text
2 8
```

答案说明: 局部赋值只影响函数内部。

### 2. 用 lambda 作为 key，将 ["pear","a","kiwi"] 按字符串长度升序排序并输出。

参考答案:

```python
print(sorted(["pear", "a", "kiwi"], key=lambda word: len(word)))
```

标准输入:

（空）

预期输出:

```text
['a', 'pear', 'kiwi']
```

答案说明: 长度相同的元素保持原顺序，因为排序是稳定的。

# 第 9 课 · 模块与标准库

`python.lesson09` · 等级: 进阶

关联知识点（按学习顺序）:

- `python.module` — 模块与 import

## 学习目标

- 能区分 import 模块与 from 模块 import 名称。
- 能使用 math 与 random，并区分可复现示例和随机结果。

## 讲解

模块通常是组织相关定义的 .py 文件。import math 后通过 math.sqrt 调用；from math import sqrt 后直接写 sqrt。as 可以起别名。标准库随 Python 提供，无需为 math 或 random 安装第三方包。

把自己写的辅助函数放入独立模块有助于复用；文件名不要叫 math.py 或 random.py，以免遮住标准库。本教材用标准库演示，避免依赖外部文件。random 用于一般模拟，不用于密码；固定种子有助于同一环境复现，但不要跨版本依赖所有随机算法的精确序列。本课核对用只有一个候选值的范围，保证结果稳定。

## 代码示例

### 1. 导入模块

```python
import math
print(math.sqrt(9), math.floor(2.9))
```

标准输入:

（空）

预期输出:

```text
3.0 2
```

### 2. 导入指定名称

```python
from math import ceil
print(ceil(2.1))
```

标准输入:

（空）

预期输出:

```text
3
```

### 3. 模块别名

```python
import math as m
print(m.factorial(4))
```

标准输入:

（空）

预期输出:

```text
24
```

### 4. 使用独立随机生成器

```python
import random
rng = random.Random(7)
print(rng.randint(4, 4))
```

标准输入:

（空）

预期输出:

```text
4
```

## 常见错误

- import math 后直接写 sqrt(9) 找不到名字；应写 math.sqrt(9)。
- 给脚本起标准库同名文件名可能导入自己的文件；使用清楚的业务名称。

## 小练习

### 1. 从 math 导入 sqrt，输出 16 的平方根。

参考答案:

```python
from math import sqrt
print(sqrt(16))
```

标准输入:

（空）

预期输出:

```text
4.0
```

答案说明: from 导入后直接用函数名。

### 2. 将 math 起别名 m，输出 5 的阶乘。

参考答案:

```python
import math as m
print(m.factorial(5))
```

标准输入:

（空）

预期输出:

```text
120
```

答案说明: 通过别名访问模块成员。

# 第 10 课 · 异常处理与文件读写

`python.lesson10` · 等级: 进阶

关联知识点（按学习顺序）:

- `python.exc` — 异常处理
- `python.file` — 文件读写

## 学习目标

- 能用 try/except/else/finally 处理预期异常，用 raise 表达非法输入。
- 能用 with open 和 UTF-8 读写文件，区分 w 与 a。

## 讲解

异常表示执行中遇到无法正常完成的情况，如 ValueError、ZeroDivisionError、FileNotFoundError。try 只包需要保护的操作，except 指定预期类型。else 在 try 没有异常时执行；finally 在正常执行及异常处理后都会执行，常用于清理。raise 可主动抛出异常，便于调用方统一处理。

open 返回文件对象。with open(...) as f: 在离开代码块时关闭文件，即使块内出现异常也会关闭。文本文件明确指定 encoding="utf-8"。模式 r 读取，w 覆盖写入，a 追加；write 不自动加换行，read 读取文本。相对路径以当前工作目录为基准。本课每个示例独立运行在临时目录，不读写真实资料。

## 代码示例

### 1. 捕获转换异常

```python
try:
    value = int("abc")
except ValueError:
    print("invalid")
```

标准输入:

（空）

预期输出:

```text
invalid
```

### 2. 成功分支与清理

```python
try:
    value = 8 / 2
except ZeroDivisionError:
    print("zero")
else:
    print(value)
finally:
    print("done")
```

标准输入:

（空）

预期输出:

```text
4.0
done
```

### 3. 主动抛出异常

```python
def positive(n):
    if n <= 0:
        raise ValueError("positive required")
    return n
try:
    positive(0)
except ValueError as err:
    print(str(err))
```

标准输入:

（空）

预期输出:

```text
positive required
```

### 4. 写入、追加与读取

```python
with open("note.txt", "w", encoding="utf-8") as f:
    f.write("alpha\n")
with open("note.txt", "a", encoding="utf-8") as f:
    f.write("beta\n")
with open("note.txt", "r", encoding="utf-8") as f:
    print(f.read(), end="")
```

标准输入:

（空）

预期输出:

```text
alpha
beta
```

## 常见错误

- 用 except: 吞掉所有错误会掩盖缺陷；只捕获自己能处理的具体异常。
- 把 w 当追加会清空原文件；追加必须用 a。

## 小练习

### 1. 处理 1/0 的异常，输出 "cannot divide"；无论如何最后输出 "finished"。

参考答案:

```python
try:
    print(1 / 0)
except ZeroDivisionError:
    print("cannot divide")
finally:
    print("finished")
```

标准输入:

（空）

预期输出:

```text
cannot divide
finished
```

答案说明: 异常跳入 except，随后执行 finally。

### 2. 用 UTF-8 将 "hello" 写入 data.txt，再读回并输出。文件路径必须是相对路径。

参考答案:

```python
with open("data.txt", "w", encoding="utf-8") as f:
    f.write("hello")
with open("data.txt", "r", encoding="utf-8") as f:
    print(f.read())
```

标准输入:

（空）

预期输出:

```text
hello
```

答案说明: 两个 with 块分别管理写入和读取，写完自动关闭。

# 第 11 课 · 推导式、内置函数与类型判断

`python.lesson11` · 等级: 进阶

关联知识点（按学习顺序）:

- `python.comp` — 列表推导式
- `python.builtin` — 常用内置函数
- `python.type` — 类型判断与 None

## 学习目标

- 能把简单的循环改写成列表或字典推导式。
- 能使用聚合、enumerate、zip，判断类型与 None。

## 讲解

[表达式 for 变量 in 序列 if 条件] 用于生成新列表，按先遍历、再筛选、再计算结果的顺序理解；if 可省略。{键: 值 for ...} 创建字典。推导式应保持简短，复杂分支写成普通循环会更清楚。

sum 求和，min/max 求最小和最大；空序列的 min/max 未提供 default 时会报错。enumerate(xs, start=1) 同时提供序号和值，zip(a,b) 配对遍历，默认到较短序列结束。它们可直接放进 for，或用 list() 展示。

type(x) 查看精确类型，isinstance(x, T) 判断是否属于某类型或其子类。None 表示缺少有效结果，判断写 x is None；它不同于 0、空字符串和 False。布尔类型 bool 是 int 的子类，因此 isinstance(True, int) 为 True，精确排除布尔值时要另外检查。

## 代码示例

### 1. 列表与字典推导式

```python
print([n * n for n in range(5) if n % 2 == 0])
print({n: n * n for n in range(3)})
```

标准输入:

（空）

预期输出:

```text
[0, 4, 16]
{0: 0, 1: 1, 2: 4}
```

### 2. 聚合内置函数

```python
xs = (3, 1, 5)
print(sum(xs), min(xs), max(xs))
```

标准输入:

（空）

预期输出:

```text
9 1 5
```

### 3. 编号与配对

```python
for i, name in enumerate(["Ada", "Bo"], start=1):
    print(i, name)
print(list(zip([1, 2, 3], ["a", "b"])))
```

标准输入:

（空）

预期输出:

```text
1 Ada
2 Bo
[(1, 'a'), (2, 'b')]
```

### 4. 类型与空值

```python
value = None
print(type(3).__name__, isinstance(3, int))
zero = 0
print(value is None, zero is None)
print(isinstance(True, int), type(True) is int)
```

标准输入:

（空）

预期输出:

```text
int True
True False
True False
```

## 常见错误

- 把推导式筛选 if 放到 for 前会改变语法含义；本课筛选写在末尾。
- 用 if not x 代替 x is None 会把 0 也当成无值；按需求明确判断。

## 小练习

### 1. 用列表推导式生成 1 到 5 中奇数的平方，输出列表及其总和。

参考答案:

```python
xs = [n * n for n in range(1, 6) if n % 2 != 0]
print(xs, sum(xs))
```

标准输入:

（空）

预期输出:

```text
[1, 9, 25] 35
```

答案说明: 先筛选奇数，再求平方；sum 对结果求和。

### 2. 字典 d={"count":0}。用 get 读取 count 和 missing，分别用 is None 判断并输出。

参考答案:

```python
d = {"count": 0}
print(d.get("count") is None)
print(d.get("missing") is None)
```

标准输入:

（空）

预期输出:

```text
False
True
```

答案说明: 0 是存在的值；get 未指定默认值且缺键时返回 None。

# 第 12 课 · 类、对象、方法与属性

`python.lesson12` · 等级: 进阶

关联知识点（按学习顺序）:

- `python.class` — 类与对象
- `python.method` — 方法与属性

## 学习目标

- 能用 class 与 __init__ 创建带实例属性的对象。
- 能写实例方法与 __str__，理解 self 和对象独立状态。

## 讲解

类描述一种对象包含的数据和行为。class 定义类，类名() 创建实例；__init__ 在初始化时设置属性，不应返回非 None 值。self 是实例方法的第一个参数名惯例，表示当前实例；self.name 与局部变量 name 不同。调用 obj.method() 时，Python 自动把 obj 传给 self。

实例属性保存每个对象自己的状态，实例方法读取或更新这些属性。先通过简单类观察两个对象的属性互不影响。__str__ 返回人可读的字符串，print(obj) 会使用它；必须返回 str。本课把可变状态放在 __init__ 的 self 属性里，避免类级可变列表在实例间共享。

## 代码示例

### 1. 定义类与初始化

```python
class Student:
    def __init__(self, name):
        self.name = name
s = Student("Ada")
print(s.name)
```

标准输入:

（空）

预期输出:

```text
Ada
```

### 2. 方法更新属性

```python
class Counter:
    def __init__(self):
        self.value = 0
    def add(self, n):
        self.value += n
        return self.value
c = Counter()
print(c.add(3), c.value)
```

标准输入:

（空）

预期输出:

```text
3 3
```

### 3. 两个对象各有状态

```python
class Box:
    def __init__(self, size):
        self.size = size
a = Box(1)
b = Box(2)
a.size = 9
print(a.size, b.size)
```

标准输入:

（空）

预期输出:

```text
9 2
```

### 4. 可读的对象输出

```python
class Book:
    def __init__(self, title):
        self.title = title
    def __str__(self):
        return f"Book({self.title})"
print(Book("Python"))
```

标准输入:

（空）

预期输出:

```text
Book(Python)
```

## 常见错误

- 在方法参数里漏写 self 会造成实参数量不匹配；定义时写 self，调用时不用手传。
- 只写 name = name 不会建立实例属性；初始化时用 self.name = name。

## 小练习

### 1. 定义 Rectangle，初始化 width、height，area() 返回面积。创建宽 3 高 4 的对象并输出面积。

参考答案:

```python
class Rectangle:
    def __init__(self, width, height):
        self.width = width
        self.height = height
    def area(self):
        return self.width * self.height
print(Rectangle(3, 4).area())
```

标准输入:

（空）

预期输出:

```text
12
```

答案说明: 方法通过 self 读取当前对象的属性。

### 2. 定义 Tag，初始化 text，__str__ 返回 "[" + text + "]"。输出 Tag("ok")。

参考答案:

```python
class Tag:
    def __init__(self, text):
        self.text = text
    def __str__(self):
        return "[" + self.text + "]"
print(Tag("ok"))
```

标准输入:

（空）

预期输出:

```text
[ok]
```

答案说明: __str__ 返回字符串，print 自动调用它。

# 第 13 课 · 继承、重写与 super

`python.lesson13` · 等级: 进阶

关联知识点（按学习顺序）:

- `python.inherit` — 继承

## 学习目标

- 能定义子类、复用父类方法并重写行为。
- 能用 super() 初始化父类部分，理解子类与父类的关系。

## 讲解

class 子类(父类): 表示继承。子类未定义的方法可沿继承关系查找；同名方法在子类重新定义称为重写。调用者使用同一个方法名，不同对象可表现不同的行为。继承适合“是一种”的关系，单纯复用代码不一定需要继承。

子类自定义 __init__ 后，父类初始化不会自动再跑一遍；用 super().__init__(...) 完成父类部分，然后设置新增属性。单继承入门场景中，super().方法() 可复用父类行为；一般语义是按方法解析顺序继续查找。isinstance(子类实例, 父类) 为 True。本课只用单继承。

## 代码示例

### 1. 继承未重写的方法

```python
class Animal:
    def move(self):
        return "move"
class Dog(Animal):
    pass
print(Dog().move())
```

标准输入:

（空）

预期输出:

```text
move
```

### 2. 重写方法

```python
class Animal:
    def speak(self):
        return "sound"
class Dog(Animal):
    def speak(self):
        return "woof"
print(Animal().speak(), Dog().speak())
```

标准输入:

（空）

预期输出:

```text
sound woof
```

### 3. 父类初始化与子类属性

```python
class Person:
    def __init__(self, name):
        self.name = name
class Student(Person):
    def __init__(self, name, score):
        super().__init__(name)
        self.score = score
s = Student("Ada", 90)
print(s.name, s.score, isinstance(s, Person))
```

标准输入:

（空）

预期输出:

```text
Ada 90 True
```

### 4. 扩展父类行为

```python
class Base:
    def label(self):
        return "base"
class Child(Base):
    def label(self):
        return super().label() + "+child"
print(Child().label())
```

标准输入:

（空）

预期输出:

```text
base+child
```

## 常见错误

- 子类 __init__ 忘记调用 super，父类需要的属性可能不存在。
- 重写方法中调用 self.同名方法() 会再次调用自己；复用父类方法用 super()。

## 小练习

### 1. 定义父类 Animal，speak() 返回 "sound"；子类 Cat 重写为 "meow"，输出 Cat 的结果。

参考答案:

```python
class Animal:
    def speak(self):
        return "sound"
class Cat(Animal):
    def speak(self):
        return "meow"
print(Cat().speak())
```

标准输入:

（空）

预期输出:

```text
meow
```

答案说明: 子类同名方法覆盖父类的查找结果。

### 2. 父类 Item 初始化 name，子类 PricedItem 通过 super 初始化 name 并保存 price。创建 ("pen",3)，输出两个属性。

参考答案:

```python
class Item:
    def __init__(self, name):
        self.name = name
class PricedItem(Item):
    def __init__(self, name, price):
        super().__init__(name)
        self.price = price
x = PricedItem("pen", 3)
print(x.name, x.price)
```

标准输入:

（空）

预期输出:

```text
pen 3
```

答案说明: 父类管理公共属性，子类补充价格属性。

