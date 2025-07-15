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
import random

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
    'time_factor': 0,  # 时间因子（基于作息时间）
    'adolescent_factor': 0,  # 青春期随机因子
    'last_weather_update': None,
    'chat_frequency': deque(maxlen=50),  # 记录最近50次聊天时间
    'weather_cache': None,
    'weather_cache_time': None,
    'last_mood_swing': None,  # 上次情绪波动时间
    'current_hormonal_state': 'normal',  # 当前荷尔蒙状态
    'stress_level': 0,  # 压力等级 (0-100)
}

# 初中生作息时间表
DAILY_SCHEDULE = {
    'weekday': {
        'sleep': [(22, 0), (6, 0)],  # 22:00-6:00 睡眠时间
        'breakfast': (7, 0, 8, 0),  # 7:00-8:00 早餐
        'morning_study': (8, 0, 12, 0),  # 8:00-12:00 上午学习
        'lunch': (12, 0, 13, 0),  # 12:00-13:00 午餐
        'afternoon_nap': (13, 0, 14, 0),  # 13:00-14:00 午休
        'afternoon_study': (14, 0, 17, 0),  # 14:00-17:00 下午学习
        'dinner': (17, 0, 18, 0),  # 17:00-18:00 晚餐
        'evening_study': (18, 0, 21, 0),  # 18:00-21:00 晚自习
        'free_time': (21, 0, 22, 0),  # 21:00-22:00 自由时间
    },
    'weekend': {
        'sleep_in': (22, 0, 10, 0),  # 22:00-10:00 补觉
        'outdoor_morning': (10, 0, 12, 0),  # 10:00-12:00 户外活动
        'lunch': (12, 0, 13, 0),  # 12:00-13:00 午餐
        'afternoon_rest': (13, 0, 15, 0),  # 13:00-15:00 自由时间
        'outdoor_afternoon': (15, 0, 18, 0),  # 15:00-18:00 户外活动
        'dinner': (18, 0, 19, 0),  # 18:00-19:00 晚餐
        'entertainment': (19, 0, 22, 0),  # 19:00-22:00 娱乐时间
    }
}

# 小布身份信息
XIAOBU_IDENTITY = {
    'name': '小布',
    'age': 14,
    'grade': '初二',
    'school': '武汉市第三中学',
    'nationality': '中国',
    'location': '武汉',
    'birthday': '2010-03-15',  # 2010年3月15日生
    'interests': ['骑车', '露营', '徒步', '游戏', '动漫', '篮球'],
    'subjects': {
        'favorite': ['体育', '美术'],
        'difficult': ['数学', '物理'],
        'okay': ['语文', '英语', '历史', '地理']
    }
}

# 中国学生假期配置
HOLIDAY_CALENDAR = {
    'winter_vacation': {  # 寒假
        'start_month': 1, 'start_day': 15,
        'end_month': 2, 'end_day': 25,
        'description': '寒假'
    },
    'summer_vacation': {  # 暑假  
        'start_month': 7, 'start_day': 1,
        'end_month': 8, 'end_day': 31,
        'description': '暑假'
    },
    'national_holidays': [  # 法定节假日
        {'month': 1, 'day': 1, 'name': '元旦', 'days': 1},
        {'month': 2, 'day': 10, 'name': '春节', 'days': 7},  # 农历新年，日期会变
        {'month': 4, 'day': 5, 'name': '清明节', 'days': 1},
        {'month': 5, 'day': 1, 'name': '劳动节', 'days': 3},
        {'month': 6, 'day': 22, 'name': '端午节', 'days': 1},  # 农历节日，日期会变
        {'month': 9, 'day': 15, 'name': '中秋节', 'days': 1},  # 农历节日，日期会变
        {'month': 10, 'day': 1, 'name': '国庆节', 'days': 7},
    ],
    'exam_periods': [  # 考试周期
        {'month': 1, 'start_day': 8, 'end_day': 14, 'name': '期末考试'},
        {'month': 6, 'start_day': 20, 'end_day': 25, 'name': '期末考试'},
        {'month': 11, 'start_day': 5, 'end_day': 10, 'name': '期中考试'},
        {'month': 5, 'start_day': 8, 'end_day': 12, 'name': '期中考试'},
    ]
}

