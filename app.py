from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
import json
import os
import subprocess
import time
import hashlib
import uuid
import psutil
import threading
from datetime import datetime, timedelta
from collections import deque
import re
import requests

app = Flask(__name__)
CORS(app)

DATA_DIR = 'chat_data'
GLOBAL_MEMORY_FILE = 'xiaobu.md'
MAX_CONTEXT_LENGTH = 32000  # Claude上下文最大字符数限制
MAX_CONTEXT_PAIRS = 30     # 最大保留的对话轮数

# 服务状态监控配置
SERVICE_STATUS = {
    'status': 'running',
    'start_time': datetime.now().isoformat(),
    'request_count': 0,
    'error_count': 0,
    'last_request_time': None,
    'cpu_usage': 0.0,
    'memory_usage': 0.0,
    'disk_usage': 0.0
}

# 情绪分析配置
EMOTION_HISTORY = deque(maxlen=100)
EMOTION_KEYWORDS = {
    'happy': ['开心', '高兴', '快乐', '愉快', '兴奋', '棒', '好', '喜欢', '满意', '赞'],
    'sad': ['难过', '伤心', '悲伤', '失望', '沮丧', '糟糕', '不好', '痛苦', '遗憾'],
    'angry': ['生气', '愤怒', '烦躁', '气愤', '恼火', '讨厌', '怒', '不爽', '愤慨'],
    'anxious': ['紧张', '焦虑', '担心', '不安', '害怕', '恐惧', '忧虑', '压力'],
    'excited': ['激动', '兴奋', '刺激', '热血', '热情', '振奋', '雀跃'],
    'neutral': ['一般', '普通', '正常', '还行', '凑合', '还可以']
}

# 小布情绪系统配置
XIAOBU_STATE = {
    'base_emotion': 50,  # 基础情绪值 (0-100)
    'weather_factor': 0,  # 天气影响因子
    'chat_load_factor': 0,  # 聊天负载因子
    'sentiment_factor': 0,  # 情感影响因子
    'last_weather_update': None,
    'chat_frequency': deque(maxlen=50),  # 记录最近50次聊天时间
    'weather_cache': None,
    'weather_cache_time': None
}

# 情绪emoji映射
EMOTION_EMOJIS = {
    'very_happy': '😊',
    'happy': '😄', 
    'neutral': '😐',
    'sad': '😢',
    'very_sad': '😭',
    'angry': '😠',
    'anxious': '😰',
    'excited': '🤩',
    'tired': '😴',
    'stressed': '😵'
}

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def get_wuhan_weather():
    """获取武汉天气信息"""
    try:
        # 如果缓存有效（15分钟内），直接返回缓存
        if (XIAOBU_STATE['weather_cache'] and 
            XIAOBU_STATE['weather_cache_time'] and
            (datetime.now() - XIAOBU_STATE['weather_cache_time']).total_seconds() < 900):
            return XIAOBU_STATE['weather_cache']
        
        # 使用免费天气API (OpenWeatherMap或其他)
        # 这里使用一个简化的天气模拟，实际使用时需要替换为真实API
        weather_data = {
            'temperature': 22,  # 温度
            'humidity': 65,     # 湿度
            'condition': 'cloudy',  # 天气状况: sunny, cloudy, rainy, snowy
            'air_quality': 85,  # 空气质量指数
            'comfort_index': 75  # 舒适度指数
        }
        
        # 更新缓存
        XIAOBU_STATE['weather_cache'] = weather_data
        XIAOBU_STATE['weather_cache_time'] = datetime.now()
        
        return weather_data
    except Exception as e:
        print(f"获取天气信息失败: {e}")
        return None

