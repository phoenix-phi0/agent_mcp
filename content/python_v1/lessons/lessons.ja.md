# ゼロから学ぶ Python

各コードブロックは独立して実行します。出力ブロックは末尾の改行を含み、行末の空白にも意味があります。正確な入出力は JSON のフィールドを参照してください。

# 第 1 課 · 最初のプログラムから算術演算まで

`python.lesson01` · レベル: 入門

関連する知識ポイント（学習順）:

- `python.env` — 環境と最初のプログラム
- `python.var` — 変数と代入
- `python.num` — 数値型
- `python.op` — 算術演算

## 学習目標

- .py ファイルを保存して実行し、コード・コメント・出力を区別できる。
- 変数に数値を保存し、型変換・交換・基本演算ができる。

## 解説

環境、変数、数値、演算の順に学びます。コードを hello.py に保存し、ターミナルで python3 hello.py を実行します。このコマンドは .py ファイルに書きません。Python は文を上から順に実行し、print() で結果を表示します。# から行末まではコメントです。まず出力を確かめ、数値を一つ変えて再実行しましょう。

代入文 = は右辺を先に計算し、左辺の名前で結果を参照できるようにします。変数名は大文字と小文字を区別します。ここでは英字・数字・アンダースコアを使い、数字で始めたり class などのキーワードを使ったりしません。a, b = b, a は右辺の元の値を取り出してから交換します。

int は整数、float は浮動小数点数です。int(3.9) は小数部を取り除き、四捨五入ではありません。+ - * / は四則演算で、整数同士の / でも float になります。// は負の無限大方向への整数除算、% は剰余、** はべき乗です。負数では -7 // 2 は -4 になります。乗除は加減より先に計算され、括弧で順序を変えられます。この数値の例では x += 1 は x = x + 1 に相当します。

## コード例

### 1. 実行とコメント

```python
# First program
print("Hello, Python")
```

標準入力:

（空）

予想される出力:

```text
Hello, Python
```

### 2. 代入と交換

```python
a, b = 2, 5
a, b = b, a
print(a, b)
```

標準入力:

（空）

予想される出力:

```text
5 2
```

### 3. 数値の変換

```python
print(int(3.9), float("2.5"))
print(6 / 3)
```

標準入力:

（空）

予想される出力:

```text
3 2.5
2.0
```

### 4. 演算と複合代入

```python
x = (2 + 3) * 4
x += 1
print(x, 2 ** 3)
print(7 // 2, 7 % 2, -7 // 2)
```

標準入力:

（空）

予想される出力:

```text
21 8
3 1 -4
```

## よくある間違い

- ターミナルのコマンドをコードにすると構文エラーになります。ファイルには Python の文だけを書きます。
- int() が四捨五入し、// が常にゼロ方向へ丸めると思い込まないよう、正負の数で規則を確認します。

## 練習

### 1. 本が 17 冊あり、箱一つに 5 冊入ります。満杯の箱の数と残りの冊数を出力してください。

解答例:

```python
print(17 // 5, 17 % 5)
```

標準入力:

（空）

予想される出力:

```text
3 2
```

解答の説明: // で完全な組の数、% で余りを求めます。

### 2. 文字列 "12" を整数に変換してから 3 を足し、結果を出力してください。

解答例:

```python
print(int("12") + 3)
```

標準入力:

（空）

予想される出力:

```text
15
```

解答の説明: 数値として加算するには先に変換します。

# 第 2 課 · 文字列・メソッド・フォーマット出力

`python.lesson02` · レベル: 入門

関連する知識ポイント（学習順）:

- `python.str` — 文字列の基本
- `python.strm` — 文字列のメソッド
- `python.fstr` — フォーマット出力 f-string

## 学習目標

- 文字列を作成し、インデックスで文字を取得して、よく使う文字列メソッドを利用できる。
- f-string で変数を埋め込み、小数の桁数を指定できる。

## 解説

文字列 str は対応するシングルクォートまたはダブルクォートで囲みます。+ は文字列の連結、整数との * は繰り返しを表します。len() は文字数を求め、インデックスは 0 から始まります。文字列はその場で変更できず、メソッドは通常、新しい文字列を返します。結果を残すには変数へ代入します。

upper()/lower() は大文字・小文字への変換、strip() は両端の空白の除去、replace(旧, 新) は置換です。split(区切り文字) は複数の文字列に分け、join() は指定した区切り文字でつなぎます。split の出力の角括弧はリストを表し、第 5 課で詳しく学びます。ここでは分割と連結を理解しましょう。

f-string はクォートの前に f を付け、{式} で値を埋め込みます。:.2f は小数点以下 2 桁で表示し、元の変数は変更しません。float は多くの十進小数を二進数で近似するため、境界付近の表示が十進数での四捨五入の直感と異なる場合があります。例では結果が明確な数を使います。

## コード例

### 1. 作成・連結・インデックス

```python
s = "Python"
print(s[0], len(s))
print("ab" * 2 + "!")
```

標準入力:

（空）

予想される出力:

```text
P 6
abab!
```

### 2. メソッドは新しい文字列を返す

