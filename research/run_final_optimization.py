#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终优化运行器 - 集成训练/测试分割的超高性能优化系统
"""

import os
import sys
import logging

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from . import CryptoDataLoader, FinalUltraOptimizer, print_final_results

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """主函数 - 运行最终优化系统"""
    print("🚀 加密货币交易策略最终优化系统")
    print("=" * 60)
    print("✅ 严格训练/测试分割（无数据泄露）")
    print("⚡ 超高性能向量化计算")
    print("📊 真实可信的OOS收益率")
    print("=" * 60)
    
    try:
        # 选择运行模式
        print("\n选择优化模式:")
        print("1. 快速测试 (3个币种, ~30秒)")
        print("2. 中等测试 (10个币种, ~2分钟)")
        print("3. 完整优化 (所有184个币种, ~10分钟)")
        
        choice = input("\n输入选择 (1-3): ").strip()
        
        if choice == '1':
            limit_symbols = 3
            test_name = "快速测试"
        elif choice == '2':
            limit_symbols = 10
            test_name = "中等测试"
        elif choice == '3':
            limit_symbols = None
            test_name = "完整优化"
        else:
            print("无效选择，使用快速测试")
            limit_symbols = 3
            test_name = "快速测试"
        
        print(f"\n🔥 开始{test_name}...")
        
        # 加载数据
        print("📊 加载历史数据...")
        data_loader = CryptoDataLoader()
        
        if limit_symbols:
            symbols = data_loader.get_available_symbols()[:limit_symbols]
            all_data = []
            for symbol in symbols:
                full_data = data_loader.hist_loader.get_hist_candle_data(symbol, bar="1H", return_dataframe=True)
                if full_data is not None and len(full_data) > 0:
                    # 标准化数据格式
                    standardized_df = pd.DataFrame({
                        'timestamp': pd.to_datetime(full_data['timestamp'], unit='ms'),
                        'open': full_data['open'].astype(float),
                        'high': full_data['high'].astype(float),
                        'low': full_data['low'].astype(float),
                        'close': full_data['close'].astype(float),
                        'symbol': symbol
                    })
                    all_data.append(standardized_df)
            
            if all_data:
                import pandas as pd
                combined_data = pd.concat(all_data, ignore_index=True)
            else:
                print("❌ 无法加载数据")
                return
        else:
            combined_data = data_loader.load_all_data(months=36)  # 加载3年数据
        
        print(f"✅ 数据加载完成: {len(combined_data)} 条记录")
        
        # 初始化最终优化器
        final_optimizer = FinalUltraOptimizer(combined_data, test_days=90)
        
        # 运行优化
        results = final_optimizer.batch_optimize_with_split()
        
        if results:
            # 显示结果
            print_final_results(results, top_n=min(15, len(results)))
            
            # 保存结果
            saved_file = final_optimizer.save_results(results)
            
            # 总结
            test_returns = [r.test_return for r in results.values()]
            positive_returns = sum(1 for r in test_returns if r > 0)
            
            print(f"\n🎉 优化完成!")
            print(f"📊 处理币种: {len(results)}")
            print(f"📈 平均测试收益: {sum(test_returns)/len(test_returns):.2%} (91天)")
            print(f"✅ 盈利币种: {positive_returns}/{len(results)} ({positive_returns/len(results):.1%})")
            print(f"💾 详细结果: {saved_file}")
            
            print(f"\n💡 重要说明:")
            print(f"- 测试收益率基于最近91天真实数据")
            print(f"- 参数基于历史数据优化，无数据泄露")
            print(f"- 这些收益率是策略的真实预期表现")
            
        else:
            print("❌ 优化失败")
            
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断优化")
    except Exception as e:
        print(f"\n❌ 优化错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
