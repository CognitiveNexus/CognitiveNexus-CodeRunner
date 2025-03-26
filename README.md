# 思维脉络 Cognitive Nexus - C 语言代码执行后端

[![PHP 8.1](https://img.shields.io/badge/PHP-8.1-blue.svg)](https://www.php.net/)
[![Docker](https://img.shields.io/badge/Docker-CE-blue.svg)](https://www.docker.com/)

这是 [思维脉络](https://github.com/CognitiveNexus) 项目的 C 语言代码执行后端仓库，基于 PHP 和 Docker 构建。

## 项目概述

本项目提供了一个安全的 C 语言代码执行环境，通过以下技术栈实现：

-   **PHP**：作为 HTTP 请求的接收和处理层，负责解析用户提交的代码并调用 Docker 执行环境。
-   **Docker CE**：提供隔离的代码执行环境，确保用户代码不会影响主机系统。
-   **GCC**：用于编译用户提交的 C 语言代码。
-   **GDB**：通过 GDB Python API 监控和分析代码执行过程。

> **警告** 本项目允许用户提交并执行 C 语言代码，尽管已采取安全措施，但仍可能存在潜在风险。

## 运行环境

-   **PHP 8.1** 或更高版本
-   **Docker CE**

## 快速开始

本项目主要支持 Ubuntu 22.04 LTS，但也适用于其他 Linux 发行版，可参考相关文档进行配置。

### 1. 克隆项目

```bash
git clone git@github.com:CognitiveNexus/CognitiveNexus-CodeRunner
cd CognitiveNexus-CodeRunner
```

### 2. 安装并配置 PHP

1.  安装 `php-fpm`：

    ```bash
    sudo apt-get install php8.1-fpm php8.1-uuid composer
    ```

2.  安装 Composer 依赖：

    ```bash
    cd api/
    composer install
    ```

3.  配置 HTTP 服务器：

    -   将 `api/public/` 设置为服务器根目录。
    -   配置服务器与 `php-fpm` 的通信，确保能够执行 PHP 脚本。
    -   推荐使用 Nginx 作为 HTTP 服务器。
    -   若需更高安全性，可配置为仅监听本地地址（`127.0.0.1`），将请求通过外部脚本进行请求鉴权后转发至当前服务器。

### 3. 安装并配置 Docker

1.  安装 [Docker CE](https://docs.docker.com/engine/install/ubuntu/#install-using-the-repository)
2.  构建 Docker 镜像：

    ```bash
    ./build.sh
    ```

### 4. 启动服务

完成上述配置后，启动 HTTP 服务器即可访问服务。更详细的说明可以参考下方[接口说明](#接口说明)。

## 项目结构

```
CognitiveNexus-CodeRunner
├── api/                    # PHP 后端代码
│   ├── composer.json
│   ├── composer.lock
│   ├── public/             # HTTP 服务器根目录
│   │   ├── index.html      # 简易的接口测试页
│   │   └── run.php         # 处理请求并调用 Docker 执行环境
│   └── vendor/
├── build.sh                # 初始化项目，即构建 Docker 镜像并创建沙盒文件夹
├── docker/                 # Docker 相关文件
│   ├── Dockerfile          # Docker 镜像构建文件
│   └── scripts/
│       ├── compile.sh
│       ├── run.sh
│       ├── start.sh
│       └── tracer.py       # GDB 调试脚本，用于监控和分析代码执行过程
├── README.md
├── tests/                  # 用于测试接口的 C 语言代码，后续可能会设计自动化测试流程
└── tmp/                    # 文件沙盒，用于存储用户提交的代码和临时文件
```

## 接口说明

### 请求

`run.php` 接收 HTTP POST 请求，请求体需为 `json` 格式，包含以下内容：

```jsonc
{
    "code": "int main() {\n...",    // C 语言代码
    "stdin": "1 1 4 5 1 4",         // 标准输入流
    "usst": "1906"                  // 神秘的数字
}
```

### 返回数据

返回的数据同样为 `json` 格式，包含以下字段：

```jsonc
{
    "status": "success",    // 或 "error"
    "data": { /* ... */ },  // 调试结果，仅当 status 为 success 时存在
    "message": "...",       // 错误消息，仅当 status 为 error 时存在
    "logs": {
        "compile": "...",   // GCC 编译输出
        "run": "..."        // GDB 运行输出
    }
}
```

#### 字段说明

-   `status`

    值为 `"success"` 时，表示代码已成功编译、执行并完成调试，但不保证调试过程中没有问题。调试结果存储在 `data` 字段中。

-   `data`

    包含以下内容：

    ```jsonc
    {
        "typeDefinitions": { /* ... */ },    // 类型定义
        "steps": [ /* ... */ ],             // 每一步执行的数据
        "endState": "finished"              // 或 "timeout" 或 "overstep" 或 "aborted"
    }
    ```

-   `data.endState`

    表示调试的结束状态：

    -   `"finished"`：程序正常结束。
    -   `"timeout"`：程序运行超出 5 秒的时间限制，因而被中止。
    -   `"overstep"`：程序运行超出 500 步的执行限制，因而被中止。
    -   `"aborted"`: 程序收到异常退出信号（如 `SIGINT`、`SIGSEGV`），因而被中止。
    
    注意，由于 `SIGKILL` 无法被 GDB 捕获，若程序因 `SIGKILL` 被中止（通常是因为内存不足），`endState` 仍会被标记为 `"finished"`。此时需结合 Run Log 中的 `SIGKILL` 记录判断实际退出原因。

    即使 `endState` 非 `"finished"`，已执行部分的数据仍会完整存储在 `struct` 和 `steps` 中。

-   `data.typeDefinitions`

    包含程序中各个变量类型的详细信息。

-   `data.step`

    包含每一步执行的详细信息。
    
更具体的结构可以参见结果的 [TypeScript 类型定义](https://github.com/CognitiveNexus/CognitiveNexus-CodeRunnerFrontend/blob/main/src/types/CodeRunnerTypes.ts)。

## 已知问题

-   暂不支持：枚举、位域、函数指针类型。
-   暂不支持通过 malloc() 创建的、用法类似数组的指针。