```python
s = "  PyThOn  "
print(s.strip().lower())
print(s.strip().upper().replace("PY", "MY"))
print(len(s))
```

標準入力:

（空）

予想される出力:

```text
python
MYTHON
10
```

### 3. 分割と連結

```python
parts = "red,blue".split(",")
print(parts)
print("/".join(parts))
```

標準入力:

（空）

予想される出力:

```text
['red', 'blue']
red/blue
```

### 4. 値の埋め込みと小数桁数

```python
name = "Ada"
price = 3.5
print(f"{name}: {price:.2f}")
```

標準入力:

（空）

予想される出力:

```text
Ada: 3.50
```

## よくある間違い

- f を忘れると波括弧が展開されません。クォートの前の f を確認します。
- strip() の戻り値を使わなければ、元の文字列には空白が残ります。

## 練習

### 1. "  hello  " の両端の空白を取り除き、大文字にして出力してください。

解答例:

```python
print("  hello  ".strip().upper())
```

標準入力:

（空）

予想される出力:

```text
HELLO
```

解答の説明: メソッドを続けて呼び出すと、後のメソッドは前の結果を処理します。

### 2. f-string を使い、7.0 を "total=7.00" と出力してください。

解答例:

```python
total = 7.0
print(f"total={total:.2f}")
```

標準入力:

（空）

予想される出力:

```text
total=7.00
```

解答の説明: :.2f は小数点以下を 2 桁で表示します。

# 第 3 課 · 入力・比較・条件分岐

`python.lesson03` · レベル: 入門

関連する知識ポイント（学習順）:

- `python.io` — 入出力
- `python.bool` — 真偽値と比較
- `python.logic` — 論理演算
- `python.if` — if 条件分岐

## 学習目標

- 入力を読み取って数値に変換し、比較と論理演算を理解できる。
- if/elif/else で互いに排他的な条件を表せる。

## 解説

input() は一行を読み、末尾の改行を除いた文字列を返します。数値計算には int() または float() で変換します。input("n: ") は改行なしで先に案内を表示します。print の sep は値の区切り、end は末尾を指定します。出力照合では案内や末尾の改行も含めます。

比較 < <= > >= == != の結果は True または False です。= は代入、== は値の比較、is は同じオブジェクトかどうかの比較で、一般の等値比較の代わりにはできません。and は「かつ」、or は「または」、not は否定です。and/or は短絡評価を行い、一般にはオペランドを返しますが、この課では比較結果をオペランドに使います。

if の後に条件とコロンを書き、ブロックは空白 4 個でそろえます。elif はそれ以前の条件がすべて偽のときに判定し、else は残りの場合を扱います。一つの if の連鎖では最大一つの分岐を実行します。まず条件を言葉にし、範囲の狭い条件から順に並べましょう。

## コード例

### 1. 入力と出力の区切り

```python
n = int(input("n: "))
print(n, n + 1, sep="/", end="!\n")
```

標準入力:

```text
4
```

予想される出力:

```text
n: 4/5!
```

### 2. 比較と論理

```python
age = 18
print(age >= 18 and age < 65)
print(age < 0 or age > 120)
print(not (age == 18))
```

標準入力:

（空）

予想される出力:

```text
True
False
False
```

### 3. 単一分岐と二分岐

```python
n = 7
if n > 0:
    print("positive")
if n % 2 == 0:
    print("even")
else:
    print("odd")
```

標準入力:

（空）

予想される出力:

```text
positive
odd
```

### 4. 複数の分岐による評価

```python
score = 85
if score >= 90:
    print("A")
elif score >= 80:
    print("B")
else:
    print("C")
```

標準入力:

（空）

予想される出力:

```text
B
```

## よくある間違い

- 入力の "5" に整数を直接足すとエラーになります。先に int に変換します。
- >= 60 を >= 90 より先に置くと高得点の分岐へ進めません。条件の順序とインデントを確認します。

## 練習

### 1. 整数を一つ読み、18 以上なら "adult"、それ以外なら "minor" を出力してください。入力 16 で確認します。

解答例:

```python
age = int(input())
if age >= 18:
    print("adult")
else:
    print("minor")
```

標準入力:

```text
16
```

予想される出力:

```text
minor
```

解答の説明: 入力を先に変換し、分岐のインデントをそろえます。

### 2. a=3、b=3 とし、a==b と not(a<b) を順に出力してください。数値の比較に is は使いません。

解答例:

```python
a = 3
b = 3
print(a == b)
print(not (a < b))
```

標準入力:

（空）

予想される出力:

```text
True
True
```

解答の説明: == は値を比較します。小なりの関係は偽なので、否定すると真です。

# 第 4 課 · 繰り返し：while と for

`python.lesson04` · レベル: 入門

関連する知識ポイント（学習順）:

- `python.while` — while ループ
- `python.for` — for ループと range

## 学習目標

- 終了条件のある while ループを書き、break と continue を区別できる。
- for と range で回数とステップを指定できる。

## 解説

while は各周回の前に条件を調べます。回数を数えるループには初期化・条件・更新が必要で、更新を忘れると終了しないことがあります。break はループ全体を終了し、continue はその周回の残りの文を飛ばします。そのため、continue の前にカウンターを更新しましょう。

