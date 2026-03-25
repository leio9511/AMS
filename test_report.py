#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AMS 测试报告验证脚本
QA角色 - 自动触发报表并验证内容

使用方法:
    python test_report.py
    
验证项:
    1. 自动触发报表生成
    2. 截获 Telegram 发送的内容
    3. 验证内容是否包含"分析建议"关键词
"""

import sys
import os
import json
import subprocess
from datetime import datetime
from unittest.mock import patch, MagicMock

# 添加 AMS 目录到路径
sys.path.insert(0, '/root/.openclaw/workspace/AMS')

# 导入被测试模块
import etf_tracker

class TelegramInterceptor:
    """Telegram 消息拦截器"""
    
    def __init__(self):
        self.captured_messages = []
        self.original_send_msg = None
    
    def start_capture(self):
        """开始捕获消息"""
        self.original_send_msg = etf_tracker.send_msg
        self.captured_messages = []
        
        def mock_send_msg(text):
            self.captured_messages.append({
                'text': text,
                'timestamp': datetime.now().isoformat()
            })
            print(f"[INTERCEPTED] 捕获到消息, 长度: {len(text)} 字符")
            return True
        
        etf_tracker.send_msg = mock_send_msg
        print("[INTERCEPTOR] 开始拦截 Telegram 消息...")
    
    def stop_capture(self):
        """停止捕获"""
        if self.original_send_msg:
            etf_tracker.send_msg = self.original_send_msg
        print(f"[INTERCEPTOR] 停止拦截, 共捕获 {len(self.captured_messages)} 条消息")
    
    def get_messages(self):
        """获取捕获的消息"""
        return self.captured_messages


class TestReportValidator:
    """报告验证器"""
    
    REQUIRED_KEYWORDS = [
        "分析建议",
        "折价品种诊断", 
        "溢价品种监控",
        "实时ETF数据"
    ]
    
    REQUIRED_SECTIONS = [
        "🔔 【AMS 全功能分析报告】",
        "📊 【实时ETF数据】",
        "📉 【折价品种诊断】",
        "📈 【溢价品种监控】",
        "💡 【分析建议】"
    ]
    
    def __init__(self):
        self.results = {
            'passed': [],
            'failed': [],
            'warnings': []
        }
    
    def validate_keywords(self, report_content):
        """验证关键词"""
        print("\n[VALIDATION] 开始验证关键词...")
        
        for keyword in self.REQUIRED_KEYWORDS:
            if keyword in report_content:
                self.results['passed'].append(f"关键词 '{keyword}' 存在")
                print(f"  ✅ '{keyword}' - 通过")
            else:
                self.results['failed'].append(f"关键词 '{keyword}' 缺失")
                print(f"  ❌ '{keyword}' - 失败")
    
    def validate_sections(self, report_content):
        """验证报告结构"""
        print("\n[VALIDATION] 开始验证报告结构...")
        
        for section in self.REQUIRED_SECTIONS:
            if section in report_content:
                self.results['passed'].append(f"章节 '{section[:20]}...' 存在")
                print(f"  ✅ {section[:30]}...")
            else:
                self.results['failed'].append(f"章节 '{section[:20]}...' 缺失")
                print(f"  ❌ {section[:30]}... - 缺失")
    
    def validate_data_format(self, report_content):
        """验证数据格式"""
        print("\n[VALIDATION] 开始验证数据格式...")
        
        # 检查是否包含时间戳
        if "📅 时间:" in report_content:
            self.results['passed'].append("时间戳格式正确")
            print("  ✅ 时间戳格式正确")
        else:
            self.results['failed'].append("时间戳格式错误")
            print("  ❌ 时间戳格式错误")
        
        # 检查是否包含折溢价数据
        if "%)" in report_content:
            self.results['passed'].append("包含折溢价百分比数据")
            print("  ✅ 包含折溢价百分比数据")
        else:
            self.results['warnings'].append("未检测到折溢价百分比")
            print("  ⚠️ 未检测到折溢价百分比")
    
    def get_summary(self):
        """获取验证摘要"""
        total = len(self.results['passed']) + len(self.results['failed'])
        passed = len(self.results['passed'])
        failed = len(self.results['failed'])
        warnings = len(self.results['warnings'])
        
        summary = {
            'total_tests': total,
            'passed': passed,
            'failed': failed,
            'warnings': warnings,
            'pass_rate': f"{(passed/total*100):.1f}%" if total > 0 else "N/A",
            'status': 'PASS' if failed == 0 else 'FAIL'
        }
        return summary


def run_test():
    """运行测试"""
    print("="*60)
    print("AMS 测试报告验证脚本 V1.0")
    print("="*60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # 1. 初始化拦截器
    interceptor = TelegramInterceptor()
    validator = TestReportValidator()
    
    # 2. 开始拦截
    interceptor.start_capture()
    
    try:
        # 3. 触发测试报告生成
        print("\n[TEST] 触发测试报告生成...")
        report_content, success = etf_tracker.generate_test_report()
        
        print(f"\n[TEST] 报告生成结果: {'成功' if success else '失败'}")
        print(f"[TEST] 报告长度: {len(report_content)} 字符")
        
        # 4. 验证报告内容
        validator.validate_keywords(report_content)
        validator.validate_sections(report_content)
        validator.validate_data_format(report_content)
        
        # 5. 验证拦截的消息
        messages = interceptor.get_messages()
        print(f"\n[INTERCEPTOR] 拦截到 {len(messages)} 条消息")
        
        if messages:
            msg = messages[0]['text']
            if "分析建议" in msg:
                print("  ✅ 拦截的消息包含 '分析建议' 关键词")
                validator.results['passed'].append("Telegram消息包含'分析建议'")
            else:
                print("  ❌ 拦截的消息缺少 '分析建议' 关键词")
                validator.results['failed'].append("Telegram消息缺少'分析建议'")
        
    finally:
        # 6. 停止拦截
        interceptor.stop_capture()
    
    # 7. 输出结果摘要
    print("\n" + "="*60)
    print("验证结果摘要")
    print("="*60)
    
    summary = validator.get_summary()
    print(f"总测试数: {summary['total_tests']}")
    print(f"通过: {summary['passed']}")
    print(f"失败: {summary['failed']}")
    print(f"警告: {summary['warnings']}")
    print(f"通过率: {summary['pass_rate']}")
    print(f"状态: {summary['status']}")
    
    # 8. 输出报告内容预览
    print("\n" + "="*60)
    print("报告内容预览 (前500字符)")
    print("="*60)
    print(report_content[:500])
    print("...")
    
    # 9. 保存测试结果
    test_result = {
        'timestamp': datetime.now().isoformat(),
        'summary': summary,
        'report_length': len(report_content),
        'messages_intercepted': len(messages),
        'validator_results': validator.results
    }
    
    result_path = '/root/.openclaw/workspace/AMS/test_result.json'
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(test_result, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVED] 测试结果已保存到: {result_path}")
    
    return summary['status'] == 'PASS'


if __name__ == '__main__':
    success = run_test()
    sys.exit(0 if success else 1)
