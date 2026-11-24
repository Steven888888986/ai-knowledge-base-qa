"""Minimal stdio MCP-style server for local integration.

It intentionally implements the small JSON-RPC subset needed by a demo client:
initialize, tools/list, and tools/call(search_knowledge_base).
"""
import json, sys
from app import query

def main():
    for line in sys.stdin:
        try:
            req=json.loads(line); method=req.get("method"); params=req.get("params", {})
            if method == "initialize": result={"protocolVersion":"2024-11-05","capabilities":{"tools":{}},"serverInfo":{"name":"kbqa","version":"1.0"}}
            elif method == "tools/list": result={"tools":[{"name":"search_knowledge_base","description":"Search indexed AI knowledge with citations","inputSchema":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}]}
            elif method == "tools/call" and params.get("name")=="search_knowledge_base": result={"content":[{"type":"text","text":json.dumps(query(params.get("arguments",{}).get("query", "")), ensure_ascii=False)}]}
            else: result={"error":{"code":-32601,"message":"method not found"}}
            print(json.dumps({"jsonrpc":"2.0","id":req.get("id"),"result":result},ensure_ascii=False),flush=True)
        except Exception as e: print(json.dumps({"jsonrpc":"2.0","id":None,"error":{"code":-32603,"message":str(e)}}),flush=True)
if __name__ == "__main__": main()
