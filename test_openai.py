#!/usr/bin/env python3
"""测试OpenAI API连接的简单脚本"""

import os
import sys

def test_openai_connection():
    try:
        import openai
        print("✅ OpenAI库已安装")
        
        # 检查API Key
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("❌ 未设置OPENAI_API_KEY环境变量")
            return False
        
        print(f"✅ API Key已设置: {api_key[:20]}...")
        
        # 创建客户端
        client = openai.OpenAI(api_key=api_key)
        print("✅ OpenAI客户端创建成功")
        
        # 测试不同的模型
        models_to_test = ["gpt-3.5-turbo", "gpt-4o-mini", "gpt-4"]
        
        for model in models_to_test:
            try:
                print(f"🧪 测试模型: {model}")
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "Hello! Just say 'Hi' back."}
                    ],
                    max_tokens=10,
                    temperature=0
                )
                
                print(f"✅ 模型 {model} 调用成功!")
                print(f"📝 响应: {response.choices[0].message.content}")
                return True
                
            except Exception as e:
                print(f"❌ 模型 {model} 失败: {str(e)}")
                continue
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
        print(f"🔍 错误类型: {type(e).__name__}")
        return False

if __name__ == "__main__":
    print("🔬 OpenAI API连接测试")
    print("=" * 40)
    success = test_openai_connection()
    sys.exit(0 if success else 1)