def calculate_weather_factor():
    """计算天气对情绪的影响因子"""
    weather = get_wuhan_weather()
    if not weather:
        return 0
    
    factor = 0
    
    # 温度影响 (18-26度为舒适区间)
    temp = weather['temperature']
    if 18 <= temp <= 26:
        factor += 10  # 舒适温度增加情绪
    elif temp < 10 or temp > 35:
        factor -= 15  # 极端温度降低情绪
    elif temp < 18 or temp > 26:
        factor -= 5   # 轻微不适温度
    
    # 天气状况影响
    condition = weather['condition']
    if condition == 'sunny':
        factor += 15
    elif condition == 'cloudy':
        factor += 5
    elif condition == 'rainy':
        factor -= 10
    elif condition == 'snowy':
        factor -= 5
    
    # 空气质量影响
    aqi = weather['air_quality']
    if aqi <= 50:
        factor += 5   # 优秀空气质量
    elif aqi > 150:
        factor -= 10  # 较差空气质量
    
    return max(-20, min(20, factor))  # 限制在-20到20之间

def calculate_chat_load_factor():
    """计算聊天负载对情绪的影响因子"""
    now = datetime.now()
    recent_chats = XIAOBU_STATE['chat_frequency']
    
    if len(recent_chats) < 2:
        return 0, "聊天记录较少"
    
    # 计算最近10分钟的聊天频率
    ten_minutes_ago = now - timedelta(minutes=10)
    recent_10min = [t for t in recent_chats if t > ten_minutes_ago]
    
    factor = 0
    chat_count = len(recent_10min)
    
    if chat_count > 30:  # 高频聊天，增加压力
        factor = -15
        reason = "聊天频率过高感到疲劳"
    elif chat_count > 15:
        factor = -8
        reason = "聊天较为频繁有些累"
    elif chat_count < 3:  # 聊天频率低，可能无聊
        factor = -5
        reason = "聊天较少感到无聊"
    else:  # 适中频率
        factor = 5
        reason = "聊天频率刚好"
    
    return factor, reason

def calculate_sentiment_factor():
    """计算用户情感对情绪的影响因子"""
    if not EMOTION_HISTORY:
        return 0, "暂无情感数据"
    
    # 分析最近10条对话的情感
    recent_emotions = list(EMOTION_HISTORY)[-10:]
    
    positive_emotions = ['happy', 'excited']
    negative_emotions = ['sad', 'angry', 'anxious']
    
    positive_count = sum(1 for e in recent_emotions if e['user_emotion'] in positive_emotions)
    negative_count = sum(1 for e in recent_emotions if e['user_emotion'] in negative_emotions)
    
    # 计算情感倾向
    if positive_count > negative_count:
        factor = min(15, positive_count * 3)
        reason = f"用户积极情绪较多({positive_count}次)"
    elif negative_count > positive_count:
        factor = max(-15, -negative_count * 3)
        reason = f"用户消极情绪较多({negative_count}次)"
    else:
        factor = 0
        reason = "用户情绪相对平衡"
    
    return factor, reason

def calculate_xiaobu_emotion():
    """计算小布的当前情绪状态"""
    # 更新各种影响因子
    weather_factor = calculate_weather_factor()
    chat_load_factor, chat_reason = calculate_chat_load_factor()
    sentiment_factor, sentiment_reason = calculate_sentiment_factor()
    
    # 计算总情绪值
    total_emotion = (XIAOBU_STATE['base_emotion'] + 
                    weather_factor + 
                    chat_load_factor + 
                    sentiment_factor)
    
    # 限制在0-100范围内
    total_emotion = max(0, min(100, total_emotion))
    
    # 更新状态
    XIAOBU_STATE['weather_factor'] = weather_factor
    XIAOBU_STATE['chat_load_factor'] = chat_load_factor
    XIAOBU_STATE['sentiment_factor'] = sentiment_factor
    
    # 确定情绪类型和原因
    if total_emotion >= 80:
        emotion_type = 'very_happy'
        reason = "心情很好"
    elif total_emotion >= 65:
        emotion_type = 'happy' 
        reason = "心情不错"
    elif total_emotion >= 45:
        emotion_type = 'neutral'
        reason = "心情一般"
    elif total_emotion >= 30:
        emotion_type = 'sad'
        reason = "有点不开心"
    else:
        emotion_type = 'very_sad'
        reason = "心情很低落"
    
    # 根据主要影响因子调整原因
    factors = [
        (abs(weather_factor), "天气" if weather_factor > 0 else "天气不好"),
        (abs(chat_load_factor), chat_reason),
        (abs(sentiment_factor), sentiment_reason)
    ]
    
    # 找到影响最大的因子
    max_factor = max(factors, key=lambda x: x[0])
    if max_factor[0] > 5:  # 如果影响因子足够大
        reason = max_factor[1]
    
    return {
        'emotion_value': total_emotion,
        'emotion_type': emotion_type,
        'emoji': EMOTION_EMOJIS[emotion_type],
        'reason': reason[:10],  # 限制10个字以内
        'factors': {
            'weather': weather_factor,
            'chat_load': chat_load_factor, 
            'sentiment': sentiment_factor,
            'base': XIAOBU_STATE['base_emotion']
        }
    }