for は反復可能なオブジェクトから要素を一つずつ取り出します。この課では文字列と range を走査します。range(n) は 0 から n-1 までで、range(開始, 終了, ステップ) は終了値を含みません。ステップは負にもできますが、0 は指定できません。方向が合わなければ要素はありません。

## コード例

### 1. while で数える

```python
i = 0
while i < 3:
    print(i)
    i += 1
```

標準入力:

（空）

予想される出力:

```text
0
1
2
```

### 2. スキップと終了

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

標準入力:

（空）

予想される出力:

```text
1
3
```

### 3. 走査と回数

```python
for ch in "ab":
    print(ch)
for n in range(2):
    print(n)
```

標準入力:

（空）

予想される出力:

```text
a
b
0
1
```

### 4. 正負のステップ

```python
for n in range(2, 7, 2):
    print(n, end=" ")
print()
for n in range(3, 0, -1):
    print(n)
```

標準入力:

（空）

予想される出力:

```text
2 4 6 
3
2
1
```

## よくある間違い

- while の条件に使う変数を更新し忘れないよう、最初の二周を手で追います。
- range の終了値を含めると一回多く数えてしまいます。右端を含まないことを覚えましょう。

## 練習

### 1. for を使って 1 から 5 までの合計を求め、最後の結果だけを出力してください。

解答例:

```python
total = 0
for n in range(1, 6):
    total += n
print(total)
```

標準入力:

（空）

予想される出力:

```text
15
```

解答の説明: 合計用の変数はループの前に初期化し、出力もループの外で行います。

### 2. while を使い、3 から 1 まで一行ずつカウントダウンしてください。

解答例:

```python
n = 3
while n > 0:
    print(n)
    n -= 1
```

標準入力:

（空）

予想される出力:

```text
3
2
1
```

解答の説明: 各周回で 1 を引き、0 になったら終了します。

# 第 5 課 · リスト・よく使う操作・スライス

`python.lesson05` · レベル: 基礎

関連する知識ポイント（学習順）:

- `python.list` — リスト
- `python.listop` — リストのよく使う操作
- `python.slice` — スライス

## 学習目標

- リストを作成・変更し、追加・並べ替え・削除の操作を区別できる。
- 正負のインデックスとスライスでシーケンスの一部を取り出せる。

## 解説

リストは角括弧で順序のある複数の値を保存します。インデックスは 0 から始まり、負のインデックス -1 は最後の要素です。リストは変更でき、xs[0] = 新しい値 で置換、append(x) で一要素の追加、extend(反復可能なオブジェクト) で各要素の追加を行います。別の名前への代入だけではリストはコピーされません。

sort() はその場で並べ替えて None を返し、sorted(xs) は元を変えずに並べ替えた新しいリストを返します。remove(値) は最初に一致する要素を削除し、見つからなければエラーです。pop(インデックス) は指定要素を削除して返し、省略すると末尾を扱います。同じリストを走査しながら要素を削除することは避けましょう。

スライス [開始:終了:ステップ] は終了位置を含まず、開始や終了の省略時は対応する境界を使います。[::-1] は逆順に取り出します。文字列にも使えます。リストのスライスは新しいリストを作りますが、浅いコピーなので、要素自体がリストなら内部のオブジェクトは共有されます。

## コード例

### 1. 作成・変更・追加

```python
xs = [1, 2]
xs[0] = 9
xs.append(3)
xs.extend([4, 5])
print(xs, xs[-1])
```

標準入力:

（空）

予想される出力:

```text
[9, 2, 3, 4, 5] 5
```

### 2. 二つの並べ替え

```python
xs = [3, 1, 2]
print(sorted(xs), xs)
result = xs.sort()
print(xs, result)
```

標準入力:

（空）

予想される出力:

```text
[1, 2, 3] [3, 1, 2]
[1, 2, 3] None
```

### 3. 値と位置による削除

```python
xs = [1, 2, 2, 3]
xs.remove(2)
last = xs.pop()
print(xs, last)
```

標準入力:

（空）

予想される出力:

```text
[1, 2] 3
```

### 4. スライスと逆順

```python
xs = [0, 1, 2, 3, 4]
print(xs[1:4], xs[::2])
print("Python"[::-1], xs[-2:])
```

標準入力:

（空）

予想される出力:

```text
[1, 2, 3] [0, 2, 4]
nohtyP [3, 4]
```

## よくある間違い

- xs = xs.sort() と書くと xs が None になります。xs をそのまま使うか sorted(xs) を使います。
- append([3,4]) は入れ子のリストを一つ追加します。二要素の追加には extend([3,4]) を使います。

## 練習

### 1. [4,1,3] を並べ替えた新しいリストを作り、元のリストも出力して変更されていないことを示してください。

解答例:

```python
xs = [4, 1, 3]
ys = sorted(xs)
print(ys)
print(xs)
```

標準入力:

（空）

予想される出力:

```text
[1, 3, 4]
[4, 1, 3]
```

解答の説明: sorted は新しいリストを返します。

### 2. [10,20,30,40,50] からスライスで [20,30,40] を取り出し、次に元のリストの最後の要素を出力してください。

