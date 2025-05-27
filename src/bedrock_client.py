import boto3, json, os
br = boto3.client("bedrock-runtime", region_name=os.getenv("AWS_REGION","us-east-1"))

def claude_chat(prompt, max_tokens=400, temp=0.3):
    body = {
      "anthropic_version": "bedrock-2023-05-31",
      "messages":[{"role":"user","content":prompt}],
      "max_tokens": max_tokens, "temperature": temp
    }
    out = br.invoke_model(
      modelId="anthropic.claude-3-sonnet-20240229-v1:0",
      body=json.dumps(body),
      contentType="application/json",
      accept="application/json")
    return json.loads(out["body"].read())["content"][0]["text"]

def titan_embed(texts):
    out = br.invoke_model(
      modelId="amazon.titan-embed-text-multilingual-v1:0",
      body=json.dumps({"inputText": texts}),
      contentType="application/json",
      accept="application/json")
    return [json.loads(out["body"].read())["embedding"]]
