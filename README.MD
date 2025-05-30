# CampNetwork 任务农场
原创作者：https://github.com/Buldozerch/CampNetwork
CampNetwork 平台的自动任务完成工具，包括 Twitter 集成功能。

## 主要特点

软件自动完成 CampNetwork 的任务：

- CampNetwork 平台上的常规任务
- Twitter 任务（关注）
- 支持多个账户
- 异步处理，高效处理大量账户
- 控制操作和任务之间的延迟
- 详细的任务完成统计

## 安装

### Windows
py -3.11 -m venv venv

venv\Scripts\activate

pip install -r requirements.txt

python main.py

### Linux/MacOS
python3.11 -m venv venv

source venv/bin/activate

pip install -r requirements.txt

MacOS 用户需要额外安装：
pip install greenlet

python main.py

## 使用方法

### 首次运行

首次运行 main.py 来创建 files/ 目录及其中的文件：
python main.py

### 运行前配置

- 在 files/private.txt 中填写私钥（每行一个密钥）
- 根据 env_example 创建 .env 文件并插入 capmonster.cloud 的 API 密钥（需要账户中有一些余额）
- 在 files/proxy.txt 中填写代理，格式为：http://log:pass@ip:port 或 log:pass@ip:port
- 如果要使用 Twitter 任务，在 files/twitter.txt 中填写 Twitter 令牌
- 可选：在 files/reserve_proxy.txt 和 files/reserve_twitter.txt 中添加备用代理和 Twitter 令牌
- 可选：在 files/ref_codes.txt 中添加推荐码
- 在 files/settings.json 中配置参数

### Settings.json

设置支持随机化。对于随机值，请指定 min/max 范围：

#### Twitter 设置
- `twitter.enabled` - 启用/禁用 Twitter 任务（true/false）
- `twitter.delay_between_actions` - Twitter 操作之间的延迟（秒）
- `twitter.delay_between_quests` - Twitter 任务之间的延迟（秒）

#### 常规设置
- `quests.delay_between_quests` - 常规任务之间的延迟（秒）

#### 推荐码设置
- `use_random_from_db` - 是否使用数据库中的随机推荐码
- `use_only_file_codes` - 是否仅使用文件中的推荐码

#### 钱包设置
- `wallets.range` - 要处理的钱包范围（start 和 end，end 为 0 表示全部）
- `wallets.startup_delay` - 账户启动之间的延迟（秒）

#### 资源设置
- `auto_replace` - 在出错时启用/禁用自动替换代理/Twitter（true/false）
- `max_failures` - 账户允许的最大自动替换次数

### 可用选项

1. **将钱包导入数据库**  
   将 private.txt 文件中的钱包添加到数据库。开始工作前必须执行。

2. **完成所有任务**  
   自动完成所有钱包的未完成任务。

3. **完成选定任务**  
   允许选择特定任务进行完成。

4. **显示统计信息**  
   显示所有钱包的统计信息，包括已完成任务的信息。

5. **资源管理**
   管理代理和 Twitter 令牌。

6. **推荐码管理**
   管理推荐码。
   
7. **设置**  
   交互式编辑程序设置。

8. **退出**  
   结束程序运行。

### 软件工作流程

1. 随机延迟启动账户
2. 在 CampNetwork 上登录
3. 检查未完成任务列表
4. 随机顺序完成常规任务
5. 如果启用了 Twitter 任务，连接 Twitter 并完成 Twitter 任务
6. 如果有错误和备用资源，在运行时替换它们
7. 将结果保存到数据库
8. 输出完成统计信息

## Twitter 模块功能

- 自动将 Twitter 账户连接到 CampNetwork
- 完成关注账户的任务
- 发布带有唯一标签的推文
- 点赞和转发指定的推文
- 错误处理和重试

## 系统要求

- Python 3.11+
- 活跃的 ETH 钱包
- 代理（可选，但推荐）
- Twitter 令牌（用于 Twitter 任务）

## 技术支持
TG 频道 https://t.me/annilumaoaridrop
GitHub: https://discord.gg/xpjFpug7