解答例:

```python
xs = [10, 20, 30, 40, 50]
print(xs[1:4])
print(xs[-1])
```

標準入力:

（空）

予想される出力:

```text
[20, 30, 40]
50
```

解答の説明: スライスはインデックス 4 の直前までで、-1 は最後の要素です。

# 第 6 課 · タプル・辞書・集合・入れ子のデータ

`python.lesson06` · レベル: 基礎

関連する知識ポイント（学習順）:

- `python.tuple` — タプル
- `python.dict` — 辞書
- `python.set` — 集合
- `python.nest` — 入れ子のデータ

## 学習目標

- 用途に合わせてタプル・辞書・集合を選び、基本操作ができる。
- リスト内のリストや辞書へのアクセス方法を理解できる。

## 解説

タプルはカンマで値を組にし、通常 (1, 2) と書きます。一要素のタプルは (1,) です。タプルの要素は置換できませんが、要素がリストならその内部は変更できます。a, b = タプル はアンパックで、左右の個数を合わせます。

辞書はキーと値を対応させ、{キー: 値} で作ります。d[キー] で取得・追加・変更ができます。存在しないキーの取得はエラーですが、d.get(キー, 既定値) は既定値を返します。for key, value in d.items() でキーと値の組を走査します。キーはハッシュ可能である必要があり、この課では文字列を使います。リストはキーにできません。

集合 set は重複しないハッシュ可能な要素を保存します。空集合は set() で、{} は空の辞書です。& は積集合、| は和集合を求めます。集合の表示順には依存できないため、例では sorted() の後に出力します。入れ子のデータは外側から内側へアクセスします。rows[0]["name"] はリスト内の辞書を選んでから、キーで値を取り出します。

## コード例

### 1. タプルの作成とアンパック

```python
point = (2, 3)
x, y = point
single = (7,)
print(x, y, len(single))
```

標準入力:

（空）

予想される出力:

```text
2 3 1
```

### 2. 辞書の追加・変更と走査

```python
scores = {"Ada": 80}
scores["Ada"] = 90
scores["Bo"] = 75
print(scores.get("Cy", 0))
for name, score in scores.items():
    print(name, score)
```

標準入力:

（空）

予想される出力:

```text
0
Ada 90
Bo 75
```

### 3. 集合による重複除去と演算

```python
a = set([3, 1, 1, 2])
b = {2, 4}
print(sorted(a))
print(sorted(a & b), sorted(a | b))
print(len(set()))
```

標準入力:

（空）

予想される出力:

```text
[1, 2, 3]
[2] [1, 2, 3, 4]
0
```

### 4. 二種類の入れ子

```python
grid = [[1, 2], [3, 4]]
rows = [{"name": "Ada", "score": 90}]
print(grid[1][0])
for row in rows:
    print(row["name"], row["score"])
```

標準入力:

（空）

予想される出力:

```text
3
Ada 90
```

## よくある間違い

- (1) は整数です。一要素のタプルにはカンマが必要です。
- 集合の出力順に依存すると結果が不安定になるため、表示前に並べ替えます。

## 練習

### 1. ("Ada", 90) を name と score にアンパックし、辞書を作って、存在しないキー "age" を get で取得してください。既定値は 0 とし、名前・点数・既定値を出力します。

解答例:

```python
name, score = ("Ada", 90)
row = {"name": name, "score": score}
print(row["name"], row["score"], row.get("age", 0))
```

標準入力:

（空）

予想される出力:

```text
Ada 90 0
```

解答の説明: アンパックで値を取り出し、get はキーがないとき指定の既定値を返します。

### 2. [2,1,2,3,1] の重複を除き、昇順のリストとして出力してください。

解答例:

```python
print(sorted(set([2, 1, 2, 3, 1])))
```

標準入力:

（空）

予想される出力:

```text
[1, 2, 3]
```

解答の説明: set で重複を除き、sorted で表示順を固定します。

# 第 7 課 · 関数の定義・引数・戻り値

`python.lesson07` · レベル: 基礎

関連する知識ポイント（学習順）:

- `python.func` — 関数の定義
- `python.param` — 関数の引数
- `python.ret` — 戻り値

## 学習目標

- ドキュメンテーション文字列を持つ関数を定義して呼び出せる。
- 位置引数・デフォルト引数・キーワード引数・*args を使い、表示と戻り値を区別できる。

## 解説

def 名前(引数): で関数を定義し、インデント内の文は呼び出したときに実行されます。関数本体の先頭の文字列は説明用のドキュメンテーション文字列となり、__doc__ で読めます。繰り返す処理を関数にまとめると、呼び出す側は入力を渡して結果を使えます。

位置引数は順番に、キーワード引数は名前で渡します。デフォルト引数は値が渡されなかったときに使います。既定値は定義時に一度だけ評価されるため、初学者は変更可能なリストを既定値にしないようにします。*args は余分な位置引数をタプルにまとめます。通常の呼び出しでは位置引数をキーワード引数より前に書きます。

return はその呼び出しを直ちに終了して、値を呼び出し元へ返します。print は表示するだけで、return のない関数は None を返します。return a, b は実際には一つのタプルを返し、呼び出し側でアンパックできます。この課では関数の中から外部の変数を変更しません。

