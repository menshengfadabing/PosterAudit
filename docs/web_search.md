Web Search("火山引擎 豆包模型 doubao-seed max_tokens 输出限制 2026
编辑
复制
分享
搜索网页
火山引擎 豆包模型 doubao-seed max_tokens 输出限制 2026
11 个结果
根据火山引擎官方文档，以下是豆包模型（Doubao-seed 系列）的 max_tokens 输出限制信息：
豆包模型输出限制汇总
表格
模型版本	最大输出长度 (max_tokens)	最大输出总长度 (max_completion_tokens)	思维链长度限制
doubao-seed-1.8	64k	64k	32k
doubao-seed-2.0 系列	各模型不同（见模型列表）	64k	各模型不同
关键参数说明 
max_tokens：控制模型回答的最大长度（单位：token），不包含思维链内容。默认值为 4096（4k）。
max_completion_tokens：控制模型输出的总长度（包括回答 + 思维链内容），取值范围为 [0, 64k]。配置此参数后，max_tokens 的默认值会失效，可用于超长文本输出场景。
重要限制：
max_tokens 和 max_completion_tokens 不可同时设置，否则会直接报错
Responses API 不支持 max_tokens 字段
Chat API 支持 max_completion_tokens 字段（250528及之后版本的大语言模型）
doubao-seed-1.8 具体规格 
上下文窗口：256k
最大输入长度：224k
最大思维链内容长度：32k
最大输出长度：64k
使用示例
Python
复制
# 设置最大输出长度为 1024 token（仅回答部分）
max_tokens=1024

# 或设置总输出长度为 32k（回答 + 思维链）
max_completion_tokens=32768
如需获取特定 doubao-seed-2.0 版本（Pro/Lite/Mini）的详细限制，建议查阅火山引擎官方模型列表页面 。