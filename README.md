# 思维脉络 Cognitive Nexus

这是 [思维脉络](https://github.com/CognitiveNexus) 的 C 语言变量追踪工具仓库。尚在建设中。

### 运行环境

本项目基于 Ubuntu 22.04.5 LTS 开发。使用 WSL 或许也能跑。

### 使用方法

1. 安装依赖：`$ sudo apt-get install python3 gcc gdb expect`
2. 编写 `code.c`
3. 编译：`$ ./compile.sh`
4. 运行：`$ ./run.sh`
5. 结果将储存在 `dump.json` 中