## コード例

### 1. 定義・呼び出し・ドキュメンテーション文字列

```python
def greet(name):
    """Build a greeting."""
    return "Hi, " + name
print(greet("Ada"))
print(greet.__doc__)
```

標準入力:

（空）

予想される出力:

```text
Hi, Ada
Build a greeting.
```

### 2. 位置引数・デフォルト引数・キーワード引数

```python
def total(price, count=2):
    return price * count
print(total(3), total(3, 4))
print(total(count=5, price=2))
```

標準入力:

（空）

予想される出力:

```text
6 12
10
```

### 3. 可変長の位置引数

```python
def add_all(*args):
    total = 0
    for n in args:
        total += n
    return total
print(add_all(1, 2, 3), add_all())
```

標準入力:

（空）

予想される出力:

```text
6 0
```

### 4. タプルの戻り値と暗黙の None

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

標準入力:

（空）

予想される出力:

```text
2 8
shown
None
```

## よくある間違い

- 関数名だけでは呼び出しになりません。greet("Ada") のように括弧で引数を渡します。
- print の画面表示を戻り値と混同しないようにします。後で計算に使う結果は return で返します。

## 練習

### 1. square(n) を定義して平方を返し、square(6) を出力してください。

解答例:

```python
def square(n):
    return n * n
print(square(6))
```

標準入力:

（空）

予想される出力:

```text
36
```

解答の説明: return で積を返し、呼び出し側の print で表示します。

### 2. repeat(text, count=2) を定義し、繰り返した文字列を返してください。"ha" を渡し、既定の回数とキーワード count=3 でそれぞれ呼び出します。

解答例:

```python
def repeat(text, count=2):
    return text * count
print(repeat("ha"))
print(repeat("ha", count=3))
```

標準入力:

（空）

予想される出力:

```text
haha
hahaha
```

解答の説明: デフォルト引数は省略でき、キーワード引数で既定値を明示的に変更できます。

# 第 8 課 · スコープと lambda による並べ替え

`python.lesson08` · レベル: 基礎

関連する知識ポイント（学習順）:

- `python.scope` — スコープ
- `python.lambda` — lambda 無名関数

## 学習目標

- ローカル変数とグローバル変数を区別し、global の働きを理解できる。
- lambda で簡単な式を書き、sorted の key として使える。

## 解説

関数内の代入は通常ローカル変数を作り、同名のグローバル変数を自動では変更しません。名前はローカル、外側のスコープ、モジュールのグローバル、組み込みの順に探します。global を宣言すると、その名前への代入はモジュールレベルの変数を対象にします。普段は引数と return で値を受け渡し、共有状態を減らしましょう。

lambda 引数: 式 は小さな無名関数を作り、式の結果を自動的に返します。複数の通常の文は書けません。sorted(data, key=関数) は各要素を key に渡した結果で並べ替えますが、返すのは元の要素です。複雑な処理には名前のある def の関数を使いましょう。

## コード例

### 1. ローカル変数はグローバルを上書きしない

```python
x = 10
def local():
    x = 3
    return x
print(local(), x)
```

標準入力:

（空）

予想される出力:

```text
3 10
```

### 2. グローバルを明示的に変更する

```python
count = 0
def tick():
    global count
    count += 1
tick()
print(count)
```

標準入力:

（空）

予想される出力:

```text
1
```

### 3. lambda は式の結果を返す

```python
double = lambda n: n * 2
print(double(4))
```

標準入力:

（空）

予想される出力:

```text
8
```

### 4. キーによる並べ替え

```python
rows = [("Ada", 90), ("Bo", 75)]
print(sorted(rows, key=lambda row: row[1]))
```

標準入力:

（空）

予想される出力:

```text
[('Bo', 75), ('Ada', 90)]
```

## よくある間違い

- 関数内で global を宣言せずにグローバルのカウンターへ += すると、UnboundLocalError になることがあります。
- key=f() はその場で呼び出してしまいます。sorted に関数を渡すには key=f と書きます。

## 練習

### 1. グローバルの x=8 とし、関数内でローカルの x=2 を設定して返してください。呼び出し結果とグローバルの x を出力します。

解答例:

```python
x = 8
def value():
    x = 2
    return x
print(value(), x)
```

標準入力:

（空）

予想される出力:

```text
2 8
```

解答の説明: ローカルへの代入は関数内部だけに影響します。

### 2. lambda を key に使い、["pear","a","kiwi"] を文字列の長さの昇順に並べ替えて出力してください。

解答例:

```python
print(sorted(["pear", "a", "kiwi"], key=lambda word: len(word)))
```

標準入力:

（空）

予想される出力:

```text
['a', 'pear', 'kiwi']
```

解答の説明: 並べ替えは安定しているので、同じ長さの要素は元の順序を保ちます。

# 第 9 課 · モジュールと標準ライブラリ

`python.lesson09` · レベル: 応用

関連する知識ポイント（学習順）:

- `python.module` — モジュールと import

## 学習目標

- import モジュールと from モジュール import 名前を区別できる。
- math と random を使い、再現可能な例とランダムな結果を区別できる。

