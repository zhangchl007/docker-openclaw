#!/usr/bin/env python3
"""
Notification Handler - 通知发送器
支持多种通知渠道：WeCom Bot, ServerChan, Telegram, PushPlus

Usage:
    python notifier.py --channel wecom --message "测试消息"
    python notifier.py --channel serverchan --message "测试消息"
    python notifier.py --report daily
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


class Notifier:
    """多渠道通知发送器"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or os.environ.get(
            'NOTIFIER_CONFIG',
            '/home/node/.openclaw/stock-data/notifier.json'
        )
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """加载配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
    
    def _http_post(self, url: str, data: dict, headers: dict = None, timeout: int = 30) -> dict:
        """发送HTTP POST请求"""
        if headers is None:
            headers = {'Content-Type': 'application/json'}
        
        json_data = json.dumps(data).encode('utf-8')
        req = Request(url, data=json_data, headers=headers, method='POST')
        
        try:
            with urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except (URLError, HTTPError) as e:
            return {'error': str(e), 'success': False}
        except Exception as e:
            return {'error': str(e), 'success': False}
    
    def _format_for_wecom(self, message: str) -> str:
        """
        为企业微信格式化消息
        企业微信Markdown支持有限，需要特殊处理
        """
        # 移除不支持的Markdown语法
        # WeCom不支持表格，转换为列表
        lines = message.split('\n')
        result = []
        in_table = False
        
        for line in lines:
            # 跳过表格分隔行
            if re.match(r'^\|[-:\s|]+\|$', line):
                in_table = True
                continue
            
            # 处理表格行
            if line.startswith('|') and line.endswith('|'):
                # 转换表格为列表格式
                cells = [c.strip() for c in line.split('|')[1:-1]]
                if in_table and len(cells) >= 2:
                    result.append(f"> {' | '.join(cells)}")
                else:
                    in_table = True
                    result.append(f"**{' | '.join(cells)}**")
                continue
            else:
                in_table = False
            
            # 保留其他内容
            result.append(line)
        
        return '\n'.join(result)
    
    def _split_message(self, message: str, max_bytes: int = 3800) -> list:
        """
        Split a long message into multiple parts at section boundaries.
        Each part stays under max_bytes (UTF-8).
        """
        sections = re.split(r'\n(?=### |\n## |\n---)', message)
        
        parts = []
        current = ""
        
        for section in sections:
            test = current + section
            if len(test.encode('utf-8')) > max_bytes and current:
                parts.append(current.rstrip())
                current = section
            else:
                current = test
        
        if current.strip():
            parts.append(current.rstrip())
        
        return parts if parts else [message[:max_bytes]]
    
    def send_wecom(self, message: str, msg_type: str = 'markdown') -> dict:
        """
        发送企业微信机器人消息
        自动将长消息拆分为多条发送
        
        配置示例:
        {
            "wecom": {
                "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
            }
        }
        """
        webhook = self.config.get('wecom', {}).get('webhook')
        if not webhook:
            webhook = os.environ.get('WECOM_WEBHOOK')
        
        if not webhook:
            return {'error': '未配置企业微信Webhook', 'success': False}
        
        # 格式化消息
        formatted_message = self._format_for_wecom(message)
        
        # 拆分长消息 (企业微信Markdown限制4096字节)
        parts = self._split_message(formatted_message, max_bytes=3800)
        
        results = []
        for i, part in enumerate(parts):
            if len(parts) > 1:
                part = f"📄 ({i+1}/{len(parts)})\n\n{part}"
            
            if msg_type == 'markdown':
                data = {
                    'msgtype': 'markdown',
                    'markdown': {
                        'content': part
                    }
                }
            else:
                data = {
                    'msgtype': 'text',
                    'text': {
                        'content': part
                    }
                }
            
            result = self._http_post(webhook, data)
            results.append(result)
            
            # Rate limit between messages
            if i < len(parts) - 1:
                import time
                time.sleep(1)
        
        # Summarize results
        all_ok = all(r.get('errcode', -1) == 0 for r in results)
        return {
            'channel': 'wecom',
            'success': all_ok,
            'parts_sent': len(results),
            'errcode': 0 if all_ok else results[-1].get('errcode', -1),
            'errmsg': 'ok' if all_ok else results[-1].get('errmsg', 'error')
        }
    
    def send_wecom_app(self, message: str, msg_type: str = 'markdown') -> dict:
        """
        发送企业微信应用消息 - 最安全的官方API
        
        配置示例:
        {
            "wecom_app": {
                "corpid": "YOUR_CORP_ID",
                "agentid": "YOUR_AGENT_ID", 
                "secret": "YOUR_APP_SECRET",
                "touser": "@all"  # 或指定用户ID，如 "UserID1|UserID2"
            }
        }
        
        获取方式:
        1. 登录企业微信管理后台: https://work.weixin.qq.com/
        2. 应用管理 → 创建应用 → 获取 AgentId 和 Secret
        3. 我的企业 → 企业信息 → 获取 CorpID
        """
        config = self.config.get('wecom_app', {})
        corpid = config.get('corpid') or os.environ.get('WECOM_CORPID')
        agentid = config.get('agentid') or os.environ.get('WECOM_AGENTID')
        secret = config.get('secret') or os.environ.get('WECOM_SECRET')
        touser = config.get('touser', '@all')
        
        if not all([corpid, agentid, secret]):
            return {'error': '未完整配置企业微信应用 (需要corpid, agentid, secret)', 'success': False}
        
        # 1. 获取access_token
        token_url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={secret}"
        try:
            from urllib.request import urlopen
            with urlopen(token_url, timeout=10) as response:
                token_result = json.loads(response.read().decode('utf-8'))
            
            if token_result.get('errcode', 0) != 0:
                return {'error': f"获取token失败: {token_result.get('errmsg')}", 'success': False}
            
            access_token = token_result['access_token']
        except Exception as e:
            return {'error': f"获取token异常: {str(e)}", 'success': False}
        
        # 2. 发送消息
        send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={access_token}"
        
        # 格式化消息
        formatted_message = self._format_for_wecom(message)
        
        # 企业微信应用消息限制
        if len(formatted_message.encode('utf-8')) > 2000:
            formatted_message = formatted_message[:800] + "\n\n...(内容过长已截断)"
        
        if msg_type == 'markdown':
            data = {
                'touser': touser,
                'msgtype': 'markdown',
                'agentid': int(agentid),
                'markdown': {
                    'content': formatted_message
                }
            }
        else:
            data = {
                'touser': touser,
                'msgtype': 'text',
                'agentid': int(agentid),
                'text': {
                    'content': message
                }
            }
        
        result = self._http_post(send_url, data)
        result['channel'] = 'wecom_app'
        result['success'] = result.get('errcode', -1) == 0
        return result
    
    def send_serverchan(self, title: str, message: str) -> dict:
        """
        发送Server酱消息
        
        配置示例:
        {
            "serverchan": {
                "sendkey": "YOUR_SENDKEY"
            }
        }
        
        Server酱配置地址: https://sct.ftqq.com/
        """
        sendkey = self.config.get('serverchan', {}).get('sendkey')
        if not sendkey:
            sendkey = os.environ.get('SERVERCHAN_SENDKEY')
        
        if not sendkey:
            return {'error': '未配置Server酱SendKey', 'success': False}
        
        url = f"https://sctapi.ftqq.com/{sendkey}.send"
        data = {
            'title': title,
            'desp': message
        }
        
        result = self._http_post(url, data)
        result['channel'] = 'serverchan'
        result['success'] = result.get('code') == 0 or result.get('errno') == 0
        return result
    
    def send_pushplus(self, title: str, message: str) -> dict:
        """
        发送PushPlus消息
        
        配置示例:
        {
            "pushplus": {
                "token": "YOUR_TOKEN"
            }
        }
        
        PushPlus配置地址: https://www.pushplus.plus/
        """
        token = self.config.get('pushplus', {}).get('token')
        if not token:
            token = os.environ.get('PUSHPLUS_TOKEN')
        
        if not token:
            return {'error': '未配置PushPlus Token', 'success': False}
        
        url = "http://www.pushplus.plus/send"
        data = {
            'token': token,
            'title': title,
            'content': message,
            'template': 'markdown'
        }
        
        result = self._http_post(url, data)
        result['channel'] = 'pushplus'
        result['success'] = result.get('code') == 200
        return result
    
    def send_telegram(self, message: str) -> dict:
        """
        发送Telegram消息
        
        配置示例:
        {
            "telegram": {
                "bot_token": "YOUR_BOT_TOKEN",
                "chat_id": "YOUR_CHAT_ID"
            }
        }
        """
        bot_token = self.config.get('telegram', {}).get('bot_token')
        chat_id = self.config.get('telegram', {}).get('chat_id')
        
        if not bot_token:
            bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if not chat_id:
            chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        
        if not bot_token or not chat_id:
            return {'error': '未配置Telegram Bot Token或Chat ID', 'success': False}
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }
        
        result = self._http_post(url, data)
        result['channel'] = 'telegram'
        result['success'] = result.get('ok', False)
        return result
    
    def send(self, channel: str, message: str, title: str = None) -> dict:
        """发送消息到指定渠道"""
        if channel == 'wecom':
            return self.send_wecom(message)
        elif channel == 'wecom_app':
            return self.send_wecom_app(message)
        elif channel == 'serverchan':
            return self.send_serverchan(title or '股票通知', message)
        elif channel == 'pushplus':
            return self.send_pushplus(title or '股票通知', message)
        elif channel == 'telegram':
            return self.send_telegram(message)
        else:
            return {'error': f'不支持的渠道: {channel}', 'success': False}
    
    def send_all(self, message: str, title: str = None) -> dict:
        """发送到所有已配置的渠道，优先使用官方渠道"""
        results = {}
        
        # 按安全性排序的渠道列表
        channels_priority = ['wecom_app', 'wecom', 'telegram', 'serverchan', 'pushplus']
        
        for channel in channels_priority:
            config_key = channel
            has_config = False
            
            if channel == 'wecom_app':
                # 检查企业微信应用配置
                app_config = self.config.get('wecom_app', {})
                has_config = all([
                    app_config.get('corpid') or os.environ.get('WECOM_CORPID'),
                    app_config.get('agentid') or os.environ.get('WECOM_AGENTID'),
                    app_config.get('secret') or os.environ.get('WECOM_SECRET')
                ])
            elif channel == 'wecom':
                has_config = bool(self.config.get('wecom', {}).get('webhook') or os.environ.get('WECOM_WEBHOOK'))
            elif channel == 'serverchan':
                has_config = bool(self.config.get('serverchan', {}).get('sendkey') or os.environ.get('SERVERCHAN_SENDKEY'))
            elif channel == 'pushplus':
                has_config = bool(self.config.get('pushplus', {}).get('token') or os.environ.get('PUSHPLUS_TOKEN'))
            elif channel == 'telegram':
                tg_config = self.config.get('telegram', {})
                has_config = bool(
                    (tg_config.get('bot_token') or os.environ.get('TELEGRAM_BOT_TOKEN')) and
                    (tg_config.get('chat_id') or os.environ.get('TELEGRAM_CHAT_ID'))
                )
            
            if has_config:
                results[channel] = self.send(channel, message, title)
        
        if not results:
            return {'error': '没有配置任何通知渠道', 'success': False}
        
        # 检查是否有成功发送的
        any_success = any(r.get('success', False) for r in results.values())
        results['_summary'] = {'any_success': any_success, 'channels_attempted': list(results.keys())}
        
        return results


def create_example_config():
    """创建示例配置文件"""
    example = {
        "_comment": "通知渠道配置 - 请填入您的密钥（推荐使用wecom_app，最安全）",
        
        "wecom_app": {
            "corpid": "YOUR_CORP_ID",
            "agentid": "YOUR_AGENT_ID",
            "secret": "YOUR_APP_SECRET",
            "touser": "@all",
            "_doc": "企业微信应用消息（最安全）- 登录 https://work.weixin.qq.com/ 获取"
        },
        
        "wecom": {
            "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY",
            "_doc": "企业微信机器人Webhook地址"
        },
        "serverchan": {
            "sendkey": "YOUR_SENDKEY",
            "_doc": "Server酱SendKey，从 https://sct.ftqq.com/ 获取"
        },
        "pushplus": {
            "token": "YOUR_TOKEN",
            "_doc": "PushPlus Token，从 https://www.pushplus.plus/ 获取"
        },
        "telegram": {
            "bot_token": "YOUR_BOT_TOKEN",
            "chat_id": "YOUR_CHAT_ID",
            "_doc": "Telegram Bot Token和Chat ID"
        }
    }
    return example


def main():
    parser = argparse.ArgumentParser(description='Notification Handler')
    parser.add_argument('--channel', choices=['wecom', 'wecom_app', 'serverchan', 'pushplus', 'telegram', 'all'],
                       help='通知渠道')
    parser.add_argument('--message', type=str, help='消息内容')
    parser.add_argument('--title', type=str, default='股票通知', help='消息标题')
    parser.add_argument('--report', choices=['daily', 'weekly'], help='发送报告')
    parser.add_argument('--init-config', action='store_true', help='生成示例配置文件')
    parser.add_argument('--test', action='store_true', help='测试通知')
    
    args = parser.parse_args()
    notifier = Notifier()
    
    if args.init_config:
        config = create_example_config()
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return
    
    if args.test:
        message = f"🦞 OpenClaw 通知测试\n\n时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n如果您看到这条消息，说明通知配置成功！"
        if args.channel == 'all':
            result = notifier.send_all(message, '通知测试')
        elif args.channel:
            result = notifier.send(args.channel, message, '通知测试')
        else:
            print("请指定 --channel 参数")
            return
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    
    if args.report:
        # 导入分析器生成报告
        try:
            from report import DeepDiveReport
            rpt = DeepDiveReport()
            message = rpt.generate()
            
            if args.report == 'daily':
                title = f"📊 股票日报 - {datetime.now().strftime('%Y-%m-%d')}"
            else:
                title = f"📊 股票周报 - {datetime.now().strftime('%Y年第%W周')}"
            
            if args.channel == 'all':
                result = notifier.send_all(message, title)
            elif args.channel:
                result = notifier.send(args.channel, message, title)
            else:
                result = notifier.send_all(message, title)
            
            print(json.dumps(result, ensure_ascii=False, indent=2))
            
        except ImportError as e:
            print(f"无法导入报告模块: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            try:
                rpt.provider.cleanup()
            except:
                pass
        return
    
    if args.message:
        if args.channel == 'all':
            result = notifier.send_all(args.message, args.title)
        elif args.channel:
            result = notifier.send(args.channel, args.message, args.title)
        else:
            print("请指定 --channel 参数")
            return
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    
    parser.print_help()


if __name__ == '__main__':
    main()
