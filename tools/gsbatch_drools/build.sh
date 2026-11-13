#!/usr/bin/env bash
# 编译 GsbatchDecide。Drools 依赖直接用 ~/.m2 里现成的（8.44.0.Final），
# 不联网、不需要 maven。JDK 找 ~/opt 下的 Temurin 17。
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
JAVA_HOME="${JAVA_HOME:-$HOME/opt/jdk-17.0.21+9}"
M2="$HOME/.m2/repository"

CP=$(find "$M2" -name "*.jar" | grep -v sources | grep -v javadoc | tr '\n' ':')

mkdir -p "$HERE/out"
"$JAVA_HOME/bin/javac" -encoding UTF-8 -cp "$CP" -d "$HERE/out" "$HERE/GsbatchDecide.java" "$HERE/Attempt.java" "$HERE/Decision.java"
cp "$HERE/decide.drl" "$HERE/out/"
echo "编译完成：$HERE/out"