## 解説

モジュールは通常、関連する定義をまとめた .py ファイルです。import math の後は math.sqrt、from math import sqrt の後は sqrt と書いて呼び出します。as で別名を付けられます。math や random は Python に付属する標準ライブラリなので、外部パッケージの導入は不要です。

自作の補助関数を別モジュールにすると再利用しやすくなります。標準ライブラリを隠してしまうため、ファイル名に math.py や random.py を使わないようにします。教材では外部ファイルに依存しない標準ライブラリの例を使います。random は一般的なシミュレーション用で、パスワード用ではありません。シード固定は同じ環境での再現に役立ちますが、すべての乱数アルゴリズムの正確な列がバージョンを超えて同じとは限りません。この課の照合では候補が一つだけの範囲を使い、結果を安定させます。

## コード例

### 1. モジュールのインポート

```python
import math
print(math.sqrt(9), math.floor(2.9))
```

標準入力:

（空）

予想される出力:

```text
3.0 2
```

### 2. 指定した名前のインポート

```python
from math import ceil
print(ceil(2.1))
```

標準入力:

（空）

予想される出力:

```text
3
```

### 3. モジュールの別名

```python
import math as m
print(m.factorial(4))
```

標準入力:

（空）

予想される出力:

```text
24
```

### 4. 独立した乱数生成器を使う

```python
import random
rng = random.Random(7)
print(rng.randint(4, 4))
```

標準入力:

（空）

予想される出力:

```text
4
```

## よくある間違い

- import math の後に sqrt(9) とだけ書くと名前が見つかりません。math.sqrt(9) と書きます。
- スクリプトに標準ライブラリと同じ名前を付けると自分のファイルが読み込まれることがあるため、用途の分かる別名を使います。

## 練習

### 1. math から sqrt をインポートし、16 の平方根を出力してください。

解答例:

```python
from math import sqrt
print(sqrt(16))
```

標準入力:

（空）

予想される出力:

```text
4.0
```

解答の説明: from でインポートした後は関数名を直接使います。

### 2. math に m という別名を付け、5 の階乗を出力してください。

解答例:

```python
import math as m
print(m.factorial(5))
```

標準入力:

（空）

予想される出力:

```text
120
```

解答の説明: 別名を通してモジュールのメンバーにアクセスします。

# 第 10 課 · 例外処理とファイルの読み書き

`python.lesson10` · レベル: 応用

関連する知識ポイント（学習順）:

- `python.exc` — 例外処理
- `python.file` — ファイルの読み書き

## 学習目標

- try/except/else/finally で予想される例外を処理し、raise で不正な入力を表せる。
- with open と UTF-8 でファイルを読み書きし、w と a を区別できる。

## 解説

例外は処理を正常に完了できない状況を表し、ValueError、ZeroDivisionError、FileNotFoundError などがあります。try には保護が必要な操作を入れ、except で予想する型を指定します。else は try で例外が起きなかったとき、finally は正常実行や例外処理の後に実行され、後片付けによく使います。raise で明示的に例外を発生させ、呼び出し側で統一して処理できます。

open はファイルオブジェクトを返します。with open(...) as f: はブロックを離れるとき、例外が起きてもファイルを閉じます。テキストファイルでは encoding="utf-8" を明示します。r は読み取り、w は上書き、a は追記です。write は改行を自動追加せず、read はテキストを読み取ります。相対パスの基準は現在の作業ディレクトリです。この課の各例は独立した一時ディレクトリで実行し、実際の資料を読み書きしません。

## コード例

### 1. 変換の例外を捕捉する

```python
try:
    value = int("abc")
except ValueError:
    print("invalid")
```

標準入力:

（空）

予想される出力:

```text
invalid
```

### 2. 成功時の分岐と後片付け

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

標準入力:

（空）

予想される出力:

```text
4.0
done
```

### 3. 明示的に例外を発生させる

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

標準入力:

（空）

予想される出力:

```text
positive required
```

### 4. 書き込み・追記・読み取り

```python
with open("note.txt", "w", encoding="utf-8") as f:
    f.write("alpha\n")
with open("note.txt", "a", encoding="utf-8") as f:
    f.write("beta\n")
with open("note.txt", "r", encoding="utf-8") as f:
    print(f.read(), end="")
```

標準入力:

（空）

予想される出力:

```text
alpha
beta
```

## よくある間違い

- except: ですべてのエラーを握りつぶすと不具合が隠れます。処理できる具体的な例外だけを捕捉します。
- w を追記だと思うと元のファイルが空になります。追記には a を使います。

## 練習

### 1. 1/0 の例外を処理して "cannot divide" を出力し、最後に必ず "finished" を出力してください。

解答例:

```python
try:
    print(1 / 0)
except ZeroDivisionError:
    print("cannot divide")
finally:
    print("finished")
```

標準入力:

（空）

予想される出力:

```text
cannot divide
finished
```

解答の説明: 例外で except に移り、その後 finally を実行します。

### 2. UTF-8 で "hello" を data.txt に書き込み、読み戻して出力してください。ファイルパスは相対パスにします。

解答例:

