#!/usr/bin/env python3
"""测试OpenAI API连接的简单脚本"""

import os
import sys

from agent_llm import DEFAULT_API_VERSION, DEFAULT_DEPLOYMENT_NAME

def test_openai_connection():
    try:
        import openai
        print("✅ OpenAI库已安装")

        client_cls = getattr(openai, "AzureOpenAI", None)
        if client_cls is None:
            print("❌ 当前OpenAI库缺少AzureOpenAI客户端")
            return False

        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        deployment = os.environ.get(
            "AZURE_OPENAI_DEPLOYMENT_NAME", DEFAULT_DEPLOYMENT_NAME
        )
        api_version = os.environ.get("OPENAI_API_VERSION", DEFAULT_API_VERSION)
        if not api_key or not endpoint:
            print("❌ 缺少 AZURE_OPENAI_API_KEY 或 AZURE_OPENAI_ENDPOINT 环境变量")
            return False

        print(f"✅ 使用Azure端点: {endpoint}")

        # 创建客户端
        client = client_cls(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        print("✅ Azure OpenAI客户端创建成功")

        # 测试部署
        models_to_test = [deployment]
        
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
