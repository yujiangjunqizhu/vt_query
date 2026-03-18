# VirusTotal 增强版查询工具

VirusTotal 增强版查询工具，支持威胁情报查询、网页截图、HTML可视化报告和多种导出格式。

## 功能特性

- ✅ 支持多种查询类型：MD5、SHA1、SHA256、SHA512、IP、域名、URL
- ✅ 多API密钥轮询，避免速率限制
- ✅ 自动检测查询类型
- ✅ 网页截图功能（支持Chrome、Edge、Firefox）
- ✅ 按查询内容创建独立文件夹组织结果
- ✅ HTML可视化报告（含威胁等级、检测率进度条）
- ✅ 多格式导出：JSON、CSV、TXT、HTML
- ✅ Windows控制台UTF-8编码支持

## 安装依赖

```bash
pip install -r requirements.txt
```

## 使用方法

### 基本查询
```bash
# 查询IP地址
python vt_query_fixed.py 8.8.8.8

# 查询域名
python vt_query_fixed.py google.com

# 查询文件哈希
python vt_query_fixed.py c694c3c578678ac228f1c38f670969c0
```

### 导出结果
```bash
# 导出为JSON
python vt_query_fixed.py 8.8.8.8 --export json

# 导出为CSV
python vt_query_fixed.py 8.8.8.8 --export csv

# 导出为TXT
python vt_query_fixed.py 8.8.8.8 --export txt

# 导出为HTML报告
python vt_query_fixed.py 8.8.8.8 --export html

# 导出到独立文件夹（含截图和HTML报告）
python vt_query_fixed.py 8.8.8.8 --export separate
```

### 批量查询
```bash
# 从文件批量查询（每行一个查询项）
python vt_query_fixed.py --batch queries.txt
```

### 配置API密钥
```bash
# 添加API密钥
python vt_query_fixed.py --config add --key YOUR_API_KEY

# 查看已配置的API密钥
python vt_query_fixed.py --config list

# 清除所有API密钥
python vt_query_fixed.py --config clear

# 测试API密钥连接
python vt_query_fixed.py --config test
```

### 高级选项
```bash
# 禁用颜色输出
python vt_query_fixed.py 8.8.8.8 --no-color

# 禁用网页截图
python vt_query_fixed.py 8.8.8.8 --no-screenshot

# 指定查询类型
python vt_query_fixed.py c694c3c578678ac228f1c38f670969c0 --type md5
```

## API Key、配置文件与安全提示

### 是否需要 API Key
需要。该工具基于 VirusTotal 接口进行查询，正式使用前至少应准备一个可用的 VirusTotal API Key。

### 需要哪些 Key
- VirusTotal API Key

### 获取方式
可在 VirusTotal 官方平台注册账号后，在账户 / API 相关页面获取个人 API Key。使用前建议确认当前账号权限、调用额度与速率限制是否满足需要。

### 配置位置
- 示例配置文件：[`vt_config.example.json`](威胁情报自动查询/vt（终版）/vt_config.example.json)
- 实际配置文件：[`vt_config.json`](威胁情报自动查询/vt（终版）/vt_config.json)

当前示例中，API Key 放在 `api_keys` 数组中，例如：

```json
{
  "api_keys": [
    "YOUR_VIRUSTOTAL_API_KEY"
  ]
}
```

如果需要多 Key 轮换，可在同一数组中继续追加多个 Key。

### 安全提示
- 不要提交包含真实 Key 的 [`vt_config.json`](威胁情报自动查询/vt（终版）/vt_config.json)；
- 不要把真实查询结果、真实截图、真实 HTML 报告提交到仓库，尤其是 [`results/`](威胁情报自动查询/vt（终版）/results) 下内容；
- 若后续父任务统一建立结果归档大目录，建议将真实导出文件按工具和日期分类存放在受控目录中，不直接纳入版本控制。

## 网页截图功能说明

- **自动检测**：程序自动检测系统安装的浏览器（Chrome > Edge > Firefox）
- **无需配置**：无需手动指定浏览器，程序会自动选择可用的浏览器
- **快速失败**：如果未安装任何支持的浏览器，程序会跳过截图功能，不会卡顿
- **截图保存**：截图文件保存在查询结果文件夹中，文件名为 `screenshot.png`

### 浏览器安装要求
- **Chrome**：https://www.google.com/chrome/
- **Edge**：https://www.microsoft.com/edge
- **Firefox**：https://www.mozilla.org/firefox/

## 输出结果

每个查询都会创建独立文件夹，包含：
- `result.json` - 完整JSON数据
- `result.csv` - CSV格式数据
- `result.txt` - 文本报告
- `report.html` - 可视化HTML报告
- `screenshot.png` - 网页截图（如果启用）

## 示例输出

```
================================================================================
📊 VirusTotal 查询结果
================================================================================

🔍 基本信息:
------------------------------------------------------------
状态: 查询成功
查询内容: 8.8.8.8
查询类型: ip
查询时间: 2026-03-03 17:20:08

🎯 威胁分析:
------------------------------------------------------------
是否恶意: 否
是否高危: 否
恶意检测数: 0
未检测数: 35
总扫描引擎: 93
检测率: 0/93

📋 详细信息:
------------------------------------------------------------
文件类型: IP地址
最后分析时间: 2026-03-03 10:16:06

🔗 情报链接:
------------------------------------------------------------
https://www.virustotal.com/gui/ip-address/8.8.8.8
================================================================================
```

## 注意事项

1. 请确保已安装Python 3.6+环境
2. 首次使用时建议添加至少一个VirusTotal API密钥
3. 网页截图功能需要安装浏览器，但不是必需功能
4. 批量查询时程序会自动处理速率限制
5. 所有输出文件保存在 `results/` 目录下

## 贡献

欢迎提交问题和拉取请求！