```python
with open("data.txt", "w", encoding="utf-8") as f:
    f.write("hello")
with open("data.txt", "r", encoding="utf-8") as f:
    print(f.read())
```

標準入力:

（空）

予想される出力:

```text
hello
```

解答の説明: 二つの with ブロックで書き込みと読み取りを別々に管理し、書き終わると自動的に閉じます。

# 第 11 課 · 内包表記・組み込み関数・型の判定

`python.lesson11` · レベル: 応用

関連する知識ポイント（学習順）:

- `python.comp` — リスト内包表記
- `python.builtin` — よく使う組み込み関数
- `python.type` — 型の判定と None

## 学習目標

- 簡単なループをリスト内包表記や辞書内包表記に書き換えられる。
- 集計・enumerate・zip を使い、型と None を判定できる。

## 解説

[式 for 変数 in シーケンス if 条件] は新しいリストを作ります。走査、絞り込み、結果の計算の順に理解し、if は省略できます。{キー: 値 for ...} は辞書を作ります。内包表記は短く保ち、複雑な分岐は普通のループで書くと分かりやすくなります。

sum は合計、min/max は最小値と最大値を求めます。空のシーケンスで default を指定しない min/max はエラーになります。enumerate(xs, start=1) は番号と値を同時に返し、zip(a,b) は対応する値を組にし、既定では短い方に合わせて終了します。直接 for で使うか、list() で内容を表示できます。

type(x) は正確な型を調べ、isinstance(x, T) はその型またはサブクラスに属するかを判定します。None は有効な結果がないことを表し、x is None で判定します。0・空文字列・False とは異なります。bool は int のサブクラスなので isinstance(True, int) は True です。真偽値を厳密に除きたいときは別に確認します。

## コード例

### 1. リスト内包表記と辞書内包表記

```python
print([n * n for n in range(5) if n % 2 == 0])
print({n: n * n for n in range(3)})
```

標準入力:

（空）

予想される出力:

```text
[0, 4, 16]
{0: 0, 1: 1, 2: 4}
```

### 2. 集計用の組み込み関数

```python
xs = (3, 1, 5)
print(sum(xs), min(xs), max(xs))
```

標準入力:

（空）

予想される出力:

```text
9 1 5
```

### 3. 番号付けと組み合わせ

```python
for i, name in enumerate(["Ada", "Bo"], start=1):
    print(i, name)
print(list(zip([1, 2, 3], ["a", "b"])))
```

標準入力:

（空）

予想される出力:

```text
1 Ada
2 Bo
[(1, 'a'), (2, 'b')]
```

### 4. 型と値なし

```python
value = None
print(type(3).__name__, isinstance(3, int))
zero = 0
print(value is None, zero is None)
print(isinstance(True, int), type(True) is int)
```

標準入力:

（空）

予想される出力:

```text
int True
True False
True False
```

## よくある間違い

- 絞り込み用の if を for より前に置くと構文の意味が変わります。この課の絞り込みは末尾に書きます。
- if not x を x is None の代わりにすると 0 も値なしとして扱います。目的に合わせて明確に判定します。

## 練習

### 1. リスト内包表記で 1 から 5 の奇数の平方を作り、リストと合計を出力してください。

解答例:

```python
xs = [n * n for n in range(1, 6) if n % 2 != 0]
print(xs, sum(xs))
```

標準入力:

（空）

予想される出力:

```text
[1, 9, 25] 35
```

解答の説明: 奇数に絞ってから平方を求め、sum で結果を合計します。

### 2. 辞書 d={"count":0} から count と missing を get で取得し、それぞれ is None で判定して出力してください。

解答例:

```python
d = {"count": 0}
print(d.get("count") is None)
print(d.get("missing") is None)
```

標準入力:

（空）

予想される出力:

```text
False
True
```

解答の説明: 0 は存在する値です。get は既定値を指定せずキーがないと None を返します。

# 第 12 課 · クラス・オブジェクト・メソッド・属性

`python.lesson12` · レベル: 応用

関連する知識ポイント（学習順）:

- `python.class` — クラスとオブジェクト
- `python.method` — メソッドと属性

## 学習目標

- class と __init__ でインスタンス属性を持つオブジェクトを作れる。
- インスタンスメソッドと __str__ を書き、self とオブジェクトごとの状態を理解できる。

## 解説

クラスはオブジェクトのデータと動作を表します。class で定義し、クラス名() でインスタンスを作ります。__init__ は初期化時に属性を設定し、None 以外の値を返してはいけません。self はインスタンスメソッドの第 1 引数の慣例的な名前で、現在のインスタンスを表します。self.name はローカル変数 name とは異なります。obj.method() の呼び出しでは Python が obj を self に渡します。

インスタンス属性は各オブジェクトの状態を保存し、インスタンスメソッドはそれを読み書きします。まず簡単なクラスで、二つのオブジェクトの属性が互いに影響しないことを確認します。__str__ は人が読める文字列を返し、print(obj) が利用します。戻り値は必ず str にします。この課では変更可能な状態を __init__ 内の self の属性に置き、クラスの可変リストがインスタンス間で共有されることを避けます。

## コード例

### 1. クラスの定義と初期化

