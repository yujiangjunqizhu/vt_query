#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VirusTotal 增强版查询工具 - 完整修复版
修复API密钥保存问题和404错误处理
新增：网页截图功能、按查询内容组织结果、HTML可视化报告
"""

import sys
import os
import io
import json
import csv
import time
import base64
import re
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import argparse
from dataclasses import dataclass
import shutil

# 设置Windows控制台UTF-8编码
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ==================== 配置管理 ====================

@dataclass
class VTConfig:
    """VT配置类"""
    api_keys: List[str] = None
    timeout: int = 30
    max_retries: int = 3
    rate_limit_delay: float = 1.0
    enable_color: bool = True
    output_dir: str = "results"
    enable_screenshot: bool = True
    screenshot_timeout: int = 30
    
    def __post_init__(self):
        if self.api_keys is None:
            self.api_keys = []
    
    @classmethod
    def load_from_file(cls, config_file: str = "vt_config.json") -> "VTConfig":
        """从文件加载配置"""
        default_config = {
            "api_keys": [],
            "timeout": 30,
            "max_retries": 3,
            "rate_limit_delay": 1.0,
            "enable_color": True,
            "output_dir": "results",
            "enable_screenshot": True,
            "screenshot_timeout": 30
        }
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    default_config.update(user_config)
            except:
                pass
        
        return cls(**default_config)
    
    def save_to_file(self, config_file: str = "vt_config.json") -> bool:
        """保存配置到文件（包含API密钥）"""
        try:
            # 创建完整配置（包含API密钥）
            full_config = {
                "api_keys": self.api_keys,
                "timeout": self.timeout,
                "max_retries": self.max_retries,
                "rate_limit_delay": self.rate_limit_delay,
                "enable_color": self.enable_color,
                "output_dir": self.output_dir,
                "enable_screenshot": self.enable_screenshot,
                "screenshot_timeout": self.screenshot_timeout
            }
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(full_config, f, indent=2, ensure_ascii=False)
            return True
        except:
            return False

# ==================== API密钥管理器 ====================

class APIKeyManager:
    """API密钥管理器（多Key轮询）"""
    
    def __init__(self, config: VTConfig):
        self.config = config
        self.keys = config.api_keys.copy()
        self.current_index = 0
    
    def get_next_key(self) -> Optional[str]:
        """获取下一个可用的API密钥"""
        if not self.keys:
            return None
        
        key = self.keys[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.keys)
        return key

# ==================== 网页截图器 ====================

class WebScreenshot:
    """网页截图器 - 支持多种浏览器"""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.driver = None
        self.available = False
        self._init_error = None
        self.browser_type = None  # 使用的浏览器类型
        self._check_availability()
    
    def _check_availability(self):
        """检查截图功能是否可用（快速检查，不初始化浏览器）"""
        try:
            from selenium import webdriver
            # 只检查selenium是否安装，不初始化浏览器
            self.available = True
        except ImportError:
            self.available = False
            self._init_error = "selenium未安装"
            print("   ℹ️  selenium未安装，截图功能不可用")
            print("   提示: 运行 'pip install selenium' 安装")
    
    def _get_browser_paths(self):
        """获取各浏览器的安装路径"""
        import platform
        import os
        
        system = platform.system()
        browsers = {
            'chrome': [],
            'edge': [],
            'firefox': []
        }
        
        if system == 'Windows':
            # Chrome
            browsers['chrome'] = [
                os.path.join(os.environ.get('PROGRAMFILES', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'Application', 'chrome.exe'),
            ]
            # Edge
            browsers['edge'] = [
                os.path.join(os.environ.get('PROGRAMFILES', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
            ]
            # Firefox
            browsers['firefox'] = [
                os.path.join(os.environ.get('PROGRAMFILES', ''), 'Mozilla Firefox', 'firefox.exe'),
                os.path.join(os.environ.get('PROGRAMFILES(X86)', ''), 'Mozilla Firefox', 'firefox.exe'),
            ]
        elif system == 'Darwin':  # macOS
            browsers['chrome'] = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
            browsers['edge'] = ['/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']
            browsers['firefox'] = ['/Applications/Firefox.app/Contents/MacOS/firefox']
        else:  # Linux
            browsers['chrome'] = ['/usr/bin/google-chrome', '/usr/bin/chromium-browser', '/usr/bin/chromium']
            browsers['edge'] = ['/usr/bin/microsoft-edge', '/usr/bin/microsoft-edge-stable']
            browsers['firefox'] = ['/usr/bin/firefox', '/usr/bin/firefox-esr']
        
        return browsers
    
    def _check_browser_available(self):
        """快速检查是否有可用的浏览器"""
        browsers = self._get_browser_paths()
        
        # 按优先级检查：Chrome > Edge > Firefox
        for browser_type in ['chrome', 'edge', 'firefox']:
            for path in browsers[browser_type]:
                if os.path.exists(path):
                    return browser_type
        
        return None
    
    def _init_driver(self):
        """初始化浏览器驱动（支持多种浏览器）"""
        if not self.available:
            return False
        
        # 如果之前初始化失败，直接返回
        if self._init_error:
            return False
        
        # 检查可用的浏览器
        available_browser = self._check_browser_available()
        if not available_browser:
            self._init_error = "未找到支持的浏览器"
            self.available = False
            print("   ⚠️  未检测到支持的浏览器（Chrome/Edge/Firefox），跳过截图功能")
            return False
        
        # 按优先级尝试初始化浏览器
        browser_priority = ['chrome', 'edge', 'firefox']
        
        for browser_type in browser_priority:
            if browser_type == available_browser:
                if self._try_init_browser(browser_type):
                    return True
        
        # 如果首选浏览器失败，尝试其他浏览器
        for browser_type in browser_priority:
            if browser_type != available_browser:
                if self._try_init_browser(browser_type):
                    return True
        
        self._init_error = "所有浏览器初始化失败"
        self.available = False
        print("   ⚠️  所有浏览器初始化失败，跳过截图功能")
        return False
    
    def _try_init_browser(self, browser_type: str) -> bool:
        """尝试初始化指定类型的浏览器"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.edge.options import Options as EdgeOptions
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
            
            print(f"   ⏳ 正在尝试初始化 {browser_type.upper()} 浏览器...")
            
            if browser_type == 'chrome':
                options = ChromeOptions()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                options.add_argument('--window-size=1920,1080')
                options.add_argument('--hide-scrollbars')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-logging')
                options.add_argument('--log-level=3')
                options.add_experimental_option('excludeSwitches', ['enable-logging'])
                
                self.driver = webdriver.Chrome(options=options)
                self.browser_type = 'Chrome'
                print(f"   ✅ Chrome浏览器初始化成功")
                return True
                
            elif browser_type == 'edge':
                options = EdgeOptions()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--disable-gpu')
                options.add_argument('--window-size=1920,1080')
                options.add_argument('--hide-scrollbars')
                options.add_argument('--disable-extensions')
                options.add_argument('--disable-logging')
                options.add_argument('--log-level=3')
                options.add_experimental_option('excludeSwitches', ['enable-logging'])
                
                self.driver = webdriver.Edge(options=options)
                self.browser_type = 'Edge'
                print(f"   ✅ Edge浏览器初始化成功")
                return True
                
            elif browser_type == 'firefox':
                options = FirefoxOptions()
                options.add_argument('--headless')
                options.add_argument('--no-sandbox')
                options.add_argument('--disable-dev-shm-usage')
                options.add_argument('--window-size=1920,1080')
                
                self.driver = webdriver.Firefox(options=options)
                self.browser_type = 'Firefox'
                print(f"   ✅ Firefox浏览器初始化成功")
                return True
                
        except Exception as e:
            error_msg = str(e)
            print(f"   ⚠️  {browser_type.upper()}初始化失败: {error_msg}")
            return False
        
        return False
    
    def take_screenshot(self, url: str, output_path: str, wait_time: int = 5) -> bool:
        """截取网页截图"""
        if not self.available:
            return False
        
        if self.driver is None:
            if not self._init_driver():
                return False
        
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            self.driver.get(url)
            
            # 等待页面加载
            time.sleep(wait_time)
            
            # 截图
            self.driver.save_screenshot(output_path)
            return True
        except Exception as e:
            print(f"⚠️  截图失败: {str(e)}")
            return False
    
    def close(self):
        """关闭浏览器"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
    
    def __del__(self):
        self.close()

# ==================== VT查询器 ====================

class VTQuery:
    """VirusTotal查询器"""
    
    def __init__(self, config: VTConfig):
        self.config = config
        self.key_manager = APIKeyManager(config)
        self.base_url = "https://www.virustotal.com/api/v3"
        
        # 创建会话
        import requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'VTQuery/1.0',
            'Accept': 'application/json'
        })
    
    def detect_type(self, query: str) -> str:
        """检测查询类型"""
        query = query.strip().lower()
        
        # 文件哈希
        if re.match(r'^[a-f0-9]{32}$', query):
            return 'md5'
        if re.match(r'^[a-f0-9]{40}$', query):
            return 'sha1'
        if re.match(r'^[a-f0-9]{64}$', query):
            return 'sha256'
        if re.match(r'^[a-f0-9]{128}$', query):
            return 'sha512'
        
        # IP地址
        ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
        if re.match(ip_pattern, query):
            parts = query.split('.')
            if all(0 <= int(part) <= 255 for part in parts):
                return 'ip'
        
        # 域名
        domain_pattern = r'^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$'
        if re.match(domain_pattern, query) and '://' not in query:
            return 'domain'
        
        # URL
        url_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        if re.match(url_pattern, query):
            return 'url'
        
        return 'unknown'
    
    def query(self, query: str, query_type: str = None) -> Dict[str, Any]:
        """执行查询"""
        if query_type is None:
            query_type = self.detect_type(query)
        
        if query_type == 'unknown':
            return {"状态": "查询失败", "错误信息": f"无法识别查询类型: {query}"}
        
        max_attempts = min(len(self.key_manager.keys), 3) or 1
        
        for attempt in range(max_attempts):
            api_key = self.key_manager.get_next_key()
            if not api_key:
                return {"状态": "查询失败", "错误信息": "没有可用的API密钥"}
            
            try:
                # 构造请求
                headers = {"x-apikey": api_key}
                
                if query_type in ['md5', 'sha1', 'sha256', 'sha512']:
                    url = f"{self.base_url}/files/{query}"
                elif query_type == 'ip':
                    url = f"{self.base_url}/ip_addresses/{query}"
                elif query_type == 'domain':
                    url = f"{self.base_url}/domains/{query}"
                elif query_type == 'url':
                    url_id = base64.urlsafe_b64encode(query.encode()).decode().strip("=")
                    url = f"{self.base_url}/urls/{url_id}"
                else:
                    return {"状态": "查询失败", "错误信息": f"不支持的查询类型: {query_type}"}
                
                # 发送请求
                time.sleep(self.config.rate_limit_delay)
                response = self.session.get(url, headers=headers, timeout=self.config.timeout)
                
                if response.status_code == 429:  # 频率限制
                    continue
                
                # 处理404错误（记录不存在）
                if response.status_code == 404:
                    return {
                        "状态": "未找到", 
                        "错误信息": f"该{query_type}在VirusTotal数据库中不存在",
                        "查询内容": query,
                        "查询类型": query_type,
                        "查询时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "情报链接": self._get_vt_link(query, query_type)
                    }
                
                response.raise_for_status()
                data = response.json()
                
                # 解析结果
                return self.parse_result(data, query, query_type)
                
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    continue
                
                # 处理其他HTTP错误
                if "404" in str(e):
                    return {"状态": "未找到", "错误信息": f"该{query_type}在VirusTotal数据库中不存在: {query}"}
                
                return {"状态": "查询失败", "错误信息": str(e)}
        
        return {"状态": "查询失败", "错误信息": "所有API密钥都达到限制"}
    
    def parse_result(self, data: Dict, query: str, query_type: str) -> Dict[str, Any]:
        """解析查询结果"""
        try:
            if 'data' not in data or 'attributes' not in data['data']:
                return {"状态": "查询失败", "错误信息": "无效的API响应"}
            
            attrs = data['data']['attributes']
            stats = attrs.get('last_analysis_stats', {})
            
            malicious = stats.get('malicious', 0)
            total = sum(stats.values())
            
            # 基础信息
            result = {
                "状态": "查询成功",
                "是否恶意": malicious > 0,
                "恶意检测数": malicious,
                "未检测数": stats.get('undetected', 0),
                "总扫描引擎": total,
                "检测率": f"{malicious}/{total}" if total > 0 else "0/0",
                "检测百分比": 0.0,
                "查询内容": query,
                "查询类型": query_type,
                "查询时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "最后分析时间": self._timestamp_to_str(attrs.get('last_analysis_date')),
                "首次提交时间": self._timestamp_to_str(attrs.get('first_submission_date')),
                "最后提交时间": self._timestamp_to_str(attrs.get('last_submission_date')),
                "提交次数": attrs.get('times_submitted', 0),
                "情报链接": self._get_vt_link(query, query_type),
                "是否高危": False,
            }
            
            # 计算检测百分比
            if total > 0:
                result["检测百分比"] = round((malicious / total) * 100, 2)
            
            # 是否高危
            if malicious > 10 or result["检测百分比"] > 50:
                result["是否高危"] = True
            
            # 威胁分类
            threat_categories = []
            
            # 从引擎结果中提取分类
            last_analysis = attrs.get('last_analysis_results', {})
            for engine, engine_result in last_analysis.items():
                category = engine_result.get('category', '')
                if category == 'malicious':
                    result_str = engine_result.get('result', '').lower()
                    if 'trojan' in result_str:
                        threat_categories.append('木马')
                    elif 'worm' in result_str:
                        threat_categories.append('蠕虫')
                    elif 'virus' in result_str:
                        threat_categories.append('病毒')
                    elif 'backdoor' in result_str:
                        threat_categories.append('后门程序')
                    elif 'adware' in result_str:
                        threat_categories.append('广告软件')
                    elif 'spyware' in result_str:
                        threat_categories.append('间谍软件')
                    elif 'ransomware' in result_str:
                        threat_categories.append('勒索软件')
                    elif 'downloader' in result_str:
                        threat_categories.append('下载器')
                    elif 'riskware' in result_str:
                        threat_categories.append('风险软件')
                    elif 'grayware' in result_str:
                        threat_categories.append('灰色软件')
                    elif 'malware' in result_str:
                        threat_categories.append('恶意软件')
            
            # 去重
            threat_categories = list(set(threat_categories))
            result["威胁分类"] = ",".join(threat_categories) if threat_categories else "未知"
            
            # 流行威胁分类
            popular = attrs.get('popular_threat_classification', {})
            if popular:
                suggested = popular.get('suggested_threat_label', '')
                if suggested:
                    result["流行威胁分类"] = suggested
            
            # 文件特定信息
            if query_type in ['md5', 'sha1', 'sha256', 'sha512']:
                result.update({
                    "文件类型": attrs.get('type_description', '未知'),
                    "文件大小": attrs.get('size', 0),
                    "标签": ",".join(attrs.get('tags', [])),
                    "签名信息": attrs.get('signature_info', {}).get('description', '')
                })
                
                # PE信息
                pe_info = attrs.get('pe_info', {})
                if pe_info:
                    result["PE信息"] = {
                        "时间戳": self._timestamp_to_str(pe_info.get('timestamp')),
                        "导入哈希": pe_info.get('imphash', ''),
                        "机器类型": pe_info.get('machine_type', '')
                    }
                
                # 沙箱结果
                sandbox_verdicts = attrs.get('sandbox_verdicts', {})
                if sandbox_verdicts:
                    result["沙箱结果"] = {}
                    for sandbox, verdict in sandbox_verdicts.items():
                        if isinstance(verdict, dict):
                            result["沙箱结果"][sandbox] = {
                                "类别": verdict.get('category', ''),
                                "置信度": verdict.get('confidence', 0)
                            }
            
            # IP/域名特定信息
            elif query_type in ['ip', 'domain']:
                result["标签"] = ",".join(attrs.get('tags', []))
                result["文件类型"] = "IP地址" if query_type == 'ip' else "域名"
                result["文件大小"] = "N/A"
            
            return result
            
        except Exception as e:
            return {"状态": "解析失败", "错误信息": str(e)}
    
    def _timestamp_to_str(self, timestamp: int) -> str:
        """时间戳转字符串"""
        if timestamp:
            try:
                return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass
        return "N/A"
    
    def _get_vt_link(self, query: str, query_type: str) -> str:
        """获取VT链接"""
        if query_type in ['md5', 'sha1', 'sha256', 'sha512']:
            return f"https://www.virustotal.com/gui/file/{query}"
        elif query_type == 'ip':
            return f"https://www.virustotal.com/gui/ip-address/{query}"
        elif query_type == 'domain':
            return f"https://www.virustotal.com/gui/domain/{query}"
        elif query_type == 'url':
            url_id = base64.urlsafe_b64encode(query.encode()).decode().strip("=")
            return f"https://www.virustotal.com/gui/url/{url_id}"
        return ""

# ==================== 结果展示 ====================

class ResultDisplay:
    """结果展示器"""
    
    def __init__(self, enable_color: bool = True):
        self.enable_color = enable_color
        
        # 颜色配置
        if enable_color:
            self.COLORS = {
                'title': '\033[96m',      # 青色
                'header': '\033[94m',     # 蓝色
                'key': '\033[92m',        # 绿色
                'value': '\033[93m',      # 黄色
                'danger': '\033[91m',     # 红色
                'safe': '\033[92m',       # 绿色
                'warning': '\033[93m',    # 黄色
                'info': '\033[96m',       # 青色
                'reset': '\033[0m',       # 重置
                'line': '\033[90m'        # 灰色
            }
        else:
            self.COLORS = {k: '' for k in ['title', 'header', 'key', 'value', 'danger', 'safe', 'warning', 'info', 'reset', 'line']}
    
    def display(self, result: Dict[str, Any]):
        """显示结果"""
        if result.get('状态') == '未找到':
            self._display_not_found(result)
            return
        elif '错误信息' in result:
            self._display_error(result)
            return
        
        self._display_header()
        self._display_basic_info(result)
        self._display_threat_info(result)
        self._display_detailed_info(result)
        self._display_footer(result)
    
    def _display_error(self, result: Dict):
        """显示错误信息"""
        print(f"\n{self.COLORS['danger']}❌ {result.get('状态', '错误')}: {result.get('错误信息', '未知错误')}{self.COLORS['reset']}")
    
    def _display_not_found(self, result: Dict):
        """显示未找到信息"""
        print(f"\n{self.COLORS['warning']}⚠️  {result.get('状态', '未找到')}: {result.get('错误信息', '记录不存在')}{self.COLORS['reset']}")
        print(f"{self.COLORS['info']}查询内容: {result.get('查询内容', 'N/A')}{self.COLORS['reset']}")
        print(f"{self.COLORS['info']}查询类型: {result.get('查询类型', 'N/A')}{self.COLORS['reset']}")
        print(f"{self.COLORS['info']}查询时间: {result.get('查询时间', 'N/A')}{self.COLORS['reset']}")
        
        vt_link = result.get('情报链接')
        if vt_link:
            print(f"\n{self.COLORS['info']}情报链接: {vt_link}{self.COLORS['reset']}")
    
    def _display_header(self):
        """显示头部信息"""
        print(f"\n{self.COLORS['title']}{'='*80}{self.COLORS['reset']}")
        print(f"{self.COLORS['title']}📊 VirusTotal 查询结果{self.COLORS['reset']}")
        print(f"{self.COLORS['title']}{'='*80}{self.COLORS['reset']}")
        print()
    
    def _display_basic_info(self, result: Dict):
        """显示基础信息"""
        print(f"{self.COLORS['header']}🔍 基本信息:{self.COLORS['reset']}")
        print(f"{self.COLORS['line']}{'-'*60}{self.COLORS['reset']}")
        
        # 状态
        print(f"{self.COLORS['key']}状态:{self.COLORS['reset']} {self.COLORS['safe']}{result.get('状态', 'N/A')}{self.COLORS['reset']}")
        
        # 查询信息
        print(f"{self.COLORS['key']}查询内容:{self.COLORS['reset']} {self.COLORS['value']}{result.get('查询内容', 'N/A')}{self.COLORS['reset']}")
        print(f"{self.COLORS['key']}查询类型:{self.COLORS['reset']} {self.COLORS['value']}{result.get('查询类型', 'N/A')}{self.COLORS['reset']}")
        print(f"{self.COLORS['key']}查询时间:{self.COLORS['reset']} {self.COLORS['value']}{result.get('查询时间', 'N/A')}{self.COLORS['reset']}")
        print()
    
    def _display_threat_info(self, result: Dict):
        """显示威胁信息"""
        print(f"{self.COLORS['header']}🎯 威胁分析:{self.COLORS['reset']}")
        print(f"{self.COLORS['line']}{'-'*60}{self.COLORS['reset']}")
        
        # 是否恶意
        is_malicious = result.get('是否恶意', False)
        malicious_color = self.COLORS['danger'] if is_malicious else self.COLORS['safe']
        malicious_text = "是" if is_malicious else "否"
        print(f"{self.COLORS['key']}是否恶意:{self.COLORS['reset']} {malicious_color}{malicious_text}{self.COLORS['reset']}")
        
        # 是否高危
        is_high_risk = result.get('是否高危', False)
        high_risk_color = self.COLORS['danger'] if is_high_risk else self.COLORS['safe']
        high_risk_text = "是" if is_high_risk else "否"
        print(f"{self.COLORS['key']}是否高危:{self.COLORS['reset']} {high_risk_color}{high_risk_text}{self.COLORS['reset']}")
        
        # 检测统计
        malicious = result.get('恶意检测数', 0)
        total = result.get('总扫描引擎', 0)
        undetected = result.get('未检测数', 0)
        
        print(f"{self.COLORS['key']}恶意检测数:{self.COLORS['reset']} {self.COLORS['danger'] if malicious > 0 else self.COLORS['safe']}{malicious}{self.COLORS['reset']}")
        print(f"{self.COLORS['key']}未检测数:{self.COLORS['reset']} {self.COLORS['warning']}{undetected}{self.COLORS['reset']}")
        print(f"{self.COLORS['key']}总扫描引擎:{self.COLORS['reset']} {self.COLORS['info']}{total}{self.COLORS['reset']}")
        
        # 检测率
        detection_rate = result.get('检测率', 'N/A')
        detection_percent = result.get('检测百分比', 0)
        
        if detection_percent > 0:
            color = self.COLORS['danger'] if detection_percent > 50 else self.COLORS['warning'] if detection_percent > 20 else self.COLORS['safe']
            print(f"{self.COLORS['key']}检测率:{self.COLORS['reset']} {color}{detection_rate} ({detection_percent}%){self.COLORS['reset']}")
        else:
            print(f"{self.COLORS['key']}检测率:{self.COLORS['reset']} {self.COLORS['safe']}{detection_rate}{self.COLORS['reset']}")
        
        # 威胁分类
        threat_category = result.get('威胁分类', '未知')
        if threat_category != '未知':
            print(f"{self.COLORS['key']}威胁分类:{self.COLORS['reset']} {self.COLORS['danger']}{threat_category}{self.COLORS['reset']}")
        
        # 流行威胁分类
        popular_threat = result.get('流行威胁分类')
        if popular_threat:
            print(f"{self.COLORS['key']}流行威胁分类:{self.COLORS['reset']} {self.COLORS['warning']}{popular_threat}{self.COLORS['reset']}")
        
        print()
    
    def _display_detailed_info(self, result: Dict):
        """显示详细信息"""
        print(f"{self.COLORS['header']}📋 详细信息:{self.COLORS['reset']}")
        print(f"{self.COLORS['line']}{'-'*60}{self.COLORS['reset']}")
        
        # 文件信息
        print(f"{self.COLORS['key']}文件类型:{self.COLORS['reset']} {self.COLORS['value']}{result.get('文件类型', 'N/A')}{self.COLORS['reset']}")
        
        file_size = result.get('文件大小')
        if file_size and file_size != 'N/A' and isinstance(file_size, (int, float)):
            print(f"{self.COLORS['key']}文件大小:{self.COLORS['reset']} {self.COLORS['value']}{self._format_size(file_size)}{self.COLORS['reset']}")
        
        # 标签
        tags = result.get('标签')
        if tags:
            print(f"{self.COLORS['key']}标签:{self.COLORS['reset']} {self.COLORS['info']}{tags}{self.COLORS['reset']}")
        
        # 时间信息
        time_fields = ['最后分析时间', '首次提交时间', '最后提交时间']
        for field in time_fields:
            value = result.get(field)
            if value and value != 'N/A':
                print(f"{self.COLORS['key']}{field}:{self.COLORS['reset']} {self.COLORS['value']}{value}{self.COLORS['reset']}")
        
        # 提交次数
        times_submitted = result.get('提交次数')
        if times_submitted:
            print(f"{self.COLORS['key']}提交次数:{self.COLORS['reset']} {self.COLORS['value']}{times_submitted}{self.COLORS['reset']}")
        
        # 签名信息
        signature = result.get('签名信息')
        if signature:
            print(f"{self.COLORS['key']}签名信息:{self.COLORS['reset']} {self.COLORS['value']}{signature}{self.COLORS['reset']}")
        
        # PE信息
        pe_info = result.get('PE信息')
        if isinstance(pe_info, dict) and pe_info:
            print(f"{self.COLORS['key']}PE信息:{self.COLORS['reset']}")
            for key, value in pe_info.items():
                if value:
                    print(f"  {self.COLORS['key']}{key}:{self.COLORS['reset']} {self.COLORS['value']}{value}{self.COLORS['reset']}")
        
        # 沙箱结果
        sandbox = result.get('沙箱结果')
        if isinstance(sandbox, dict) and sandbox:
            print(f"{self.COLORS['key']}沙箱结果:{self.COLORS['reset']}")
            for sandbox_name, verdict in sandbox.items():
                if isinstance(verdict, dict):
                    category = verdict.get('类别', 'unknown')
                    confidence = verdict.get('置信度', 0)
                    print(f"  {self.COLORS['key']}{sandbox_name}:{self.COLORS['reset']} {self.COLORS['value']}{category} (置信度: {confidence}){self.COLORS['reset']}")
        
        print()
    
    def _display_footer(self, result: Dict):
        """显示底部信息"""
        vt_link = result.get('情报链接')
        if vt_link:
            print(f"{self.COLORS['header']}🔗 情报链接:{self.COLORS['reset']}")
            print(f"{self.COLORS['line']}{'-'*60}{self.COLORS['reset']}")
            print(f"{self.COLORS['info']}{vt_link}{self.COLORS['reset']}")
        
        print(f"\n{self.COLORS['title']}{'='*80}{self.COLORS['reset']}")
    
    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"

# ==================== 结果导出 ====================

class ResultExporter:
    """结果导出器（中文字段）- 按查询内容组织文件夹"""
    
    def __init__(self, output_dir: str = "results"):
        self.output_dir = output_dir
        self.results = []
        self.screenshotter = None
        
        # 创建输出目录
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
    
    def init_screenshot(self, timeout: int = 30):
        """初始化截图功能"""
        if self.screenshotter is None:
            print("📸 正在初始化截图功能...")
            self.screenshotter = WebScreenshot(timeout)
            if not self.screenshotter.available:
                print("   ℹ️  截图功能不可用，将跳过网页截图")
        return self.screenshotter.available
    
    def add_result(self, result: Dict):
        """添加结果"""
        self.results.append(result)
    
    def _get_safe_filename(self, query: str) -> str:
        """获取安全的文件名"""
        # 替换不安全的字符
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', query)
        # 限制长度
        if len(safe_name) > 100:
            safe_name = safe_name[:100]
        return safe_name
    
    def _create_query_folder(self, query: str) -> str:
        """为查询创建独立文件夹"""
        safe_name = self._get_safe_filename(query)
        folder_path = os.path.join(self.output_dir, safe_name)
        
        # 如果文件夹已存在，添加时间戳
        if os.path.exists(folder_path):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            folder_path = f"{folder_path}_{timestamp}"
        
        os.makedirs(folder_path, exist_ok=True)
        return folder_path
    
    def export_single_result(self, result: Dict, export_format: str = 'all') -> Dict[str, str]:
        """导出单个结果到独立文件夹"""
        query = result.get('查询内容', 'unknown')
        folder_path = self._create_query_folder(query)
        exported_files = {}
        
        try:
            # 保存截图（仅在截图功能可用时）
            if self.screenshotter and self.screenshotter.available and result.get('情报链接'):
                screenshot_path = os.path.join(folder_path, "screenshot.png")
                print("   ⏳ 正在截取网页截图...")
                if self.screenshotter.take_screenshot(result['情报链接'], screenshot_path):
                    exported_files['screenshot'] = screenshot_path
                    result['截图路径'] = screenshot_path
                    print(f"   ✅ 截图完成（使用 {self.screenshotter.browser_type} 浏览器）")
                else:
                    print("   ⚠️  截图失败，跳过")
            
            # 导出JSON
            if export_format in ['all', 'json']:
                json_path = os.path.join(folder_path, "result.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                exported_files['json'] = json_path
            
            # 导出CSV
            if export_format in ['all', 'csv']:
                csv_path = os.path.join(folder_path, "result.csv")
                self._export_single_csv(result, csv_path)
                exported_files['csv'] = csv_path
            
            # 导出HTML报告
            if export_format in ['all', 'html']:
                html_path = os.path.join(folder_path, "report.html")
                self._export_html_report(result, html_path)
                exported_files['html'] = html_path
            
            # 导出TXT
            if export_format in ['all', 'txt']:
                txt_path = os.path.join(folder_path, "report.txt")
                self._export_single_txt(result, txt_path)
                exported_files['txt'] = txt_path
            
            exported_files['folder'] = folder_path
            
        except Exception as e:
            print(f"❌ 导出失败: {str(e)}")
        
        return exported_files
    
    def _export_single_csv(self, result: Dict, filepath: str):
        """导出单个结果为CSV"""
        fieldnames = [
            '状态', '是否恶意', '是否高危', '恶意检测数', '未检测数', 
            '总扫描引擎', '检测率', '检测百分比', '威胁分类', '流行威胁分类',
            '查询内容', '查询类型', '查询时间', '文件类型', '文件大小',
            '标签', '最后分析时间', '首次提交时间', '最后提交时间', '提交次数',
            '签名信息', '情报链接'
        ]
        
        with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            row = {}
            for field in fieldnames:
                if field in result:
                    value = result[field]
                    if field == '文件大小' and isinstance(value, (int, float)) and value > 0:
                        value = self._format_size_for_csv(value)
                    row[field] = value if not isinstance(value, (dict, list)) else str(value)
                else:
                    row[field] = ''
            
            writer.writerow(row)
    
    def _export_single_txt(self, result: Dict, filepath: str):
        """导出单个结果为TXT"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("VirusTotal 查询报告\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"查询内容: {result.get('查询内容', 'N/A')}\n")
            f.write(f"查询类型: {result.get('查询类型', 'N/A')}\n")
            f.write(f"状态: {result.get('状态', 'N/A')}\n\n")
            
            if result.get('状态') == '未找到':
                f.write(f"错误信息: {result.get('错误信息', 'N/A')}\n")
            else:
                f.write("--- 威胁分析 ---\n")
                f.write(f"是否恶意: {'是' if result.get('是否恶意') else '否'}\n")
                f.write(f"是否高危: {'是' if result.get('是否高危') else '否'}\n")
                f.write(f"恶意检测数: {result.get('恶意检测数', 0)}\n")
                f.write(f"检测率: {result.get('检测率', 'N/A')}\n")
                f.write(f"检测百分比: {result.get('检测百分比', 0)}%\n")
                f.write(f"威胁分类: {result.get('威胁分类', '未知')}\n")
                
                if result.get('流行威胁分类'):
                    f.write(f"流行威胁分类: {result.get('流行威胁分类')}\n")
                
                f.write("\n--- 详细信息 ---\n")
                f.write(f"文件类型: {result.get('文件类型', 'N/A')}\n")
                if result.get('文件大小') and isinstance(result.get('文件大小'), (int, float)):
                    f.write(f"文件大小: {self._format_size_for_csv(result.get('文件大小'))}\n")
                f.write(f"最后分析时间: {result.get('最后分析时间', 'N/A')}\n")
                f.write(f"情报链接: {result.get('情报链接', 'N/A')}\n")
    
    def _export_html_report(self, result: Dict, filepath: str):
        """导出可视化HTML报告"""
        is_malicious = result.get('是否恶意', False)
        is_high_risk = result.get('是否高危', False)
        detection_percent = result.get('检测百分比', 0)
        
        # 确定威胁等级颜色
        if is_high_risk:
            threat_level = "高危"
            threat_color = "#dc3545"
            threat_bg = "#f8d7da"
        elif is_malicious:
            threat_level = "可疑"
            threat_color = "#ffc107"
            threat_bg = "#fff3cd"
        else:
            threat_level = "安全"
            threat_color = "#28a745"
            threat_bg = "#d4edda"
        
        # 检测率进度条颜色
        if detection_percent > 50:
            progress_color = "#dc3545"
        elif detection_percent > 20:
            progress_color = "#ffc107"
        else:
            progress_color = "#28a745"
        
        html_content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VirusTotal 查询报告 - {result.get('查询内容', 'N/A')}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}
        .card {{
            background: white;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            overflow: hidden;
            margin-bottom: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            font-size: 24px;
            margin-bottom: 10px;
        }}
        .header .query {{
            font-family: monospace;
            background: rgba(255,255,255,0.1);
            padding: 10px 20px;
            border-radius: 8px;
            word-break: break-all;
            font-size: 14px;
        }}
        .threat-banner {{
            padding: 20px;
            text-align: center;
            font-size: 18px;
            font-weight: bold;
            background: {threat_bg};
            color: {threat_color};
        }}
        .content {{
            padding: 30px;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .section-title {{
            font-size: 18px;
            font-weight: 600;
            color: #333;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
        }}
        .stat-item {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 28px;
            font-weight: bold;
            color: #333;
        }}
        .stat-value.danger {{
            color: #dc3545;
        }}
        .stat-value.warning {{
            color: #ffc107;
        }}
        .stat-value.safe {{
            color: #28a745;
        }}
        .stat-label {{
            font-size: 12px;
            color: #666;
            margin-top: 5px;
        }}
        .progress-container {{
            background: #e9ecef;
            border-radius: 10px;
            height: 20px;
            overflow: hidden;
            margin: 10px 0;
        }}
        .progress-bar {{
            height: 100%;
            background: {progress_color};
            border-radius: 10px;
            transition: width 0.5s ease;
            width: {detection_percent}%;
        }}
        .info-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .info-table tr {{
            border-bottom: 1px solid #eee;
        }}
        .info-table tr:last-child {{
            border-bottom: none;
        }}
        .info-table td {{
            padding: 12px 0;
        }}
        .info-table td:first-child {{
            font-weight: 500;
            color: #666;
            width: 140px;
        }}
        .info-table td:last-child {{
            color: #333;
        }}
        .tag {{
            display: inline-block;
            background: #e9ecef;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            margin: 2px;
        }}
        .tag.malicious {{
            background: #f8d7da;
            color: #721c24;
        }}
        .link-button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 12px 30px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 500;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .link-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(102, 126, 234, 0.4);
        }}
        .screenshot {{
            width: 100%;
            border-radius: 8px;
            margin-top: 15px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 12px;
        }}
        @media (max-width: 600px) {{
            .stats-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <h1>🛡️ VirusTotal 威胁情报报告</h1>
                <div class="query">{result.get('查询内容', 'N/A')}</div>
            </div>
            <div class="threat-banner">
                {'⚠️ 检测到威胁' if is_malicious else '✅ 未检测到威胁'} - {threat_level}
            </div>
            <div class="content">
                <div class="section">
                    <div class="section-title">📊 检测统计</div>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-value {'danger' if result.get('恶意检测数', 0) > 0 else 'safe'}">{result.get('恶意检测数', 0)}</div>
                            <div class="stat-label">恶意检测数</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value warning">{result.get('未检测数', 0)}</div>
                            <div class="stat-label">未检测数</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value">{result.get('总扫描引擎', 0)}</div>
                            <div class="stat-label">总扫描引擎</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-value {'danger' if detection_percent > 50 else 'warning' if detection_percent > 20 else 'safe'}">{detection_percent}%</div>
                            <div class="stat-label">检测百分比</div>
                        </div>
                    </div>
                    <div style="margin-top: 20px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                            <span>检测率</span>
                            <span>{result.get('检测率', '0/0')}</span>
                        </div>
                        <div class="progress-container">
                            <div class="progress-bar"></div>
                        </div>
                    </div>
                </div>
                
                <div class="section">
                    <div class="section-title">🔍 基本信息</div>
                    <table class="info-table">
                        <tr>
                            <td>查询类型</td>
                            <td>{result.get('查询类型', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>查询时间</td>
                            <td>{result.get('查询时间', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>文件类型</td>
                            <td>{result.get('文件类型', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>文件大小</td>
                            <td>{self._format_size_for_csv(result.get('文件大小')) if isinstance(result.get('文件大小'), (int, float)) else result.get('文件大小', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>威胁分类</td>
                            <td>{result.get('威胁分类', '未知')}</td>
                        </tr>
                        {f'<tr><td>流行威胁分类</td><td>{result.get("流行威胁分类")}</td></tr>' if result.get('流行威胁分类') else ''}
                        <tr>
                            <td>最后分析时间</td>
                            <td>{result.get('最后分析时间', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>首次提交时间</td>
                            <td>{result.get('首次提交时间', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td>提交次数</td>
                            <td>{result.get('提交次数', 0)}</td>
                        </tr>
                    </table>
                </div>
                
                {self._generate_tags_html(result)}
                
                <div class="section" style="text-align: center;">
                    <a href="{result.get('情报链接', '#')}" target="_blank" class="link-button">
                        🔗 查看 VirusTotal 完整报告
                    </a>
                </div>
                
                {self._generate_screenshot_html(result)}
            </div>
        </div>
        <div class="footer">
            报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Powered by VirusTotal API
        </div>
    </div>
</body>
</html>'''
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
    
    def _generate_tags_html(self, result: Dict) -> str:
        """生成标签HTML"""
        tags = result.get('标签', '')
        if not tags:
            return ''
        
        tags_list = tags.split(',')
        tags_html = '<div class="section"><div class="section-title">🏷️ 标签</div><div>'
        for tag in tags_list:
            tag = tag.strip()
            if tag:
                tags_html += f'<span class="tag">{tag}</span> '
        tags_html += '</div></div>'
        return tags_html
    
    def _generate_screenshot_html(self, result: Dict) -> str:
        """生成截图HTML"""
        screenshot_path = result.get('截图路径')
        if screenshot_path and os.path.exists(screenshot_path):
            return f'''
                <div class="section">
                    <div class="section-title">📸 网页截图</div>
                    <img src="screenshot.png" alt="VirusTotal Screenshot" class="screenshot">
                </div>
            '''
        return ''
    
    def export_json(self, filename: str = None) -> str:
        """导出为JSON"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vt_results_{timestamp}.json"
        
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            return filepath
        except Exception as e:
            raise Exception(f"JSON导出失败: {str(e)}")
    
    def export_csv(self, filename: str = None) -> str:
        """导出为CSV（中文字段）"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vt_results_{timestamp}.csv"
        
        filepath = os.path.join(self.output_dir, filename)
        
        if not self.results:
            raise Exception("没有结果可导出")
        
        # 定义CSV字段（中文）
        fieldnames = [
            '状态', '是否恶意', '是否高危', '恶意检测数', '未检测数', 
            '总扫描引擎', '检测率', '检测百分比', '威胁分类', '流行威胁分类',
            '查询内容', '查询类型', '查询时间', '文件类型', '文件大小',
            '标签', '最后分析时间', '首次提交时间', '最后提交时间', '提交次数',
            '签名信息', '情报链接'
        ]
        
        try:
            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for result in self.results:
                    # 准备行数据
                    row = {}
                    
                    # 基础字段
                    for field in fieldnames:
                        if field in result:
                            row[field] = result[field]
                        else:
                            row[field] = ''
                    
                    # 文件大小格式化
                    if row['文件大小'] and isinstance(row['文件大小'], (int, float)) and row['文件大小'] > 0:
                        row['文件大小'] = self._format_size_for_csv(row['文件大小'])
                    
                    writer.writerow(row)
            
            return filepath
        except Exception as e:
            raise Exception(f"CSV导出失败: {str(e)}")
    
    def export_txt(self, filename: str = None) -> str:
        """导出为文本报告"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"vt_report_{timestamp}.txt"
        
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("VirusTotal 查询报告\n")
                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"总查询数: {len(self.results)}\n")
                f.write("=" * 80 + "\n\n")
                
                for i, result in enumerate(self.results, 1):
                    f.write(f"[{i}] {result.get('查询内容', 'N/A')} ({result.get('查询类型', 'N/A')})\n")
                    f.write(f"   状态: {result.get('状态', 'N/A')}\n")
                    
                    if result.get('状态') == '未找到':
                        f.write(f"   错误信息: {result.get('错误信息', 'N/A')}\n")
                    elif result.get('是否恶意'):
                        f.write(f"   是否恶意: 是\n")
                        f.write(f"   是否高危: {'是' if result.get('是否高危') else '否'}\n")
                        f.write(f"   恶意检测数: {result.get('恶意检测数', 0)}\n")
                        f.write(f"   检测率: {result.get('检测率', 'N/A')}\n")
                        f.write(f"   威胁分类: {result.get('威胁分类', '未知')}\n")
                    else:
                        f.write(f"   是否恶意: 否\n")
                    
                    f.write(f"   文件类型: {result.get('文件类型', 'N/A')}\n")
                    f.write(f"   最后分析时间: {result.get('最后分析时间', 'N/A')}\n")
                    f.write(f"   情报链接: {result.get('情报链接', 'N/A')}\n")
                    f.write("\n")
            
            return filepath
        except Exception as e:
            raise Exception(f"文本导出失败: {str(e)}")
    
    def export_all_separately(self, enable_screenshot: bool = True) -> List[Dict[str, str]]:
        """将所有结果分别导出到独立文件夹"""
        all_exports = []
        
        # 初始化截图功能
        if enable_screenshot and self.screenshotter is None:
            self.init_screenshot()
        
        for result in self.results:
            exported = self.export_single_result(result, 'all')
            all_exports.append(exported)
        
        return all_exports
    
    def close(self):
        """关闭资源"""
        if self.screenshotter:
            self.screenshotter.close()
    
    def _format_size_for_csv(self, size_bytes: int) -> str:
        """为CSV格式化文件大小"""
        if size_bytes is None:
            return "N/A"
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f} GB"

# ==================== 主程序 ====================

def main():
    parser = argparse.ArgumentParser(
        description='VirusTotal 增强版查询工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 单次查询
  %(prog)s c694c3c578678ac228f1c38f670969c0
  %(prog)s 8.8.8.8
  %(prog)s google.com
  
  # 指定查询类型
  %(prog)s c694c3c578678ac228f1c38f670969c0 --type md5
  
  # 批量查询
  %(prog)s --batch queries.txt
  
  # 导出结果
  %(prog)s --export csv
  %(prog)s --export json --output results.json
  
  # 导出为独立文件夹（含截图和HTML报告）
  %(prog)s --export separate
  
  # 配置管理
  %(prog)s --config add --key YOUR_API_KEY
  %(prog)s --config list
  
  # 查看统计
  %(prog)s --stats
  
  # 禁用颜色
  %(prog)s c694c3c578678ac228f1c38f670969c0 --no-color
  
  # 禁用截图
  %(prog)s c694c3c578678ac228f1c38f670969c0 --no-screenshot
        """
    )
    
    # 查询参数
    parser.add_argument('query', nargs='?', help='要查询的内容')
    parser.add_argument('--type', choices=['auto', 'md5', 'sha1', 'sha256', 'sha512', 'ip', 'domain', 'url'],
                       default='auto', help='查询类型 (默认: auto检测)')
    
    # 批量查询
    parser.add_argument('--batch', metavar='FILE', help='批量查询文件')
    
    # 导出选项
    parser.add_argument('--export', choices=['json', 'csv', 'txt', 'html', 'separate', 'all'], help='导出格式')
    parser.add_argument('--output', metavar='FILE', help='导出文件名')
    
    # 配置管理
    parser.add_argument('--config', choices=['add', 'list', 'clear', 'test'], help='配置操作')
    parser.add_argument('--key', help='API密钥 (与--config add一起使用)')
    
    # 统计信息
    parser.add_argument('--stats', action='store_true', help='显示统计信息')
    
    # 其他选项
    parser.add_argument('--no-color', action='store_true', help='禁用颜色输出')
    parser.add_argument('--no-screenshot', action='store_true', help='禁用网页截图')
    
    args = parser.parse_args()
    
    # 加载配置
    config = VTConfig.load_from_file()
    
    # 禁用颜色
    if args.no_color:
        config.enable_color = False
    
    # 禁用截图
    if args.no_screenshot:
        config.enable_screenshot = False
    
    # 创建查询器、显示器和导出器
    vt = VTQuery(config)
    display = ResultDisplay(config.enable_color)
    exporter = ResultExporter(config.output_dir)
    
    # 初始化截图功能
    if config.enable_screenshot:
        exporter.init_screenshot(config.screenshot_timeout)
    
    try:
        # 处理命令行参数
        if args.stats:
            # 显示统计信息
            print("\n📊 查询统计:")
            print(f"  当前结果数: {len(exporter.results)}")
            return
        
        elif args.config:
            # 配置管理
            if args.config == 'add' and args.key:
                config.api_keys.append(args.key)
                config.save_to_file()
                print(f"✅ 已添加API密钥: {args.key[:8]}...")
            
            elif args.config == 'list':
                print("\n🔑 已配置的API密钥:")
                for i, key in enumerate(config.api_keys, 1):
                    print(f"  {i}. {key[:8]}...{key[-4:]}")
            
            elif args.config == 'clear':
                config.api_keys = []
                config.save_to_file()
                print("✅ 已清除所有API密钥")
            
            elif args.config == 'test':
                print("🔗 测试API密钥连接...")
                for key in config.api_keys:
                    try:
                        import requests
                        headers = {"x-apikey": key}
                        response = requests.get(
                            "https://www.virustotal.com/api/v3/files/44d88612fea8a8f36de82e1278abb02f",
                            headers=headers,
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            print(f"  ✅ {key[:8]}... - 有效")
                        elif response.status_code == 401:
                            print(f"  ❌ {key[:8]}... - 无效")
                        elif response.status_code == 429:
                            print(f"  ⚠️  {key[:8]}... - 达到限制")
                        else:
                            print(f"  ❓ {key[:8]}... - 状态码: {response.status_code}")
                    
                    except Exception as e:
                        print(f"  ❌ {key[:8]}... - 错误: {str(e)}")
        
        elif args.batch:
            # 批量查询
            try:
                with open(args.batch, 'r', encoding='utf-8') as f:
                    queries = [line.strip() for line in f if line.strip()]
                
                print(f"📊 批量查询 {len(queries)} 个项目...")
                
                for i, query in enumerate(queries, 1):
                    print(f"\n[{i}/{len(queries)}] 查询: {query}")
                    
                    result = vt.query(query)
                    exporter.add_result(result)
                    
                    if result.get('状态') == '未找到':
                        print(f"  ⚠️  未找到: {result.get('错误信息', '记录不存在')}")
                    elif '错误信息' in result:
                        print(f"  ❌ 失败: {result['错误信息']}")
                    else:
                        if result.get('是否恶意'):
                            print(f"  ❌ 恶意: {result.get('恶意检测数', 0)}/{result.get('总扫描引擎', 0)}")
                        else:
                            print(f"  ✅ 安全")
                    
                    # 延迟避免频率限制
                    if i < len(queries):
                        time.sleep(config.rate_limit_delay)
                
                print(f"\n✅ 批量查询完成，共 {len(queries)} 个项目")
                
                if args.export:
                    if args.export == 'separate' or args.export == 'all':
                        print("\n📁 导出结果到独立文件夹...")
                        exports = exporter.export_all_separately(config.enable_screenshot)
                        for exp in exports:
                            print(f"  ✅ 已导出: {exp.get('folder', 'N/A')}")
                    else:
                        _do_export(exporter, args.export, args.output)
                    
            except FileNotFoundError:
                print(f"❌ 文件不存在: {args.batch}")
            except Exception as e:
                print(f"❌ 批量查询失败: {str(e)}")
        
        elif args.query:
            # 单次查询
            query_type = None if args.type == 'auto' else args.type
            result = vt.query(args.query, query_type)
            exporter.add_result(result)
            
            display.display(result)
            
            if args.export:
                if args.export == 'separate' or args.export == 'all':
                    print("\n📁 导出结果到独立文件夹...")
                    exported = exporter.export_single_result(result, 'all')
                    print(f"  ✅ 已导出到: {exported.get('folder', 'N/A')}")
                    if exported.get('screenshot'):
                        print(f"  📸 截图已保存: {exported.get('screenshot')}")
                    if exported.get('html'):
                        print(f"  📄 HTML报告: {exported.get('html')}")
                else:
                    _do_export(exporter, args.export, args.output)
        
        elif args.export:
            # 仅导出
            if exporter.results:
                if args.export == 'separate' or args.export == 'all':
                    print("\n📁 导出结果到独立文件夹...")
                    exports = exporter.export_all_separately(config.enable_screenshot)
                    for exp in exports:
                        print(f"  ✅ 已导出: {exp.get('folder', 'N/A')}")
                else:
                    _do_export(exporter, args.export, args.output)
            else:
                print("❌ 没有查询结果可导出")
        
        else:
            # 交互模式
            print("\n🔍 VirusTotal 增强版查询工具")
            print("=" * 60)
            
            while True:
                try:
                    print("\n📝 请选择操作:")
                    print("  1. 🔍 单次查询")
                    print("  2. 📊 批量查询")
                    print("  3. 💾 导出结果")
                    print("  4. 📁 导出所有结果到独立文件夹")
                    print("  5. ⚙️ 配置管理")
                    print("  6. 📈 查看统计")
                    print("  7. 🚪 退出")
                    
                    choice = input("\n👉 请输入选项 (1-7): ").strip()
                    
                    if choice == '1':
                        query = input("📥 请输入查询内容: ").strip()
                        if query:
                            result = vt.query(query)
                            exporter.add_result(result)
                            display.display(result)
                            
                            # 询问是否导出
                            export_choice = input("\n💾 是否导出结果? (y/n): ").strip().lower()
                            if export_choice == 'y':
                                exported = exporter.export_single_result(result, 'all')
                                print(f"  ✅ 已导出到: {exported.get('folder', 'N/A')}")
                                if exported.get('screenshot'):
                                    print(f"  📸 截图已保存")
                                if exported.get('html'):
                                    print(f"  📄 HTML报告已生成")
                    
                    elif choice == '2':
                        filepath = input("📄 请输入批量查询文件路径: ").strip()
                        if filepath:
                            if not os.path.exists(filepath):
                                print(f"❌ 文件不存在: {filepath}")
                                continue
                            
                            try:
                                with open(filepath, 'r', encoding='utf-8') as f:
                                    queries = [line.strip() for line in f if line.strip()]
                                
                                print(f"📊 批量查询 {len(queries)} 个项目...")
                                
                                for i, query in enumerate(queries, 1):
                                    print(f"\n[{i}/{len(queries)}] 查询: {query}")
                                    
                                    result = vt.query(query)
                                    exporter.add_result(result)
                                    
                                    if result.get('状态') == '未找到':
                                        print(f"  ⚠️  未找到: {result.get('错误信息', '记录不存在')}")
                                    elif '错误信息' in result:
                                        print(f"  ❌ 失败: {result['错误信息']}")
                                    else:
                                        if result.get('是否恶意'):
                                            print(f"  ❌ 恶意: {result.get('恶意检测数', 0)}/{result.get('总扫描引擎', 0)}")
                                        else:
                                            print(f"  ✅ 安全")
                                    
                                    # 延迟避免频率限制
                                    if i < len(queries):
                                        time.sleep(config.rate_limit_delay)
                                
                                print(f"\n✅ 批量查询完成，共 {len(queries)} 个项目")
                                
                                # 询问是否导出
                                export_choice = input("\n💾 是否导出所有结果到独立文件夹? (y/n): ").strip().lower()
                                if export_choice == 'y':
                                    exports = exporter.export_all_separately(config.enable_screenshot)
                                    for exp in exports:
                                        print(f"  ✅ 已导出: {exp.get('folder', 'N/A')}")
                            
                            except Exception as e:
                                print(f"❌ 批量查询失败: {str(e)}")
                    
                    elif choice == '3':
                        _export_interactive(exporter)
                    
                    elif choice == '4':
                        if exporter.results:
                            print("\n📁 导出所有结果到独立文件夹...")
                            exports = exporter.export_all_separately(config.enable_screenshot)
                            for exp in exports:
                                print(f"  ✅ 已导出: {exp.get('folder', 'N/A')}")
                        else:
                            print("❌ 没有查询结果可导出")
                    
                    elif choice == '5':
                        _config_interactive(config)
                    
                    elif choice == '6':
                        print(f"\n📊 查询统计:")
                        print(f"  当前结果数: {len(exporter.results)}")
                    
                    elif choice == '7':
                        print("\n👋 再见！")
                        break
                    
                    else:
                        print("❌ 无效选项")
                
                except KeyboardInterrupt:
                    print("\n⚠️ 中断操作")
                    break
                except Exception as e:
                    print(f"❌ 错误: {str(e)}")
    
    finally:
        # 确保关闭资源
        exporter.close()

def _do_export(exporter: ResultExporter, export_format: str, output_file: str = None):
    """执行导出"""
    try:
        if export_format == 'json':
            filepath = exporter.export_json(output_file)
            print(f"✅ JSON已导出: {filepath}")
        elif export_format == 'csv':
            filepath = exporter.export_csv(output_file)
            print(f"✅ CSV已导出: {filepath}")
        elif export_format == 'txt':
            filepath = exporter.export_txt(output_file)
            print(f"✅ 文本报告已导出: {filepath}")
        elif export_format in ['html', 'separate', 'all']:
            exports = exporter.export_all_separately()
            for exp in exports:
                print(f"✅ 已导出: {exp.get('folder', 'N/A')}")
        else:
            print(f"❌ 不支持的导出格式: {export_format}")
    except Exception as e:
        print(f"❌ 导出失败: {str(e)}")

def _export_interactive(exporter: ResultExporter):
    """交互式导出"""
    if not exporter.results:
        print("❌ 没有查询结果可导出")
        return
    
    print("\n📁 导出格式:")
    print("  1. JSON")
    print("  2. CSV (中文字段)")
    print("  3. TXT (文本报告)")
    print("  4. 独立文件夹 (含截图和HTML报告)")
    
    choice = input("\n👉 请选择格式 (1-4): ").strip()
    formats = {'1': 'json', '2': 'csv', '3': 'txt', '4': 'separate'}
    
    if choice in formats:
        filename = input("💾 文件名 (留空使用默认): ").strip()
        try:
            if choice == '4':
                exports = exporter.export_all_separately()
                for exp in exports:
                    print(f"  ✅ 已导出: {exp.get('folder', 'N/A')}")
            else:
                _do_export(exporter, formats[choice], filename if filename else None)
        except Exception as e:
            print(f"❌ 导出失败: {str(e)}")
    else:
        print("❌ 无效选项")

def _config_interactive(config: VTConfig):
    """交互式配置"""
    print("\n⚙️ 配置管理:")
    print("  1. 添加API密钥")
    print("  2. 查看API密钥")
    print("  3. 清除所有密钥")
    print("  4. 测试API密钥")
    
    choice = input("\n👉 请选择操作 (1-4): ").strip()
    
    if choice == '1':
        key = input("🔑 请输入API密钥: ").strip()
        if key:
            config.api_keys.append(key)
            config.save_to_file()
            print(f"✅ 已添加API密钥: {key[:8]}...")
    
    elif choice == '2':
        print("\n🔑 已配置的API密钥:")
        for i, key in enumerate(config.api_keys, 1):
            print(f"  {i}. {key[:8]}...{key[-4:]}")
    
    elif choice == '3':
        confirm = input("⚠️ 确认清除所有API密钥? (y/n): ").strip().lower()
        if confirm == 'y':
            config.api_keys = []
            config.save_to_file()
            print("✅ 已清除所有API密钥")
    
    elif choice == '4':
        print("🔗 测试API密钥连接...")
        for key in config.api_keys:
            try:
                import requests
                headers = {"x-apikey": key}
                response = requests.get(
                    "https://www.virustotal.com/api/v3/files/44d88612fea8a8f36de82e1278abb02f",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    print(f"  ✅ {key[:8]}... - 有效")
                elif response.status_code == 401:
                    print(f"  ❌ {key[:8]}... - 无效")
                elif response.status_code == 429:
                    print(f"  ⚠️  {key[:8]}... - 达到限制")
                else:
                    print(f"  ❓ {key[:8]}... - 状态码: {response.status_code}")
            
            except Exception as e:
                print(f"  ❌ {key[:8]}... - 错误: {str(e)}")
    
    else:
        print("❌ 无效选项")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 用户中断，退出程序")
        sys.exit(0)
    except Exception as e:
        print(f"❌ 程序出错: {e}")
        sys.exit(1)