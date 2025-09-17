#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cryptocurrency Strategy Optimization - Main Entry Point
Wrapper script to run the research module optimization system
"""

import os
import sys
import subprocess

def main():
    """Main entry point - runs the research module optimization"""
    print("🚀 Cryptocurrency Trading Strategy Optimization")
    print("=" * 50)
    print("Launching research module...")
    print("=" * 50)
    
    # Get the project root directory
    project_root = os.path.dirname(os.path.abspath(__file__))
    
    try:
        # Run the research module
        result = subprocess.run([
            sys.executable, '-m', 'research.run_final_optimization'
        ], cwd=project_root, check=True)
        
        print("\n✅ Optimization completed successfully!")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Optimization failed with exit code {e.returncode}")
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        print("\n⚠️ Optimization interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error running optimization: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