```python
class Student:
    def __init__(self, name):
        self.name = name
s = Student("Ada")
print(s.name)
```

標準入力:

（空）

予想される出力:

```text
Ada
```

### 2. メソッドで属性を更新する

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

標準入力:

（空）

予想される出力:

```text
3 3
```

### 3. 二つのオブジェクトそれぞれの状態

```python
class Box:
    def __init__(self, size):
        self.size = size
a = Box(1)
b = Box(2)
a.size = 9
print(a.size, b.size)
```

標準入力:

（空）

予想される出力:

```text
9 2
```

### 4. 読みやすいオブジェクトの表示

```python
class Book:
    def __init__(self, title):
        self.title = title
    def __str__(self):
        return f"Book({self.title})"
print(Book("Python"))
```

標準入力:

（空）

予想される出力:

```text
Book(Python)
```

## よくある間違い

- メソッドの引数に self を忘れると個数が合わなくなります。定義では self を書き、呼び出すときは明示的に渡しません。
- name = name だけではインスタンス属性は作れません。初期化には self.name = name を使います。

## 練習

### 1. Rectangle を定義し、width と height を初期化して area() で面積を返してください。幅 3、高さ 4 のオブジェクトを作り、面積を出力します。

解答例:

```python
class Rectangle:
    def __init__(self, width, height):
        self.width = width
        self.height = height
    def area(self):
        return self.width * self.height
print(Rectangle(3, 4).area())
```

標準入力:

（空）

予想される出力:

```text
12
```

解答の説明: メソッドは self を通して現在のオブジェクトの属性を読みます。

### 2. Tag を定義して text を初期化し、__str__ で "[" + text + "]" を返してください。Tag("ok") を出力します。

解答例:

```python
class Tag:
    def __init__(self, text):
        self.text = text
    def __str__(self):
        return "[" + self.text + "]"
print(Tag("ok"))
```

標準入力:

（空）

予想される出力:

```text
[ok]
```

解答の説明: __str__ は文字列を返し、print が自動的に呼び出します。

# 第 13 課 · 継承・オーバーライド・super

`python.lesson13` · レベル: 応用

関連する知識ポイント（学習順）:

- `python.inherit` — 継承

## 学習目標

- サブクラスを定義し、親クラスのメソッドを再利用して動作をオーバーライドできる。
- super() で親クラスの部分を初期化し、サブクラスと親クラスの関係を理解できる。

## 解説

class サブクラス(親クラス): は継承を表します。サブクラスにないメソッドは継承関係に沿って探します。同名のメソッドをサブクラスで定義し直すことをオーバーライドといいます。呼び出し側が同じメソッド名を使っても、オブジェクトによって異なる動作をします。継承は「一種である」という関係に適し、コードの再利用だけなら必ずしも必要ではありません。

サブクラスで __init__ を定義すると、親クラスの初期化は自動では実行されません。super().__init__(...) で親クラスの部分を初期化してから追加の属性を設定します。単一継承の基本例では super().メソッド() で親の動作を再利用できます。一般にはメソッド解決順序に従って次を探します。isinstance(サブクラスのインスタンス, 親クラス) は True です。この課では単一継承だけを使います。

## コード例

### 1. オーバーライドしていないメソッドの継承

```python
class Animal:
    def move(self):
        return "move"
class Dog(Animal):
    pass
print(Dog().move())
```

標準入力:

（空）

予想される出力:

```text
move
```

### 2. メソッドのオーバーライド

```python
class Animal:
    def speak(self):
        return "sound"
class Dog(Animal):
    def speak(self):
        return "woof"
print(Animal().speak(), Dog().speak())
```

標準入力:

（空）

予想される出力:

```text
sound woof
```

### 3. 親クラスの初期化と子クラスの属性

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

標準入力:

（空）

予想される出力:

```text
Ada 90 True
```

### 4. 親クラスの動作を拡張する

```python
class Base:
    def label(self):
        return "base"
class Child(Base):
    def label(self):
        return super().label() + "+child"
print(Child().label())
```

標準入力:

（空）

予想される出力:

```text
base+child
```

## よくある間違い

- サブクラスの __init__ で super を呼び忘れると、親クラスが必要とする属性が存在しないことがあります。
- オーバーライドしたメソッド内で self.同名メソッド() を呼ぶと自分を再び呼び出します。親の処理には super() を使います。

## 練習

### 1. 親クラス Animal の speak() は "sound" を返し、サブクラス Cat で "meow" にオーバーライドしてください。Cat の結果を出力します。

解答例:

```python
class Animal:
    def speak(self):
        return "sound"
class Cat(Animal):
    def speak(self):
        return "meow"
print(Cat().speak())
```

標準入力:

（空）

予想される出力:

```text
meow
```

解答の説明: サブクラスの同名メソッドが優先して見つかります。

### 2. 親クラス Item は name を初期化します。サブクラス PricedItem は super で name を初期化し、price を保存してください。("pen",3) を作って二つの属性を出力します。

解答例:

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

標準入力:

（空）

予想される出力:

```text
pen 3
```

解答の説明: 親クラスが共通の属性を管理し、サブクラスが価格の属性を追加します。