def record_chat_time():
    """记录聊天时间用于负载计算"""
    XIAOBU_STATE['chat_frequency'].append(datetime.now())

def update_system_metrics():
    """更新系统性能指标"""
    try:
        SERVICE_STATUS['cpu_usage'] = psutil.cpu_percent(interval=1)
        SERVICE_STATUS['memory_usage'] = psutil.virtual_memory().percent
        SERVICE_STATUS['disk_usage'] = psutil.disk_usage('/').percent
    except Exception as e:
        print(f"更新系统指标失败: {e}")

def analyze_emotion(text):
    """分析文本情绪"""
    emotion_scores = {emotion: 0 for emotion in EMOTION_KEYWORDS.keys()}
    
    for emotion, keywords in EMOTION_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                emotion_scores[emotion] += 1
    
    # 找到得分最高的情绪
    max_emotion = max(emotion_scores, key=emotion_scores.get)
    max_score = emotion_scores[max_emotion]
    
    # 如果没有匹配到关键词，返回neutral
    if max_score == 0:
        return 'neutral', 0.1
    
    # 计算置信度
    total_score = sum(emotion_scores.values())
    confidence = max_score / total_score if total_score > 0 else 0
    
    return max_emotion, confidence

def record_emotion(user_message, bot_response):
    """记录对话的情绪数据"""
    user_emotion, user_confidence = analyze_emotion(user_message)
    bot_emotion, bot_confidence = analyze_emotion(bot_response)
    
    emotion_record = {
        'timestamp': datetime.now().isoformat(),
        'user_emotion': user_emotion,
        'user_confidence': user_confidence,
        'bot_emotion': bot_emotion,
        'bot_confidence': bot_confidence,
        'user_message_length': len(user_message),
        'bot_message_length': len(bot_response)
    }
    
    EMOTION_HISTORY.append(emotion_record)
    return emotion_record

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
    
    # 更新服务状态
    SERVICE_STATUS['request_count'] += 1
    SERVICE_STATUS['last_request_time'] = datetime.now().isoformat()
    
    # 记录聊天时间用于负载计算
    record_chat_time()
    
    print(f"\n=== 新对话请求 ===")
    print(f"客户端ID: {client_id[:8]}...")
    print(f"请求时间: {datetime.now().strftime('%H:%M:%S')}")
    
    if not message:
        SERVICE_STATUS['error_count'] += 1
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
        SERVICE_STATUS['error_count'] += 1
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
    
    # 记录情绪数据
    emotion_record = record_emotion(message, response)
    
    # 修剪上下文
    global_memory = load_global_memory()
    chat_data['context'] = trim_context(chat_data['context'], global_memory)
    
    chat_data['history'].append({
        'type': 'bot',
        'content': response,
        'timestamp': datetime.now().isoformat(),
        'emotion': emotion_record
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

@app.route('/api/service-status', methods=['GET'])
def get_service_status():
    """获取服务状态信息"""
    # 更新系统指标
    update_system_metrics()
    
    # 计算运行时间
    start_time = datetime.fromisoformat(SERVICE_STATUS['start_time'])
    uptime_seconds = (datetime.now() - start_time).total_seconds()
    uptime_hours = uptime_seconds / 3600
    
    # 计算错误率
    error_rate = 0
    if SERVICE_STATUS['request_count'] > 0:
        error_rate = (SERVICE_STATUS['error_count'] / SERVICE_STATUS['request_count']) * 100
    
    status_info = {
        **SERVICE_STATUS,
        'uptime_hours': round(uptime_hours, 2),
        'uptime_seconds': int(uptime_seconds),
        'error_rate': round(error_rate, 2),
        'system_info': {
            'python_version': os.sys.version,
            'platform': os.name,
            'current_time': datetime.now().isoformat()
        }
    }
    
    return jsonify(status_info)

@app.route('/api/emotions', methods=['GET'])
def get_emotions():
    """获取情绪分析数据"""
    limit = request.args.get('limit', 50, type=int)
    
    # 获取最近的情绪记录
    recent_emotions = list(EMOTION_HISTORY)[-limit:]
    
    # 统计情绪分布
    emotion_counts = {}
    total_confidence = {}
    
    for record in recent_emotions:
        user_emotion = record['user_emotion']
        bot_emotion = record['bot_emotion']
        
        # 统计用户情绪
        if user_emotion not in emotion_counts:
            emotion_counts[user_emotion] = {'user': 0, 'bot': 0}
            total_confidence[user_emotion] = {'user': 0, 'bot': 0}
        
        emotion_counts[user_emotion]['user'] += 1
        total_confidence[user_emotion]['user'] += record['user_confidence']
        
        # 统计机器人情绪
        if bot_emotion not in emotion_counts:
            emotion_counts[bot_emotion] = {'user': 0, 'bot': 0}
            total_confidence[bot_emotion] = {'user': 0, 'bot': 0}
        
        emotion_counts[bot_emotion]['bot'] += 1
        total_confidence[bot_emotion]['bot'] += record['bot_confidence']
    
    # 计算平均置信度
    emotion_stats = {}
    for emotion in emotion_counts:
        user_count = emotion_counts[emotion]['user']
        bot_count = emotion_counts[emotion]['bot']
        
        emotion_stats[emotion] = {
            'user_count': user_count,
            'bot_count': bot_count,
            'user_avg_confidence': round(total_confidence[emotion]['user'] / user_count, 3) if user_count > 0 else 0,
            'bot_avg_confidence': round(total_confidence[emotion]['bot'] / bot_count, 3) if bot_count > 0 else 0
        }
    
    return jsonify({
        'recent_emotions': recent_emotions,
        'emotion_statistics': emotion_stats,
        'total_records': len(EMOTION_HISTORY),
        'returned_records': len(recent_emotions)
    })

@app.route('/api/emotions/summary', methods=['GET'])
def get_emotion_summary():
    """获取情绪摘要统计"""
    if not EMOTION_HISTORY:
        return jsonify({
            'message': '暂无情绪数据',
            'total_conversations': 0
        })
    
    # 最近的情绪记录
    latest_record = EMOTION_HISTORY[-1] if EMOTION_HISTORY else None
    
    # 统计最近10条记录的情绪趋势
    recent_10 = list(EMOTION_HISTORY)[-10:]
    user_emotions = [r['user_emotion'] for r in recent_10]
    bot_emotions = [r['bot_emotion'] for r in recent_10]
    
    # 计算主导情绪
    from collections import Counter
    user_emotion_trend = Counter(user_emotions).most_common(1)
    bot_emotion_trend = Counter(bot_emotions).most_common(1)
    
    return jsonify({
        'latest_emotion': latest_record,
        'total_conversations': len(EMOTION_HISTORY),
        'recent_trend': {
            'user_dominant_emotion': user_emotion_trend[0][0] if user_emotion_trend else 'neutral',
            'bot_dominant_emotion': bot_emotion_trend[0][0] if bot_emotion_trend else 'neutral',
            'sample_size': len(recent_10)
        },
        'available_emotions': list(EMOTION_KEYWORDS.keys())
    })

@app.route('/api/xiaobu/emotion', methods=['GET'])
def get_xiaobu_emotion():
    """获取小布的当前情绪状态"""
    emotion_state = calculate_xiaobu_emotion()
    weather_data = get_wuhan_weather()
    
    return jsonify({
        'timestamp': datetime.now().isoformat(),
        'emotion': emotion_state['emotion_type'],
        'emoji': emotion_state['emoji'],
        'reason': emotion_state['reason'],
        'emotion_value': emotion_state['emotion_value'],
        'factors': emotion_state['factors'],
        'weather': weather_data,
        'chat_frequency_recent': len([t for t in XIAOBU_STATE['chat_frequency'] 
                                    if (datetime.now() - t).total_seconds() < 600]),
        'total_chats_today': len(XIAOBU_STATE['chat_frequency'])
    })

@app.route('/api/realtime/status')
def realtime_status():
    """Server-Sent Events实时推送服务状态"""
    def generate():
        while True:
            try:
                # 更新系统指标
                update_system_metrics()
                
                # 构建状态数据
                data = {
                    'timestamp': datetime.now().isoformat(),
                    'cpu_usage': SERVICE_STATUS['cpu_usage'],
                    'memory_usage': SERVICE_STATUS['memory_usage'],
                    'disk_usage': SERVICE_STATUS['disk_usage'],
                    'request_count': SERVICE_STATUS['request_count'],
                    'error_count': SERVICE_STATUS['error_count'],
                    'error_rate': (SERVICE_STATUS['error_count'] / SERVICE_STATUS['request_count'] * 100) if SERVICE_STATUS['request_count'] > 0 else 0
                }
                
                yield f"data: {json.dumps(data)}\n\n"
                time.sleep(5)  # 每5秒推送一次
            except Exception as e:
                print(f"SSE错误: {e}")
                break
    
    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/realtime/emotions')
def realtime_emotions():
    """Server-Sent Events实时推送情绪数据"""
    def generate():
        last_count = 0
        while True:
            try:
                current_count = len(EMOTION_HISTORY)
                
                # 只在有新数据时推送
                if current_count > last_count:
                    # 获取最新的情绪记录
                    new_records = list(EMOTION_HISTORY)[last_count:]
                    
                    data = {
                        'timestamp': datetime.now().isoformat(),
                        'new_emotions': new_records,
                        'total_count': current_count
                    }
                    
                    yield f"data: {json.dumps(data)}\n\n"
                    last_count = current_count
                
                time.sleep(2)  # 每2秒检查一次
            except Exception as e:
                print(f"SSE情绪推送错误: {e}")
                break
    
    return Response(generate(), mimetype='text/event-stream')

def start_background_monitoring():
    """启动后台监控线程"""
    def monitor():
        while True:
            try:
                update_system_metrics()
                time.sleep(30)  # 每30秒更新一次系统指标
            except Exception as e:
                print(f"后台监控错误: {e}")
                time.sleep(60)
    
    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()
    print("后台监控线程已启动")

if __name__ == '__main__':
    print("启动Claude聊天机器人服务...")
    print("API端点:")
    print("- GET  /api/service-status     - 获取服务状态")
    print("- GET  /api/emotions           - 获取情绪分析数据")
    print("- GET  /api/emotions/summary   - 获取情绪摘要")
    print("- GET  /api/xiaobu/emotion     - 获取小布情绪状态")
    print("- GET  /api/realtime/status    - 实时服务状态推送(SSE)")
    print("- GET  /api/realtime/emotions  - 实时情绪数据推送(SSE)")
    
    # 启动后台监控
    start_background_monitoring()
    
    app.run(debug=True, host='0.0.0.0', port=8080)