"""测试 DEEPSEEK 模型连通性"""
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 加载环境变量
load_dotenv()

# 获取 DEEPSEEK 配置
api_base = os.getenv("DEEPSEEK_API_BASE")
api_key = os.getenv("DEEPSEEK_API_KEY")
model = os.getenv("DEEPSEEK_MODEL")

print(f"API Base: {api_base}")
print(f"Model: {model}")
print(f"API Key: {api_key[:10]}...")

# 创建 LLM 实例
llm = ChatOpenAI(
    base_url=api_base,
    api_key=api_key,
    model=model,
)

# 发送测试消息
try:
    response = llm.invoke("你是谁？")
    print(f"\n响应: {response.content}")
    print("\n✅ DEEPSEEK 模型连接成功!")
except Exception as e:
    print(f"\n❌ 连接失败: {e}")