# 青春期情绪波动配置
ADOLESCENT_MOODS = {
    'irritable': {'probability': 0.15, 'intensity': -20, 'duration': 60},  # 易怒
    'moody': {'probability': 0.12, 'intensity': -15, 'duration': 45},  # 情绪不稳
    'rebellious': {'probability': 0.08, 'intensity': -25, 'duration': 90},  # 叛逆
    'hyperactive': {'probability': 0.10, 'intensity': 25, 'duration': 30},  # 亢奋
    'emotional': {'probability': 0.18, 'intensity': -10, 'duration': 120},  # 敏感
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
    'stressed': '😵',
    'sleepy': '😴',
    'hungry': '😋',
    'energetic': '💪',
    'moody': '😤',
    'camping': '🏕️',
    'cycling': '🚴',
    'hiking': '🥾',
    'lazy_weekend': '😪',
    'studying': '📚',
    'rebellious': '😠',
    'irritated': '😒',
    'bored': '😑',
    'playful': '😜',
    'nervous': '😬',
    'confused': '😕'
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
    time_factor, time_reason, holiday_type, holiday_name = calculate_time_factor()
    adolescent_factor, adolescent_reason = calculate_adolescent_factor()
    stress_factor = update_stress_level()
    
    # 计算总情绪值
    total_emotion = (XIAOBU_STATE['base_emotion'] + 
                    weather_factor + 
                    chat_load_factor + 
                    sentiment_factor + 
                    time_factor + 
                    adolescent_factor - 
                    stress_factor * 0.3)  # 压力负面影响
    
    # 限制在0-100范围内
    total_emotion = max(0, min(100, total_emotion))
    
    # 更新状态
    XIAOBU_STATE['weather_factor'] = weather_factor
    XIAOBU_STATE['chat_load_factor'] = chat_load_factor
    XIAOBU_STATE['sentiment_factor'] = sentiment_factor
    XIAOBU_STATE['time_factor'] = time_factor
    XIAOBU_STATE['adolescent_factor'] = adolescent_factor
    
    # 获取当前时间段信息
    activity, is_weekend, _, _ = get_current_time_period()
    
    # 根据时间段和情绪值确定具体情绪类型
    emotion_type, reason = determine_emotion_type(total_emotion, activity, is_weekend, 
                                                 time_factor, adolescent_factor, 
                                                 holiday_type, holiday_name)
    
    # 根据主要影响因子调整原因
    factors = [
        (abs(weather_factor), "天气" if weather_factor > 0 else "天气不好"),
        (abs(chat_load_factor), chat_reason),
        (abs(sentiment_factor), sentiment_reason),
        (abs(time_factor), time_reason),
        (abs(adolescent_factor), adolescent_reason),
        (abs(stress_factor), "压力大" if stress_factor > 20 else "")
    ]
    
    # 找到影响最大的因子
    max_factor = max(factors, key=lambda x: x[0])
    if max_factor[0] > 10:  # 如果影响因子足够大
        reason = max_factor[1]
    
    return {
        'emotion_value': total_emotion,
        'emotion_type': emotion_type,
        'emoji': EMOTION_EMOJIS[emotion_type],
        'reason': reason[:10],  # 限制10个字以内
        'activity': activity,
        'is_weekend': is_weekend,
        'holiday_type': holiday_type,
        'holiday_name': holiday_name,
        'stress_level': XIAOBU_STATE['stress_level'],
        'identity': XIAOBU_IDENTITY,
        'factors': {
            'weather': weather_factor,
            'chat_load': chat_load_factor, 
            'sentiment': sentiment_factor,
            'time': time_factor,
            'adolescent': adolescent_factor,
            'stress': stress_factor,
            'base': XIAOBU_STATE['base_emotion']
        }
    }

def determine_emotion_type(emotion_value, activity, is_weekend, time_factor, adolescent_factor, holiday_type, holiday_name):
    """根据情绪值和当前活动确定具体的情绪类型"""
    
    # 假期特殊状态
    if holiday_type == 'winter_vacation':
        if emotion_value >= 80:
            return 'very_happy', "寒假开心"
        elif activity == 'sleep_in' and emotion_value < 30:
            return 'sleepy', "寒假被吵醒"
        else:
            return 'happy', "寒假心情好"
    
    elif holiday_type == 'summer_vacation':
        if emotion_value >= 85:
            return 'very_happy', "暑假太爽"
        elif activity in ['outdoor_morning', 'outdoor_afternoon']:
            activities = ['camping', 'cycling', 'hiking']
            chosen = random.choice(activities)
            return chosen, f"暑假想{['露营', '骑车', '徒步'][activities.index(chosen)]}"
        else:
            return 'happy', "暑假开心"
    
    elif holiday_type == 'national_holiday':
        return 'happy', f"{holiday_name}开心"
    
    elif holiday_type == 'exam_period':
        if emotion_value < 30:
            return 'stressed', f"{holiday_name}焦虑"
        elif activity in ['morning_study', 'afternoon_study', 'evening_study']:
            return 'anxious', "考试压力大"
        else:
            return 'nervous', "考试紧张"
    
    # 特殊情况：睡眠被打扰
    if activity in ['sleep', 'sleep_in'] and emotion_value < 40:
        return 'sleepy', "被吵醒了"
    
    # 青春期特殊状态
    if XIAOBU_STATE['current_hormonal_state'] != 'normal':
        hormonal_state = XIAOBU_STATE['current_hormonal_state']
        if hormonal_state == 'irritable':
            return 'irritated', "心情烦躁"
        elif hormonal_state == 'rebellious':
            return 'rebellious', "有点叛逆"
        elif hormonal_state == 'moody':
            return 'moody', "情绪不稳"
        elif hormonal_state == 'hyperactive':
            return 'energetic', "精力充沛"
        elif hormonal_state == 'emotional':
            return 'anxious', "情绪敏感"
    
    # 饥饿状态
    if activity in ['breakfast', 'lunch', 'dinner'] and time_factor < -15:
        return 'hungry', "肚子饿了"
    
    # 周末户外活动
    if is_weekend and activity in ['outdoor_morning', 'outdoor_afternoon']:
        if emotion_value >= 70:
            activities = {
                'camping': '想露营',
                'cycling': '想骑车', 
                'hiking': '想徒步'
            }
            chosen = random.choice(list(activities.keys()))
            return chosen, activities[chosen]
        else:
            return 'lazy_weekend', "周末想躺平"
    
    # 学习时间 - 根据小布的科目喜好
    if activity in ['morning_study', 'afternoon_study', 'evening_study']:
        if holiday_type == 'school_day':  # 只有上学日才有学习情绪
            if emotion_value >= 65:
                return 'studying', "学习状态"
            elif emotion_value < 40:
                return 'bored', "不想学习"
        else:
            # 假期不想学习
            return 'rebellious', "假期不想学"
    
    # 午休时间
    if activity in ['afternoon_nap', 'afternoon_rest']:
        return 'sleepy', "午休时间"
    
    # 娱乐时间
    if activity == 'entertainment' or (activity == 'free_time' and emotion_value >= 60):
        return 'playful', "放松时间"
    
    # 基础情绪判断
    if emotion_value >= 85:
        return 'very_happy', "心情超好"
    elif emotion_value >= 70:
        return 'happy', "心情不错"
    elif emotion_value >= 55:
        return 'neutral', "心情一般"
    elif emotion_value >= 40:
        return 'sad', "有点失落"
    elif emotion_value >= 25:
        return 'anxious', "心情不佳"
    else:
        return 'very_sad', "心情很差"

def record_chat_time():
    """记录聊天时间用于负载计算"""
    XIAOBU_STATE['chat_frequency'].append(datetime.now())

def check_holiday_status():
    """检查当前是否为假期"""
    now = datetime.now()
    month = now.month
    day = now.day
    
    # 检查寒假
    winter = HOLIDAY_CALENDAR['winter_vacation']
    if (month == winter['start_month'] and day >= winter['start_day']) or \
       (month == winter['end_month'] and day <= winter['end_day']):
        return 'winter_vacation', '寒假'
    
    # 检查暑假
    summer = HOLIDAY_CALENDAR['summer_vacation']
    if month >= summer['start_month'] and month <= summer['end_month']:
        if (month == summer['start_month'] and day >= summer['start_day']) or \
           (month == summer['end_month'] and day <= summer['end_day']) or \
           (month > summer['start_month'] and month < summer['end_month']):
            return 'summer_vacation', '暑假'
    
    # 检查法定节假日
    for holiday in HOLIDAY_CALENDAR['national_holidays']:
        if month == holiday['month'] and abs(day - holiday['day']) <= holiday['days'] // 2:
            return 'national_holiday', holiday['name']
    
    # 检查考试期间
    for exam in HOLIDAY_CALENDAR['exam_periods']:
        if month == exam['month'] and exam['start_day'] <= day <= exam['end_day']:
            return 'exam_period', exam['name']
    
    return 'school_day', '上学日'

def get_current_time_period():
    """获取当前时间段和对应的活动"""
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    
    # 检查假期状态
    holiday_type, holiday_name = check_holiday_status()
    
    is_weekend = weekday >= 5  # Saturday=5, Sunday=6
    
    # 假期期间使用周末时间表
    if holiday_type in ['winter_vacation', 'summer_vacation', 'national_holiday']:
        schedule = DAILY_SCHEDULE['weekend']
        is_weekend = True  # 假期当作周末处理
    else:
        schedule = DAILY_SCHEDULE['weekend' if is_weekend else 'weekday']
    
    current_time = hour + minute / 60.0
    
    for activity, time_range in schedule.items():
        if activity == 'sleep' and not is_weekend:
            # 工作日睡眠时间跨越午夜
            if current_time >= 22 or current_time < 6:
                return activity, is_weekend, holiday_type, holiday_name
        elif activity == 'sleep_in' and is_weekend:
            # 周末/假期睡眠时间
            if current_time >= 22 or current_time < 10:
                return activity, is_weekend, holiday_type, holiday_name
        else:
            start_hour, start_min, end_hour, end_min = time_range
            start_time = start_hour + start_min / 60.0
            end_time = end_hour + end_min / 60.0
            
            if start_time <= current_time < end_time:
                return activity, is_weekend, holiday_type, holiday_name
    
    return 'free_time', is_weekend, holiday_type, holiday_name

def calculate_time_factor():
    """计算基于作息时间的情绪因子"""
    activity, is_weekend, holiday_type, holiday_name = get_current_time_period()
    now = datetime.now()
    hour = now.hour
    
    factor = 0
    reason = ""
    
    # 假期期间的特殊处理
    if holiday_type == 'winter_vacation':
        factor = 30
        reason = "寒假超开心"
        if activity == 'sleep_in' and hour < 10:
            factor = -20
            reason = "寒假被吵醒"
    elif holiday_type == 'summer_vacation':
        factor = 35
        reason = "暑假太爽了"
        if activity == 'sleep_in' and hour < 11:
            factor = -15
            reason = "暑假想睡懒觉"
    elif holiday_type == 'national_holiday':
        factor = 25
        reason = f"{holiday_name}放假"
    elif holiday_type == 'exam_period':
        factor = -25
        reason = f"{holiday_name}压力大"
        if activity in ['morning_study', 'afternoon_study', 'evening_study']:
            factor = -30
            reason = "考试周不想学"
    elif is_weekend:
        # 普通周末
        if activity == 'sleep_in':
            if hour < 8:
                factor = -30
                reason = "被打扰睡眠很烦"
            else:
                factor = -15
                reason = "还想再睡会"
        elif activity == 'outdoor_morning':
            factor = 20
            reason = "想去骑车"
        elif activity == 'outdoor_afternoon':
            activities = ['露营', '徒步', '骑车']
            chosen_activity = random.choice(activities)
            factor = 25
            reason = f"想去{chosen_activity}"
        elif activity == 'afternoon_rest':
            factor = -5
            reason = "周末想补觉"
        elif activity == 'entertainment':
            factor = 15
            reason = "周末娱乐时间"
        else:
            factor = 10
            reason = "周末心情好"
    else:
        # 工作日上学
        if activity == 'sleep':
            factor = -35
            reason = "睡眠时间被打扰"
        elif activity in ['breakfast', 'lunch', 'dinner']:
            if random.random() < 0.3:  # 30%概率饿了
                factor = -20
                reason = "肚子饿了"
            else:
                factor = 5
                reason = "吃饭时间"
        elif activity in ['morning_study', 'afternoon_study']:
            # 上学日学习时间，根据科目调整情绪
            favorite_subjects = XIAOBU_IDENTITY['subjects']['favorite']
            difficult_subjects = XIAOBU_IDENTITY['subjects']['difficult']
            
            if random.choice(['数学', '物理', '语文', '英语']) in difficult_subjects:
                factor = -5
                reason = "不喜欢这科"
            elif random.choice(['体育', '美术']) in favorite_subjects:
                factor = 20
                reason = "喜欢这节课"
            else:
                factor = 5
                reason = "学习状态还行"
        elif activity == 'evening_study':
            factor = -10
            reason = "晚自习累了"
        elif activity == 'afternoon_nap':
            factor = -10
            reason = "午休时间困"
        elif activity == 'free_time':
            factor = 20
            reason = "自由时间开心"
    
    return factor, reason, holiday_type, holiday_name

def calculate_adolescent_factor():
    """计算青春期随机情绪波动因子"""
    now = datetime.now()
    
    # 检查是否处于情绪波动期
    if (XIAOBU_STATE['last_mood_swing'] and 
        (now - XIAOBU_STATE['last_mood_swing']).total_seconds() < 3600):  # 1小时内
        # 仍在上次情绪波动影响中
        current_state = XIAOBU_STATE['current_hormonal_state']
        if current_state in ADOLESCENT_MOODS:
            mood_config = ADOLESCENT_MOODS[current_state]
            return mood_config['intensity'], f"青春期{current_state}"
    
    # 随机触发新的情绪波动
    for mood, config in ADOLESCENT_MOODS.items():
        if random.random() < config['probability'] / 100:  # 降低触发概率
            XIAOBU_STATE['last_mood_swing'] = now
            XIAOBU_STATE['current_hormonal_state'] = mood
            return config['intensity'], f"青春期{mood}"
    
    # 正常状态，但有轻微随机波动
    base_randomness = random.randint(-5, 5)
    XIAOBU_STATE['current_hormonal_state'] = 'normal'
    
    return base_randomness, "青春期正常波动"

def update_stress_level():
    """更新压力等级"""
    # 基于聊天频率计算压力
    recent_chats = len([t for t in XIAOBU_STATE['chat_frequency'] 
                       if (datetime.now() - t).total_seconds() < 3600])  # 1小时内
    
    # 基于时间段增加压力
    activity, is_weekend, holiday_type, holiday_name = get_current_time_period()
    
    stress = 0
    if recent_chats > 20:
        stress += 30  # 聊天太频繁
        
    # 假期期间压力较低
    if holiday_type in ['winter_vacation', 'summer_vacation', 'national_holiday']:
        stress = max(0, stress - 20)  # 假期减压
    elif holiday_type == 'exam_period':
        stress += 40  # 考试期间压力很大
    elif activity in ['morning_study', 'afternoon_study', 'evening_study'] and not is_weekend:
        stress += 15  # 学习时间有压力
        
    if activity == 'sleep':
        stress += 40  # 睡眠被打扰压力最大
    
    XIAOBU_STATE['stress_level'] = min(100, max(0, stress))
    return stress

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
        
        # 获取当前情绪状态
        emotion_state = calculate_xiaobu_emotion()
        
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
        
        # 添加当前情绪状态
        emotion_prompt = generate_emotion_prompt(emotion_state)
        prompt_parts.append(f"# 当前情绪状态\n{emotion_prompt}")
        
        # 添加用户消息
        prompt_parts.append(f"# 用户消息\n{message}")
        
        # 组合完整prompt
        full_prompt = '\n\n'.join(prompt_parts)
        
        # 打印调试信息
        total_length = len(full_prompt)
        print(f"完整prompt长度: {total_length}字符")
        print(f"用户输入: {message[:100]}{'...' if len(message) > 100 else ''}")
        print(f"当前情绪: {emotion_state['emoji']} {emotion_state['emotion_type']} - {emotion_state['reason']}")
        
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

def generate_emotion_prompt(emotion_state):
    """生成基于当前情绪的prompt指令"""
    activity, is_weekend, holiday_type, holiday_name = get_current_time_period()
    now = datetime.now()
    
    # 基础情绪描述
    emotion_descriptions = {
        'very_happy': '心情非常好，充满活力和积极性',
        'happy': '心情不错，比较开朗和友好',
        'neutral': '心情一般，比较平静',
        'sad': '有点失落，情绪低落',
        'very_sad': '心情很差，情绪低沉',
        'angry': '感到愤怒和烦躁',
        'anxious': '感到焦虑和不安',
        'excited': '非常兴奋和激动',
        'tired': '感到疲倦',
        'stressed': '压力很大',
        'sleepy': '感到困倦想睡觉',
        'hungry': '肚子饿了，有点不耐烦',
        'energetic': '精力充沛，充满干劲',
        'moody': '情绪不稳定，容易烦躁',
        'camping': '想去露营，对户外活动感兴趣',
        'cycling': '想去骑车，对运动充满热情',
        'hiking': '想去徒步，喜欢大自然',
        'lazy_weekend': '周末想躺平，不想动',
        'studying': '在学习状态，比较专注',
        'rebellious': '有点叛逆，可能会顶嘴',
        'irritated': '心情烦躁，容易发脾气',
        'bored': '感到无聊，提不起兴趣',
        'playful': '想玩耍，比较活泼',
        'nervous': '感到紧张不安',
        'confused': '感到困惑'
    }
    
    # 活动状态描述
    activity_descriptions = {
        'sleep': '现在是睡眠时间，被打扰了很不高兴',
        'sleep_in': '周末/假期想睡懒觉，不想被打扰',
        'breakfast': '现在是早餐时间',
        'lunch': '现在是午餐时间',
        'dinner': '现在是晚餐时间',
        'morning_study': '现在是上午学习时间',
        'afternoon_study': '现在是下午学习时间',
        'evening_study': '现在是晚自习时间',
        'afternoon_nap': '现在是午休时间，有点困',
        'outdoor_morning': '上午户外活动时间',
        'outdoor_afternoon': '下午户外活动时间',
        'entertainment': '娱乐时间，想放松',
        'free_time': '自由时间，可以放松一下',
        'afternoon_rest': '下午休息时间'
    }
    
    # 假期状态描述
    holiday_descriptions = {
        'winter_vacation': '寒假期间，不用上学超开心',
        'summer_vacation': '暑假期间，自由自在',
        'national_holiday': f'{holiday_name}假期',
        'exam_period': f'{holiday_name}期间，压力很大',
        'school_day': '上学日'
    }
    
    # 青春期状态描述
    hormonal_descriptions = {
        'irritable': '青春期荷尔蒙波动，容易发脾气',
        'moody': '青春期情绪不稳定',
        'rebellious': '青春期叛逆期，可能会反驳',
        'hyperactive': '青春期精力旺盛',
        'emotional': '青春期情绪敏感',
        'normal': ''
    }
    
    emotion_desc = emotion_descriptions.get(emotion_state['emotion_type'], '心情一般')
    activity_desc = activity_descriptions.get(activity, activity)
    holiday_desc = holiday_descriptions.get(holiday_type, '普通日子')
    hormonal_desc = hormonal_descriptions.get(emotion_state.get('hormonal_state', 'normal'), '')
    
    time_str = f"{now.hour:02d}:{now.minute:02d}"
    
    # 构建身份信息
    identity = emotion_state.get('identity', XIAOBU_IDENTITY)
    favorite_subjects = "、".join(identity['subjects']['favorite'])
    difficult_subjects = "、".join(identity['subjects']['difficult'])
    interests = "、".join(identity['interests'])
    
    prompt = f"""你是{identity['name']}，{identity['age']}岁，{identity['grade']}学生，就读于{identity['school']}。

## 个人信息
- 姓名: {identity['name']}
- 年龄: {identity['age']}岁  
- 年级: {identity['grade']}
- 学校: {identity['school']}
- 地点: {identity['location']}
- 爱好: {interests}
- 喜欢的科目: {favorite_subjects}
- 不喜欢的科目: {difficult_subjects}

## 当前状态
- 时间: {time_str}
- 日期状态: {holiday_desc}
- 情绪: {emotion_state['emoji']} {emotion_desc}
- 原因: {emotion_state['reason']}
- 活动: {activity_desc}
- 情绪值: {emotion_state['emotion_value']}/100
- 压力等级: {emotion_state.get('stress_level', 0)}/100"""

    if hormonal_desc:
        prompt += f"\n- 青春期状态: {hormonal_desc}"
    
    prompt += f"""

## 回复指导
请根据你的身份和当前状态回复用户：

1. **角色一致性**: 保持{identity['age']}岁{identity['grade']}学生的身份
2. **情绪表达**: 体现当前的{emotion_state['emotion_type']}情绪
3. **时间感知**: 考虑现在是{holiday_desc}的{activity_desc}
4. **性格特点**: 展现初中生的表达方式和思维模式
5. **学科态度**: 对{difficult_subjects}表现出困难，对{favorite_subjects}表现出兴趣
6. **假期心态**: 
   - 如果是假期，不想学习，想玩耍放松
   - 如果是考试期间，表现出压力和焦虑
   - 如果是上学日，按正常作息反应
7. **地域特色**: 偶尔提及武汉的特色（如热干面、黄鹤楼等）
8. **青春期特征**: 
   - 可能会有情绪波动
   - 对某些话题比较敏感
   - 有时会表现出叛逆或倔强

用自然、真实的初中生语言回复，避免过于成熟或老气的表达。"""
    
    return prompt

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
    
    # 获取当前时间信息
    now = datetime.now()
    activity, is_weekend, holiday_type, holiday_name = get_current_time_period()
    
    return jsonify({
        'timestamp': now.isoformat(),
        'emotion': emotion_state['emotion_type'],
        'emoji': emotion_state['emoji'],
        'reason': emotion_state['reason'],
        'emotion_value': emotion_state['emotion_value'],
        'activity': emotion_state['activity'],
        'is_weekend': emotion_state['is_weekend'],
        'holiday_type': emotion_state['holiday_type'],
        'holiday_name': emotion_state['holiday_name'],
        'stress_level': emotion_state['stress_level'],
        'hormonal_state': XIAOBU_STATE['current_hormonal_state'],
        'identity': emotion_state['identity'],
        'factors': emotion_state['factors'],
        'weather': weather_data,
        'time_info': {
            'hour': now.hour,
            'minute': now.minute,
            'weekday': now.weekday(),
            'current_activity': activity
        },
        'chat_frequency_recent': len([t for t in XIAOBU_STATE['chat_frequency'] 
                                    if (now - t).total_seconds() < 600]),
        'total_chats_today': len(XIAOBU_STATE['chat_frequency'])
    })

@app.route('/api/xiaobu/schedule', methods=['GET'])
def get_xiaobu_schedule():
    """获取小布的作息时间表"""
    now = datetime.now()
    is_weekend = now.weekday() >= 5
    current_schedule = DAILY_SCHEDULE['weekend' if is_weekend else 'weekday']
    
    return jsonify({
        'timestamp': now.isoformat(),
        'is_weekend': is_weekend,
        'current_schedule': current_schedule,
        'adolescent_moods': ADOLESCENT_MOODS,
        'current_activity': get_current_time_period()[0]
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
    print("启动小布智能情绪聊天机器人...")
    print("🎭 情绪系统: 基于时间、天气、青春期特征的智能情绪曲线")
    print("📅 作息管理: 初中生作息时间表，工作日/周末模式切换")
    print("🌊 青春期模拟: 随机情绪波动、易怒、叛逆等特征")
    print("\nAPI端点:")
    print("- GET  /api/service-status     - 获取服务状态")
    print("- GET  /api/emotions           - 获取情绪分析数据")
    print("- GET  /api/emotions/summary   - 获取情绪摘要")
    print("- GET  /api/xiaobu/emotion     - 获取小布当前情绪状态")
    print("- GET  /api/xiaobu/schedule    - 获取小布作息时间表")
    print("- GET  /api/realtime/status    - 实时服务状态推送(SSE)")
    print("- GET  /api/realtime/emotions  - 实时情绪数据推送(SSE)")
    print("\n🕐 当前状态:")
    
    # 显示当前情绪状态
    try:
        emotion_state = calculate_xiaobu_emotion()
        activity, is_weekend = get_current_time_period()
        print(f"- 情绪: {emotion_state['emoji']} {emotion_state['emotion_type']} ({emotion_state['reason']})")
        print(f"- 活动: {'周末' if is_weekend else '工作日'} - {activity}")
        print(f"- 情绪值: {emotion_state['emotion_value']}/100")
        print(f"- 压力等级: {emotion_state['stress_level']}/100")
        print(f"- 青春期状态: {XIAOBU_STATE['current_hormonal_state']}")
    except Exception as e:
        print(f"- 情绪系统初始化中... ({e})")
    
    # 启动后台监控
    start_background_monitoring()
    
    app.run(debug=True, host='0.0.0.0', port=8080)