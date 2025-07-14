from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import os
import subprocess
import time
import hashlib
import uuid
from datetime import datetime

app = Flask(__name__)
CORS(app)

DATA_DIR = 'chat_data'
GLOBAL_MEMORY_FILE = 'xiaobu.md'
MAX_CONTEXT_LENGTH = 32000  # Claude上下文最大字符数限制
MAX_CONTEXT_PAIRS = 30     # 最大保留的对话轮数

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def load_global_memory():
    """加载全局记忆文件"""
    try:
        if os.path.exists(GLOBAL_MEMORY_FILE):
            with open(GLOBAL_MEMORY_FILE, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return ""
    except Exception as e:
        print(f"加载全局记忆文件失败: {e}")
        return ""

def get_client_id():
    """获取客户端唯一标识"""
    user_agent = request.headers.get('User-Agent', '')
    client_ip = request.remote_addr
    accept_language = request.headers.get('Accept-Language', '')
    accept_encoding = request.headers.get('Accept-Encoding', '')
    
    # 创建基于多个因素的唯一标识
    client_string = f"{client_ip}:{user_agent}:{accept_language}:{accept_encoding}"
    client_id = hashlib.md5(client_string.encode()).hexdigest()
    
    return client_id

def get_data_file(client_id):
    """根据客户端ID获取对应的数据文件路径"""
    ensure_data_dir()
    return os.path.join(DATA_DIR, f'chat_{client_id}.json')

def load_data(client_id):
    """加载指定客户端的数据"""
    data_file = get_data_file(client_id)
    if os.path.exists(data_file):
        with open(data_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'context': [], 'history': []}

def save_data(client_id, data):
    """保存指定客户端的数据"""
    data_file = get_data_file(client_id)
    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def calculate_context_length(context, global_memory=""):
    """计算上下文总长度"""
    context_text = '\n'.join(context) if context else ''
    total_text = global_memory + '\n\n' + context_text
    return len(total_text)

def trim_context(context, global_memory=""):
    """修剪上下文以适应长度限制"""
    if not context:
        return context
    
    # 计算全局记忆的长度
    global_memory_length = len(global_memory) + 100  # 加一些缓冲
    available_length = MAX_CONTEXT_LENGTH - global_memory_length
    
    # 如果可用长度太小，直接清空上下文
    if available_length < 500:
        print(f"可用上下文长度太小({available_length}字符)，清空上下文")
        return []
    
    # 从最新的对话开始，逐步添加直到达到长度限制
    trimmed_context = []
    current_length = 0
    
    # 确保context是成对的（用户+助手）
    # 从后往前取，保持最新的对话
    for i in range(len(context) - 1, -1, -1):
        item_length = len(context[i]) + 10  # 加一些格式化字符的长度
        
        if current_length + item_length > available_length:
            # 如果加上这一条会超限，就停止
            break
            
        trimmed_context.insert(0, context[i])
        current_length += item_length
        
        # 限制最大对话轮数
        if len(trimmed_context) >= MAX_CONTEXT_PAIRS * 2:  # 每轮包含用户和助手两条
            break
    
    # 确保context是成对的（如果有奇数条，移除最早的一条）
    if len(trimmed_context) % 2 == 1:
        trimmed_context = trimmed_context[1:]
    
    if len(trimmed_context) < len(context):
        removed_count = len(context) - len(trimmed_context)
        print(f"上下文修剪：移除了{removed_count}条早期对话，保留{len(trimmed_context)}条")
    
    return trimmed_context

def call_claude(message, context):
    try:
        # 加载全局记忆
        global_memory = load_global_memory()
        
        # 修剪上下文以适应长度限制
        trimmed_context = trim_context(context, global_memory)
        
        # 构建完整的prompt
        prompt_parts = []
        
        # 添加全局记忆作为系统提示
        if global_memory:
            prompt_parts.append(f"# 系统提示\n{global_memory}")
        
        # 添加对话上下文
        if trimmed_context:
            prompt_parts.append(f"# 对话上下文\n{chr(10).join(trimmed_context)}")
        
        # 添加用户消息
        prompt_parts.append(f"# 用户消息\n{message}")
        
        # 组合完整prompt
        full_prompt = '\n\n'.join(prompt_parts)
        
        # 打印调试信息
        total_length = len(full_prompt)
        print(f"完整prompt长度: {total_length}字符")
        print(f"用户输入: {message[:100]}{'...' if len(message) > 100 else ''}")
        
        result = subprocess.run(
            ['claude', '-p', full_prompt],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            response = result.stdout.strip()
            print(f"Bot回复: {response[:100]}{'...' if len(response) > 100 else ''}")
            return response, None
        else:
            error = result.stderr.strip()
            print(f"错误信息: {error}")
            return None, error
    except subprocess.TimeoutExpired:
        return None, "请求超时"
    except FileNotFoundError:
        return None, "Claude 命令未找到"
    except Exception as e:
        return None, str(e)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    client_id = get_client_id()
    data = request.json
    message = data.get('message', '').strip()
    
    print(f"\n=== 新对话请求 ===")
    print(f"客户端ID: {client_id[:8]}...")
    print(f"请求时间: {datetime.now().strftime('%H:%M:%S')}")
    
    if not message:
        return jsonify({'error': '消息不能为空'}), 400
    
    chat_data = load_data(client_id)
    
    if message == '/clear':
        print(f"执行清空上下文命令")
        chat_data['context'] = []
        chat_data['history'].append({
            'type': 'system',
            'content': '上下文已清空',
            'timestamp': datetime.now().isoformat()
        })
        save_data(client_id, chat_data)
        print(f"上下文已清空，历史记录保留 {len(chat_data['history'])} 条")
        return jsonify({
            'message': '上下文已清空',
            'history': chat_data['history'][-42:]
        })
    
    chat_data['history'].append({
        'type': 'user',
        'content': message,
        'timestamp': datetime.now().isoformat()
    })
    
    response, error = call_claude(message, chat_data['context'])
    
    if error:
        response, error = call_claude(message, chat_data['context'])
    
    if error:
        chat_data['history'].append({
            'type': 'error',
            'content': f'错误: {error}',
            'timestamp': datetime.now().isoformat()
        })
        save_data(client_id, chat_data)
        return jsonify({
            'error': error,
            'history': chat_data['history'][-42:]
        }), 500
    
    chat_data['context'].append(f"用户: {message}")
    chat_data['context'].append(f"助手: {response}")
    
    # 修剪上下文
    global_memory = load_global_memory()
    chat_data['context'] = trim_context(chat_data['context'], global_memory)
    
    chat_data['history'].append({
        'type': 'bot',
        'content': response,
        'timestamp': datetime.now().isoformat()
    })
    
    save_data(client_id, chat_data)
    
    print(f"上下文条目数: {len(chat_data['context'])}")
    print(f"历史记录数: {len(chat_data['history'])}")
    print(f"=== 对话完成 ===\n")
    
    return jsonify({
        'message': response,
        'history': chat_data['history'][-42:]
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    client_id = get_client_id()
    chat_data = load_data(client_id)
    return jsonify({'history': chat_data['history'][-42:]})

@app.route('/api/client-info', methods=['GET'])
def get_client_info():
    """获取客户端信息（调试用）"""
    client_id = get_client_id()
    return jsonify({
        'client_id': client_id,
        'user_agent': request.headers.get('User-Agent', ''),
        'client_ip': request.remote_addr,
        'accept_language': request.headers.get('Accept-Language', ''),
        'accept_encoding': request.headers.get('Accept-Encoding', ''),
        'data_file': get_data_file(client_id)
    })

@app.route('/api/global-memory', methods=['GET'])
def get_global_memory():
    """获取全局记忆内容"""
    memory = load_global_memory()
    return jsonify({
        'content': memory,
        'file': GLOBAL_MEMORY_FILE
    })

@app.route('/api/global-memory', methods=['POST'])
def update_global_memory():
    """更新全局记忆内容"""
    try:
        data = request.json
        content = data.get('content', '')
        
        with open(GLOBAL_MEMORY_FILE, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return jsonify({
            'success': True,
            'message': '全局记忆更新成功'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/context-info', methods=['GET'])
def get_context_info():
    """获取上下文信息（调试用）"""
    client_id = get_client_id()
    chat_data = load_data(client_id)
    global_memory = load_global_memory()
    
    context_length = calculate_context_length(chat_data['context'], global_memory)
    
    return jsonify({
        'client_id': client_id,
        'context_items': len(chat_data['context']),
        'context_length': context_length,
        'global_memory_length': len(global_memory),
        'max_context_length': MAX_CONTEXT_LENGTH,
        'max_context_pairs': MAX_CONTEXT_PAIRS,
        'context_preview': chat_data['context'][-4:] if chat_data['context'] else []
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)