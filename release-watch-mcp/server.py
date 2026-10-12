"""Small stdio MCP server implementing the 2025-03-26 tool protocol."""
import argparse
import json
import sys
import core

DATES = {'type': 'object', 'properties': {
    'since': {'type': 'string', 'description': '起始日期 YYYY-MM-DD；預設昨天（台灣時間）'},
    'through': {'type': 'string', 'description': '結束日期 YYYY-MM-DD；預設今天（台灣時間）'}
}, 'additionalProperties': False}
TOOLS = [
    {'name': 'get_watch_status', 'description': '查看 Said the Sky 追蹤設定與憑證就緒狀態，不回傳秘密。', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'check_new_releases', 'description': '查詢 Spotify 在指定日期範圍的專輯、單曲與合作作品；不寄信。', 'inputSchema': DATES},
    {'name': 'preview_notification', 'description': '查詢新作品並預覽寄給設定收件人的信件；不寄信。', 'inputSchema': DATES},
    {'name': 'send_release_notification', 'description': '實際透過 Gmail 寄送未通知的新作品至設定收件人，沒有新作品時不寄信。', 'inputSchema': DATES}
]


def call_tool(name, arguments):
    if not isinstance(arguments, dict):
        raise core.WatchError('arguments 必須是物件。')
    allowed = set() if name == 'get_watch_status' else {'since', 'through'}
    if set(arguments) - allowed or any(not isinstance(value, str) for value in arguments.values()):
        raise core.WatchError('工具參數不合法。')
    if name == 'get_watch_status':
        return core.status()
    if name == 'check_new_releases':
        return core.check_releases(**arguments)
    if name == 'preview_notification':
        return core.notification_preview(core.check_releases(**arguments))
    if name == 'send_release_notification':
        return core.notify(**arguments)
    raise core.WatchError('未知工具。')


def run_stdio():
    initialized = False
    ready = False
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except ValueError:
            print(json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}), flush=True)
            continue
        if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'), str):
            print(json.dumps({'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid Request'}}), flush=True)
            continue
        method = request['method']
        if 'id' not in request:
            if method == 'notifications/initialized' and initialized:
                ready = True
            continue
        response = {'jsonrpc': '2.0', 'id': request['id']}
        params = request.get('params', {})
        try:
            if not isinstance(params, dict):
                response['error'] = {'code': -32602, 'message': 'Invalid params'}
            elif method == 'initialize':
                initialized = True
                ready = False
                response['result'] = {'protocolVersion': '2025-03-26', 'capabilities': {'tools': {'listChanged': False}}, 'serverInfo': {'name': 'dj-fat-release-watch', 'version': '1.0.0'}}
            elif method == 'ping':
                response['result'] = {}
            elif not ready:
                response['error'] = {'code': -32600, 'message': 'Initialize the MCP session first'}
            elif method == 'tools/list':
                response['result'] = {'tools': TOOLS}
            elif method == 'tools/call':
                if params.get('name') not in {tool['name'] for tool in TOOLS}:
                    response['error'] = {'code': -32602, 'message': 'Unknown tool'}
                else:
                    try:
                        result = call_tool(params['name'], params.get('arguments', {}))
                        response['result'] = {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}], 'isError': False}
                    except (core.WatchError, ValueError, OSError, KeyError):
                        # Only deliberate user-facing messages are safe to expose.
                        error = sys.exc_info()[1]
                        message = str(error) if isinstance(error, core.WatchError) else '設定或服務回應不正確，請檢查設定與授權。'
                        response['result'] = {'content': [{'type': 'text', 'text': message}], 'isError': True}
            else:
                response['error'] = {'code': -32601, 'message': 'Method not found'}
        except Exception:
            response['error'] = {'code': -32603, 'message': 'Internal error'}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--notify', action='store_true', help='Run one scheduled notification check')
    parser.add_argument('--status', action='store_true')
    args = parser.parse_args()
    if args.notify or args.status:
        try:
            print(json.dumps(core.notify() if args.notify else core.status(), ensure_ascii=False, indent=2))
        except Exception as error:
            print(str(error) if isinstance(error, core.WatchError) else '設定或服務回應不正確。', file=sys.stderr)
            sys.exit(1)
    else:
        run_stdio()
